"""How much time a wave leaves the player, wave by wave: `py tools/arena_pressure.py [challenge ...]`.

There is no health in this game.  `-[ADEnemy update:]` walks an enemy in at `speed` until it is three
units away (`squared_distance < 9`), then closes at `agressiveSpeed` until it is `attack_distance` (0.3),
and then `attack` (0x100060304) posts PLAYER_DIED.  One enemy arriving is the whole game, so a wave is not
measured by how much life is in it but by **whether every enemy can be killed before its own clock runs
out** - and the clock of the one behind it is already running.

So for each enemy this works out a deadline, sorts the wave by deadline, and asks whether the guns the
challenge hands out can have killed the first *n* of them by the *n*th deadline.  The margin it prints is
the smallest slack over the whole wave: seconds to spare at the tightest moment.  Negative means nothing a
player does is fast enough.

The model is deliberately generous - it assumes every shot hits the thing with the nearest deadline, and
`--overhead` is the only allowance for finding and facing a target by ear.  A wave with a comfortable
margin here is easy in practice; a wave near zero is at the edge of possible.  It is for ordering arenas
against each other, not for promising one can be won.
"""
from __future__ import annotations

import argparse
import os
import plistlib
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from audiodefence.game import additions                              # noqa: E402

BUNDLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'game')

#: -[ADEnemy init]: the walk ends three units out, the attack lands at 0.3, and a spawn sound is a second
#: before anything moves at all (`spawn_sound_duration`, replaced by the real sound's length in play).
AGGRESSIVE_AT = 3.0
ATTACK_AT = 0.3
SPAWN_SOUND = 1.0
#: solve_explosion_with_dictionary: a blast within five units rings the ears, for `intensity * 10 + 3`
#: seconds where intensity is `1 - d^2/25`, and the rings add up to at most TINNITUS_MAX
TINNITUS_RANGE = 5.0
TINNITUS_CAP = 20.0


#: What a challenge's own `Modifiers` do to the numbers (`enemi_speed_modifier` / `enemi_life_modifier`
#: 0x1000de610, 0x1000de584).  A flag written twice is applied twice, because `applyModifier:` counts a
#: stack, so ['fasterEnemies', 'fasterEnemies'] is forty per cent.
MULT = {'speed': 1.0, 'life': 1.0}


def set_modifiers(flags) -> str:
    n = {}
    for f in flags or ():
        n[f] = n.get(f, 0) + 1
    MULT['speed'] = max(0.1, 1.0 + 0.2 * n.get('fasterEnemies', 0) - 0.1 * n.get('slowerEnemies', 0))
    MULT['life'] = max(0.1, 1.0 - 0.1 * n.get('weakerEnemies', 0) + 0.2 * n.get('strongerEnemies', 0))
    out = []
    if MULT['speed'] != 1.0:
        out.append('speed x%.2g' % MULT['speed'])
    if MULT['life'] != 1.0:
        out.append('life x%.2g' % MULT['life'])
    return ', '.join(out)


def life_of(kind: str) -> float:
    return float(ENEMIES[kind]['life']) * MULT['life']


def load(name: str):
    path = os.path.join(BUNDLE, name + '.plist')
    if os.path.exists(path):
        with open(path, 'rb') as fh:
            return plistlib.load(fh)
    return additions.PLISTS.get(name)


ENEMIES = load('enemies')
WEAPONS = {w['name']: w for w in load('Weapons')['Weapons']}


def sustained_dps(weapon: str, level: str = 'level_1', flags=()) -> float:
    """Damage a second with the reloads in it, which is what a wave is actually fought with.

    A challenge's `Modifiers` can change the clip and the reload, and those are arithmetic rather than
    judgement: `Weapon.__init__` takes a tenth off the capacity for each `lessBullets` and adds one for each
    `goldenBullet` (never below 1), and `reload_time_modifier` is a fifth either way per card.
    """
    n = {}
    for f in flags or ():
        n[f] = n.get(f, 0) + 1
    w = WEAPONS[weapon]
    lv = w.get(level) or {}
    dmg = float(lv.get('damages') or 0)
    rate = float(lv.get('fireRate') or 1)
    if w.get('melee'):
        return dmg / rate                                 # no clip and no reload, but see `reach`
    cap = float(lv.get('capacity') or 1)
    for _ in range(n.get('goldenBullet', 0)):
        cap += max(int(cap // 10), 1)
    for _ in range(n.get('lessBullets', 0)):
        cap = max(1.0, cap - max(int(cap // 10), 1))
    reload_at = float(lv.get('reloadTime') or 0) / max(
        0.2, 1.0 + 0.2 * n.get('fasterReloadTime', 0) - 0.2 * n.get('slowerReloadTime', 0))
    return (cap * dmg) / (cap * rate + reload_at)


def aim_cost(weapon: str, level: str, flags=()) -> float:
    """What the spread modifiers do to finding and facing a target.

    `spread_modifier` is five degrees a card either way and `Weapon.__init__` adds it to the weapon's own
    spread, so `narrowedSpread` twice takes the revolver's thirty degrees down to twenty.  A narrower cone is
    a smaller thing to hit by ear, and this charges the overhead in proportion.
    """
    n = {}
    for f in flags or ():
        n[f] = n.get(f, 0) + 1
    base = float((WEAPONS[weapon].get(level) or {}).get('spread') or 30)
    now = max(1.0, base + 5.0 * n.get('widerSpread', 0) - 5.0 * n.get('narrowedSpread', 0))
    return base / now


def walks_away(kind: str) -> bool:
    return BERSERK_IS_FREE and isinstance(ENEMIES[kind].get('berserk'), dict)


def hits_to_kill(kind: str, per_shot: float) -> int:
    import math
    return max(1, int(math.ceil(life_of(kind) / per_shot))) if per_shot else 1


def deadline(kind: str, distance: float, spawn_time: float) -> float:
    """Seconds from the wave starting until this enemy reaches the player, which is the end of the game."""
    if walks_away(kind):
        return float('inf')                               # it leaves on its own, unless it is shot
    e = ENEMIES[kind]
    speed = float(e.get('speed') or 0) * MULT['speed']
    if not speed:
        return float('inf')                               # it never comes to you
    aggressive = float(e.get('agressiveSpeed') or e.get('speed') or 0) * MULT['speed']
    # An enemy with a `circling` dict does not walk at the player.  State 2 heads along
    # (1 - circlingFactor) * toward-the-player + circlingFactor * sideways, so only that fraction of its
    # speed closes the distance: a Clown at 0.9 covers two tenths of a unit a second out of two.  The
    # aggressive state has no circling in it and comes straight in.
    f = _f(e.get('circling'), 'circlingFactor')
    walk = max(0.0, distance - AGGRESSIVE_AT) / (speed * max(0.05, 1.0 - f))
    close = (min(distance, AGGRESSIVE_AT) - ATTACK_AT) / aggressive
    return spawn_time + SPAWN_SOUND + walk + close


def _f(d, key: str, default: float = 0.0) -> float:
    if not isinstance(d, dict):
        return default
    v = d.get(key)
    return default if v is None else float(v)


def blast_damage(d2: float) -> float:
    """What `CHAIN_REACTION_BLAST` does at a squared distance, by `hit_by_explosion` 0x100061284.

    dispersal is 75, so three quarters of the 50 lands whatever the distance and the last quarter falls off
    as `1 - d2` - the radius cancels out of that expression, a quirk kept from the original.  So everything
    inside the radius takes at least 37.5, which is why a ring of Zombies (35 life) goes up whole and one
    holding a Hulk (100) does not.
    """
    blast = additions_blast()
    fixed = (blast['dispersal'] / 100.0) * blast['damages']
    falloff = max(0.0, 1.0 - d2)
    return fixed + (blast['damages'] - fixed) * falloff


def additions_blast() -> dict:
    from audiodefence.game.modifiers import CHAIN_REACTION_BLAST
    return {k: float(v) for k, v in CHAIN_REACTION_BLAST.items()}


def _place(one: dict):
    import math
    a = math.radians(float(one['spawn_angle']))
    d = float(one['spawn_distance'])
    return d * math.cos(a), d * math.sin(a)


def chain_from(wave: dict, first: str):
    """Who is left standing after `first` is killed and the chain has run its course."""
    blast = additions_blast()
    r2 = blast['radius'] ** 2
    at = {k: _place(v) for k, v in wave['Enemies'].items()}
    life = {k: life_of(k.split(' ')[0]) for k in wave['Enemies']}
    dead, queue = {first}, [first]
    while queue:
        k = queue.pop()
        ox, oy = at[k]
        for other in list(life):
            if other in dead:
                continue
            dx, dy = at[other][0] - ox, at[other][1] - oy
            d2 = dx * dx + dy * dy
            if d2 >= r2:
                continue
            life[other] -= blast_damage(d2)
            if life[other] <= 0.0:
                dead.add(other)
                queue.append(other)          # its own blast goes off in turn
    return {k: v for k, v in life.items() if k not in dead}


#: PORT JUDGEMENT: what being deaf is worth.  A ring leaves the player's ears ringing for up to twenty
#: seconds and the game gives that no mechanical effect at all - it is the *player* it disables, and this
#: tool would otherwise call a wave fought deaf exactly as easy as the same wave fought with ears.  Anything
#: arriving inside the ringing is charged this much more for being found and faced.
DEAF_COST = 2.5

#: PORT JUDGEMENT: what having no gun is worth.  An arena fought with the wok is fought at arm's length -
#: reach 3 - and there is no health in this game, so closing on a zombie and facing it exactly is a
#: different act from shooting one at ten units, and a swing that misses is not a lost second but the end
#: of the run.  Charged as overhead, on top of the wok's own rate of damage.
MELEE_COST = 2.0

#: PORT JUDGEMENT: what a `dodge` is worth.  An enemy with one strafes sideways at `dodgeSpeed` for
#: `dodgeTime` every time it is hit and survives - 3.5 units for Dodge, which at ten units' range is 19
#: degrees and so outside the revolver's spread.  It has to be found again after every single hit, and this
#: is charged as one overhead per hit it takes to kill.
DODGE_COST = 1.0

#: An enemy with a `berserk` dict walks *away* from the player (state 2 negates the orientation) and
#: `berserk_go_away` 0x100060944 sets its life to nought after `disappearAfter` seconds, so the wave counts
#: it as cleared without a shot being fired.  It asks nothing of the player who leaves it alone, which is how
#: it is counted here - and everything of the one who shoots it, which cannot be counted here at all.
BERSERK_IS_FREE = True

#: PORT JUDGEMENT: what a storm is worth.  `ambient_storm` is the original's own device - maya_2, "A storm
#: is coming!", whose tip says "it's hard to hear zombies through a storm" - and the game gives it no
#: mechanical effect at all beyond silencing the scare sounds (`ambient.py`).  It is the player it disables,
#: like tinnitus, so finding anything is charged this much more for the whole arena.
STORM_COST = 1.8


def extra_overhead(kind: str, overhead: float, per_shot: float) -> float:
    """What this enemy costs beyond its life, for having to be found again."""
    if isinstance(ENEMIES[kind].get('dodge'), dict):
        return overhead * DODGE_COST * (hits_to_kill(kind, per_shot) - 1)
    return 0.0


def wave_pressure(wave: dict, dps: float, overhead: float, per_shot: float = 0.0):
    """(margin, the enemy the margin belongs to, how long the wave takes to clear).

    The margin is the smallest slack over the wave: every enemy has to be dead before it arrives, and the
    best a player can do is take them in the order their clocks run out, so this walks that order and asks
    how much of it the guns can keep up with.
    """
    lives = {k: life_of(k.split(' ')[0]) for k in wave['Enemies']
             if not walks_away(k.split(' ')[0])}         # a Berserk left alone leaves by itself
    budget, note = 0.0, ''
    if wave.get('Rigged'):
        # one kill sets off the chain, and the cheapest kill is the one a player goes for
        first = min(lives, key=lambda k: lives[k])
        budget = lives[first] / dps + overhead
        left = chain_from(wave, first)
        note = ' (chain leaves %i)' % len(left)
        lives = left
    rows = []
    for key, rest in lives.items():
        kind = key.split(' ')[0]
        one = wave['Enemies'][key]
        rows.append((deadline(kind, float(one['spawn_distance']), float(one.get('spawn_time') or 0)),
                     rest, key))
    rows.sort()
    deaf_until = budget + tinnitus_for(wave)
    margin, who, spent = float('inf'), 'nothing can reach you', budget
    for due, rest, key in rows:
        kind = key.split(' ')[0]
        found = overhead * DEAF_COST if spent < deaf_until else overhead
        spent += rest / dps + found + extra_overhead(kind, overhead, per_shot)
        if due - spent < margin:
            margin, who = due - spent, key + note
    return margin, who, spent


def tinnitus_for(wave: dict) -> float:
    """How long a player is left deaf by a wave that goes off in a chain."""
    if not wave.get('Rigged'):
        return 0.0
    total = 0.0
    for one in wave['Enemies'].values():
        d2 = float(one['spawn_distance']) ** 2
        if d2 < TINNITUS_RANGE * TINNITUS_RANGE:
            total += (1 - d2 / 25.0) * 10.0 + 3.0
    return min(TINNITUS_CAP, total)


def report(name: str, overhead: float, level: str) -> None:
    d = load(name)
    if not d:
        print('%s: no such challenge' % name)
        return
    flags = tuple(d.get('Modifiers') or ())
    shown_mods = set_modifiers(flags)
    guns = [w['name'] for w in d.get('weapons') or []]
    rounds = {w['name']: int(w.get('ammo') or 0) for w in d.get('weapons') or []}
    ranged = [g for g in guns if not WEAPONS[g].get('melee')]
    melee = [g for g in guns if WEAPONS[g].get('melee')]
    ranged_dps = max((sustained_dps(g, level, flags) for g in ranged), default=0.0)
    melee_dps = max((sustained_dps(g, level, flags) for g in melee), default=0.0)

    # what the whole challenge asks for, and what its magazines hold
    need = 0.0
    for brick in d['bricks']:
        wave = load(brick)
        lives = {k: life_of(k.split(' ')[0]) for k in wave['Enemies']}
        if wave.get('Rigged'):
            first = min(lives, key=lambda k: lives[k])
            need += lives[first] + sum(chain_from(wave, first).values())
        else:
            need += sum(lives.values())
    carried = sum(rounds.get(g, 0) * float((WEAPONS[g].get(level) or {}).get('damages') or 0)
                  for g in ranged if 0 < rounds.get(g, 0) < 999)
    endless = any(rounds.get(g, 0) >= 999 for g in ranged)
    # An enemy with no speed never comes to the player, so the wok (reach 3) can never touch it and
    # `brickIsCleared` will not pass the wave until it is dead: those have to be shot, whatever else is.
    must_shoot = 0.0
    for brick in d['bricks']:
        for key in load(brick)['Enemies']:
            kind = key.split(' ')[0]
            if not float(ENEMIES[kind].get('speed') or 0):
                must_shoot += life_of(kind)

    # An arena whose magazines cannot cover a quarter of it is not fought with the gun, whatever it hands
    # out: it is fought at arm's length, and the wok is what the margins have to be measured against.
    fought_with_wok = bool(melee) and not endless and carried < need * 0.25
    dps = melee_dps if fought_with_wok else (ranged_dps or melee_dps)
    if fought_with_wok:
        overhead = overhead * MELEE_COST
    gun = (melee if fought_with_wok else ranged)[0]
    per_shot = float((WEAPONS[gun].get(level) or {}).get('damages') or 0)
    # a narrower cone is a smaller thing to find by ear, and a storm is the original's own way of making
    # everything harder to place (`ambient_storm`, maya_2)
    overhead = overhead * aim_cost(gun, level, flags)
    storm = (d.get('ambient') or {}).get('ambientPlaylist') == 'ambient_storm'
    if storm:
        overhead = overhead * STORM_COST

    print('%s  (%s)' % (d.get('title', name), name))
    print('  guns %s%s' % (', '.join('%s%s' % (g, ' x%i' % rounds[g] if rounds.get(g) else '')
                                      for g in guns),
                            '   modifiers: %s' % shown_mods if shown_mods else ''))
    print('  fought with the %s: %.1f damage a second sustained at %s%s'
          % ('wok' if fought_with_wok else ranged[0] if ranged else melee[0], dps, level.replace('_', ' '),
             ', in a storm' if storm else ''))
    worst, worst_wave = float('inf'), ''
    for brick in d['bricks']:
        wave = load(brick)
        margin, who, spent = wave_pressure(wave, dps, overhead, per_shot)
        life = sum(life_of(k.split(' ')[0]) for k in wave['Enemies'])
        deaf = tinnitus_for(wave)
        shown = 'nothing arrives' if margin == float('inf') else '%5.1fs' % margin
        print('    %-24s %2i enemies %5.0f life  %5.1fs work  margin %s  %s%s'
              % (brick.replace('port_', ''), len(wave['Enemies']), life, spent, shown, who,
                 '  [deaf %.0fs]' % deaf if deaf else ''))
        if margin < worst:
            worst, worst_wave = margin, brick.replace('port_', '')
    line = '  TIGHTEST %.1fs (%s)' % (worst, worst_wave)
    if not endless:
        line += ', ammunition carries %.0f damage' % carried
        if must_shoot:
            line += ', %.0f of which cannot be reached any other way' % must_shoot
        else:
            line += ' against %.0f needed' % need
    print(line)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('challenge', nargs='*', help='a challenge name; the default is every Extra arena')
    p.add_argument('--overhead', type=float, default=0.8,
                   help='seconds to find and face each enemy by ear (default 0.8)')
    p.add_argument('--level', default='level_1', help='the upgrade level to size against')
    args = p.parse_args()
    for name in args.challenge or additions.EXTRA_CHALLENGES:
        report(name, args.overhead, args.level)
        print()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
