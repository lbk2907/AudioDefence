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

#: -[ADEnemy init]: the walk ends three units out, and the attack lands at 0.3.
AGGRESSIVE_AT = 3.0
ATTACK_AT = 0.3
#: What an arrival sound is taken to last when its recordings cannot be read (`spawn_sound`).
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


_SPAWN_SOUNDS: dict = {}


def spawn_sound(kind: str) -> float:
    """How long an enemy stands still, making its arrival sound, before it walks.

    `-[ADEnemy spawn]` 0x10005fbc0 plays one of its `_spawn` recordings and `update:` 0x10005eb94 keeps it in
    state 1 until that has finished, so the enemy starts walking the length of the sound after its spawn
    time.  The recordings are read here, and the shortest is the one taken: a player cannot count on the
    longer one.  Until 2026-09-29 this was a flat second for everything, which is close for a Zombie
    (1.3 to 1.7 s) and not for a Hulk (3.7 to 5.7) or a Chainsaw (4.6): One Swing was measured with its
    Hulks and Chainsaws seconds early, and in the wrong order against the Runners around them.  It can be
    shot while it arrives (`canBeShotAt` 0x100061f68 refuses only states 0 and 999), so this delays its walk
    and not the first shot.
    """
    if kind not in _SPAWN_SOUNDS:
        folder = os.path.join(BUNDLE, 'sounds', 'enemies', kind)
        lengths = []
        try:
            import av
            for name in os.listdir(folder):
                if '_spawn' in name.lower():
                    with av.open(os.path.join(folder, name)) as c:
                        if c.duration:
                            lengths.append(c.duration / 1e6)
        except (ImportError, OSError):
            pass
        _SPAWN_SOUNDS[kind] = min(lengths) if lengths else SPAWN_SOUND
    return _SPAWN_SOUNDS[kind]


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
    return spawn_time + spawn_sound(kind) + walk + close


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
#: `dodgeTime` every time it is hit and survives - 3.5 units for Dodge, at random to one side, which at ten
#: units' range is 19 degrees: out of the ten either side where a hit is lined up, and after two the same
#: way out of the thirty either side the revolver reaches at all.  It has to be found again after near
#: enough every hit, and this is charged as one overhead per hit it takes to kill.  What the same strafe
#: costs the Dodge is `dodge_delay`.
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


def dodge_delay(kind: str, distance: float, per_shot: float) -> float:
    """How much later a Dodge arrives for being hit and surviving it, which is every hit but the last.

    Case 7 of `update:` 0x10005eb94 moves it at `dodgeSpeed` along its normal for `dodgeTime` and not an
    inch towards the player, so each one costs it `dodgeTime` of walking; and a sidestep square to the line
    it was walking puts it further out than it was, by sqrt(d^2 + s^2) - d, which it has to walk again.
    This was left out until 2026-09-28, and without it a Dodge was priced as though a hit did nothing to
    it but make it harder to find - which is the half of it that hurts the player, and not the half that
    helps.  The distance is taken halfway in, where most of the hits land.
    """
    e = ENEMIES[kind]
    d = e.get('dodge')
    if not isinstance(d, dict):
        return 0.0
    speed = float(e.get('speed') or 0) * MULT['speed']
    if not speed:
        return 0.0
    step = _f(d, 'dodgeTime', 0.7) * _f(d, 'dodgeSpeed', 5.0)
    mid = max(AGGRESSIVE_AT, (distance + AGGRESSIVE_AT) / 2.0)
    per_hit = _f(d, 'dodgeTime', 0.7) + (((mid * mid + step * step) ** 0.5) - mid) / speed
    return per_hit * (hits_to_kill(kind, per_shot) - 1)


def reach_time(kind: str, distance: float, spawn_time: float, at: float) -> float:
    """When an enemy walking straight in is `at` units from the player: `deadline`, stopped short."""
    e = ENEMIES[kind]
    speed = float(e.get('speed') or 0) * MULT['speed']
    if not speed or walks_away(kind):
        return float('inf')
    if distance <= at:
        return spawn_time + spawn_sound(kind)
    aggressive = float(e.get('agressiveSpeed') or e.get('speed') or 0) * MULT['speed']
    f = _f(e.get('circling'), 'circlingFactor')
    walk = max(0.0, distance - max(at, AGGRESSIVE_AT)) / (speed * max(0.05, 1.0 - f))
    close = max(0.0, min(distance, AGGRESSIVE_AT) - at) / aggressive if at < AGGRESSIVE_AT else 0.0
    return spawn_time + spawn_sound(kind) + walk + close


def wave_pressure(wave: dict, dps: float, overhead: float, per_shot: float = 0.0, swing=None):
    """(margin, the enemy the margin belongs to, how long the wave takes to clear).

    The margin is the smallest slack over the wave: every enemy has to be dead before it arrives, and the
    best a player can do is take them in the order their clocks run out, so this walks that order and asks
    how much of it the guns can keep up with.

    `swing` is `(damage, seconds between swings, reach)` for a wave fought with a melee weapon, which is two
    things a gun is not.  It cannot touch anything until it is within reach, so no work on an enemy starts
    before it has walked there; and it kills in whole swings, the first of them at once and each after it
    one cooldown later - which for the Claymore, at 2.5 seconds a swing, is the whole of the arena.
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
    def due(key: str, spawn_time: float) -> float:
        kind = key.split(' ')[0]
        one = wave['Enemies'][key]
        return (deadline(kind, float(one['spawn_distance']), spawn_time)
                + dodge_delay(kind, float(one['spawn_distance']), per_shot))

    # `spawn_after` (checkSpawnAfterKill: 0x1000a20ac) starts an enemy's clock when the one it names dies,
    # so it cannot be put in the order until that one has been dealt with.  Until 2026-09-28 they went in
    # with a spawn time of nought, as though the whole of a Hydra were standing there from the start.
    rows, waiting = [], {}
    for key, rest in lives.items():
        after = wave['Enemies'][key].get('spawn_after')
        if isinstance(after, dict) and after.get('enemy') in lives:
            waiting.setdefault(after['enemy'], []).append((key, rest, float(after.get('time') or 0)))
        else:
            rows.append((due(key, float(wave['Enemies'][key].get('spawn_time') or 0)), rest, key))
    deaf_until = budget + tinnitus_for(wave)
    margin, who, spent = float('inf'), 'nothing can reach you', budget
    born = {k: float(v.get('spawn_time') or 0) for k, v in wave['Enemies'].items()}
    while rows:
        rows.sort()
        at, rest, key = rows.pop(0)
        kind = key.split(' ')[0]
        found = overhead * DEAF_COST if spent < deaf_until else overhead
        if swing:
            damage, cooldown, reach = swing
            # it is turned to while it walks in, and struck the moment it is both faced and within reach
            ready = reach_time(kind, float(wave['Enemies'][key]['spawn_distance']), born[key], reach)
            first = spent + found if ready == float('inf') else max(spent + found, ready)
            blows = max(1, int(-(-rest // damage)))
            killed = first + (blows - 1) * cooldown
            spent = killed + cooldown
        else:
            spent += rest / dps + found + extra_overhead(kind, overhead, per_shot)
            killed = spent
        if at - killed < margin:
            margin, who = at - killed, key + note
        for brood, life, after in waiting.pop(key, ()):
            born[brood] = spent + after
            rows.append((due(brood, spent + after), life, brood))
    return margin, who, spent


# ------------------------------------------------------------------ weapons that hit more than one thing
#: Enemies a crowd-hitting weapon takes as one: spawned within this many seconds of each other, this many
#: units apart in distance, this many degrees apart in bearing, and walking within this fraction of each
#: other's pace - so that they arrive together and stay together, which is what makes them one shot.
PACK_TIME = 1.0
PACK_DISTANCE = 2.0
PACK_BEARING = 15.0
PACK_PACE = 0.25

#: How often a player turns to something new, for pricing a ring in the ears before choosing to cause one.
FINDS_EVERY = 3.0

#: `-[ADWeapon deploy]` 0x1000166e4 puts a weapon in state 1 and `update:` holds it there for
#: `switchingTime`, a second, before it will fire.
SWITCH_TIME = 1.0

#: A blast reaches five units (`-[ADProjectile init...]` 0x100053660 sets `explosionRadius` to 5 whatever
#: the weapon says) and rings the ears inside five, like any other (`solve_explosion_with_dictionary`).
BLAST_RADIUS = 5.0

#: PORT JUDGEMENT: a shotgun is fired when a shell is worth this much of what it would be worth at the
#: muzzle, and not before.  `hit_by_weapon` 0x100060b30 takes `dispersal` percent of the damage whatever the
#: distance and scales the rest by `1 - d^2 / range^2`, so the Sawn-off - dispersal 1 - does 30 at the
#: muzzle and 5 at ten units: fired early it is nearly wasted, and waiting is the skill.  Seven tenths is a
#: player who waits, but not for ever - six units for the Sawn-off.
SHOTGUN_WAIT = 0.7


def pace(kind: str) -> float:
    """How fast an enemy closes while it walks - the whole of `speed`, or the part a circle leaves."""
    e = ENEMIES[kind]
    return float(e.get('speed') or 0) * (1.0 - _f(e.get('circling'), 'circlingFactor'))


def packs(wave: dict) -> list:
    """The wave as the things a crowd-hitting weapon sees: lists of keys, a pack or a single enemy each."""
    enemies = wave['Enemies']
    keys = [k for k in enemies if not isinstance(enemies[k].get('spawn_after'), dict)]
    up = {k: k for k in keys}

    def root(k):
        while up[k] != k:
            up[k] = up[up[k]]
            k = up[k]
        return k
    for i, a in enumerate(keys):
        ea, ka = enemies[a], a.split(' ')[0]
        for b in keys[i + 1:]:
            eb, kb = enemies[b], b.split(' ')[0]
            if abs(float(ea.get('spawn_time') or 0) - float(eb.get('spawn_time') or 0)) > PACK_TIME:
                continue
            if abs(float(ea['spawn_distance']) - float(eb['spawn_distance'])) > PACK_DISTANCE:
                continue
            gap = abs(float(ea['spawn_angle']) - float(eb['spawn_angle'])) % 360.0
            if min(gap, 360.0 - gap) > PACK_BEARING:
                continue
            pa, pb = pace(ka), pace(kb)
            if max(pa, pb) and abs(pa - pb) / max(pa, pb) > PACK_PACE:
                continue
            up[root(a)] = root(b)
    groups = {}
    for k in keys:
        groups.setdefault(root(k), []).append(k)
    out = list(groups.values())
    out.extend([k] for k in enemies if k not in up)
    return out


def area_gun(name: str, level: str, flags=()) -> dict:
    """What a crowd-hitting gun does, in the terms `area_pressure` needs."""
    n = {}
    for f in flags or ():
        n[f] = n.get(f, 0) + 1
    w = WEAPONS[name]
    lv = w.get(level) or {}
    cap = float(lv.get('capacity') or 1)
    for _ in range(n.get('lessBullets', 0)):
        cap = max(1.0, cap - max(int(cap // 10), 1))
    reload_at = float(lv.get('reloadTime') or 0) / max(
        0.2, 1.0 + 0.2 * n.get('fasterReloadTime', 0) - 0.2 * n.get('slowerReloadTime', 0))
    dispersal = lv.get('dispersal')
    return {'name': name, 'explosive': bool(w.get('explosive')), 'damages': float(lv.get('damages') or 0),
            'dispersal': float(dispersal) if dispersal is not None else 100.0,
            'range': float(w.get('range') or 11), 'rate': float(lv.get('fireRate') or 1),
            'cycle': float(lv.get('fireRate') or 1) + reload_at / cap,
            'fuse': float(lv.get('timeBeforeExplode') or 0), 'flight': float(lv.get('projectileSpeed') or 0)}


def shell_at(gun: dict, d: float) -> float:
    """`hit_by_weapon`'s damage at `d` units, for a gun with a dispersal."""
    dmg, p = gun['damages'], gun['dispersal'] / 100.0
    if p >= 0.99:
        return dmg
    return dmg * p + (1.0 - d * d / (gun['range'] ** 2)) * dmg * (1.0 - p)


def distance_at(kind: str, distance: float, spawn_time: float, t: float) -> float:
    """How far out an enemy walking straight in is at time `t`."""
    e = ENEMIES[kind]
    walk = pace(kind) * MULT['speed']
    if not walk or t <= spawn_time + spawn_sound(kind):
        return distance
    aggressive = float(e.get('agressiveSpeed') or e.get('speed') or 0) * MULT['speed']
    t -= spawn_time + spawn_sound(kind)
    to_three = max(0.0, distance - AGGRESSIVE_AT) / walk
    if t <= to_three:
        return distance - walk * t
    return max(ATTACK_AT, min(distance, AGGRESSIVE_AT) - aggressive * (t - to_three))


def area_pressure(wave: dict, areas: list, single, swing, overhead: float, left: dict):
    """`wave_pressure` for a loadout with a weapon that hits a crowd.

    (margin, who, work, seconds deaf, rounds spent by weapon).  `left` is what each finite gun still holds,
    carried from wave to wave, and a gun that has run dry is not offered.

    The wave is taken pack by pack (`packs`) rather than enemy by enemy, still in the order their clocks run
    out, and each pack goes to whichever of the weapons in hand kills it soonest - a gun other than the
    last one used paying the second `deploy` takes to bring it up:

    * an **explosive** puts `dispersal` percent of its damage into everything inside five units whatever
      the distance (`hit_by_explosion` 0x100061284 - the fall-off only reaches one unit, the radius
      cancelling out of it), so a pack costs as many rounds as its toughest member needs of that, and a
      single one takes the whole of it, the shot being aimed at it.  The blast lands a fuse and a flight
      after the trigger, and **where it lands** is the price: inside five units it rings the ears, and
      everything found while they ring is found `DEAF_COST` times slower.  A pack holding anything that
      bullets do not suit - a Berserk, which a bullet wakes and a blast does not, a Riot Gear Zombie, whose
      shield stops a bullet and not a blast, a Dodge, which sidesteps a bullet and not a blast - is only
      ever given the explosive, because that is the whole reason it is in a pack.
    * a **shotgun** is not fired until its shell is worth `SHOTGUN_WAIT` of its best, so a pack cannot be
      started before it has walked in that far: the wait is the arena.
    * `single` is `(name, damage a second, damage a round)` for the ordinary gun beside it, used as
      `wave_pressure` uses it; `swing` is the melee weapon, used as `wave_pressure` uses that.
    """
    enemies = wave['Enemies']

    def kind(k):
        return k.split(' ')[0]

    def at(k):
        return float(enemies[k]['spawn_distance'])

    def whole(x):
        return max(1, int(-(-x // 1)))
    lives = {k: life_of(kind(k)) for k in enemies}
    rows = []
    for pack in packs(wave):
        fighting = [k for k in pack if not walks_away(kind(k))]
        if not fighting:
            continue
        born = {k: float(enemies[k].get('spawn_time') or 0) for k in pack}
        due = min(deadline(kind(k), at(k), born[k]) for k in fighting)
        awkward = any(isinstance(ENEMIES[kind(k)].get(x), dict) for k in pack
                      for x in ('berserk', 'shield', 'dodge'))
        rows.append((due, pack, fighting, born, awkward))
    rows.sort(key=lambda r: r[0])
    blasts = [a for a in areas if a['explosive']]
    margin, who, spent, deaf_until, deaf_total = float('inf'), 'nothing can reach you', 0.0, 0.0, 0.0
    used, last = {}, None
    for due, pack, fighting, born, awkward in rows:
        lead = min(fighting, key=lambda k: deadline(kind(k), at(k), born[k]))
        lk, ld, lt = kind(lead), at(lead), born[lead]
        toughest = max(lives[k] for k in fighting)
        only_blast = awkward and bool(blasts)
        options = []                               # (killed at, busy until, heard at, ringing, gun, rounds)
        find = overhead * (DEAF_COST if spent < deaf_until else 1.0)

        def bring(name):
            return SWITCH_TIME if last not in (None, name) else 0.0
        for area in areas:
            if only_blast and not area['explosive']:
                continue
            if area['explosive']:
                # the pack goes to the flat part of the blast, and whatever outlives the rest of it is on
                # its own after that, and takes the whole of each round aimed at it
                full = area['damages']
                flat = full * area['dispersal'] / 100.0
                rest = sorted(lives[k] for k in fighting)
                if len(rest) == 1:
                    rounds = whole(rest[0] / full)
                else:
                    rounds = whole(rest[-2] / flat)
                    if rest[-1] > rounds * flat:
                        rounds += whole((rest[-1] - rounds * flat) / full)
                if left.get(area['name'], 1e9) < rounds:
                    continue
                start = max(spent, lt + min(SPAWN_SOUND, spawn_sound(lk))) + find + bring(area['name'])
                fired = start + (rounds - 1) * area['cycle']
                out = distance_at(lk, ld, lt, fired)
                killed = fired + area['fuse'] + (out / area['flight'] if area['flight'] else 0.0)
                where = distance_at(lk, ld, lt, killed)
                ring = (1 - where * where / 25.0) * 10.0 + 3.0 if where < BLAST_RADIUS else 0.0
                options.append((killed, start + rounds * area['cycle'], killed, ring, area['name'], rounds))
            else:
                wait = 1.0 - (SHOTGUN_WAIT - area['dispersal'] / 100.0) / (1.0 - area['dispersal'] / 100.0)
                fire_at = min(ld, area['range'] * max(0.0, wait) ** 0.5)
                ready = reach_time(lk, ld, lt, fire_at)
                rounds = whole(toughest / shell_at(area, fire_at))
                if ready == float('inf') or left.get(area['name'], 1e9) < rounds:
                    continue
                start = max(spent + bring(area['name']), ready) + find
                killed = start + (rounds - 1) * area['rate']
                options.append((killed, start + rounds * area['cycle'], killed, 0.0, area['name'], rounds))
        if single and not only_blast:
            name, dps, per_shot = single
            rounds = sum(whole(lives[k] / per_shot) for k in fighting)
            if left.get(name, 1e9) >= rounds:
                t = max(spent, lt + min(SPAWN_SOUND, spawn_sound(lk))) + bring(name)
                for k in fighting:
                    t += lives[k] / dps + find + extra_overhead(kind(k), overhead, per_shot)
                options.append((t, t, t, 0.0, name, rounds))
        if swing and not only_blast:
            damage, cooldown, reach = swing
            t = spent
            for k in sorted(fighting, key=lambda k: reach_time(kind(k), at(k), born[k], reach)):
                t = max(t + find * MELEE_COST, reach_time(kind(k), at(k), born[k], reach))
                t += (whole(lives[k] / damage) - 1) * cooldown + cooldown
            options.append((t - cooldown, t, t, 0.0, None, 0))
        if not options:
            continue
        # a blast at your own feet is chosen with its price in mind: everything found while the ears ring
        # is found DEAF_COST times slower, one find every few seconds for as long as it rings
        killed, spent, heard, ring, gun, rounds = min(
            options, key=lambda o: o[0] + o[3] * (DEAF_COST - 1.0) * overhead / FINDS_EVERY)
        if gun is not None:
            last = gun
            used[gun] = used.get(gun, 0) + rounds
            if gun in left:
                left[gun] -= rounds
        if ring:
            deaf_total += ring
            deaf_until = min(max(deaf_until, heard) + ring, heard + TINNITUS_CAP)
        if due - killed < margin:
            margin, who = due - killed, lead + (' (+%i)' % (len(fighting) - 1) if len(fighting) > 1 else '')
    return margin, who, spent, deaf_total, used


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

    # A gun that hits more than one thing at a time is priced pack by pack (`area_pressure`), beside the
    # ordinary gun and the melee weapon it comes with; everything else is priced one enemy at a time.
    crowd = [g for g in ranged if WEAPONS[g].get('multihit') or WEAPONS[g].get('explosive')]
    plain = [g for g in ranged if g not in crowd and rounds.get(g, 0) > 0]
    # An arena whose magazines cannot cover a quarter of it is not fought with the gun, whatever it hands
    # out: it is fought at arm's length, and the melee weapon is what the margins have to be measured
    # against.
    fought_with_wok = bool(melee) and not crowd and not endless and carried < need * 0.25
    dps = melee_dps if fought_with_wok else (ranged_dps or melee_dps)
    if crowd:
        dps = max((sustained_dps(g, level, flags) for g in plain), default=0.0)
    gun = (melee if fought_with_wok else crowd or ranged)[0]
    per_shot = float((WEAPONS[gun].get(level) or {}).get('damages') or 0)
    swing = None
    if melee:
        mv = WEAPONS[melee[0]].get(level) or {}
        swing = (float(mv.get('damages') or 0), float(mv.get('fireRate') or 1),
                 float(WEAPONS[melee[0]].get('range') or 3))
    # a narrower cone is a smaller thing to find by ear, and a storm is the original's own way of making
    # everything harder to place (`ambient_storm`, maya_2)
    overhead = overhead * aim_cost(gun, level, flags)
    storm = (d.get('ambient') or {}).get('ambientPlaylist') == 'ambient_storm'
    if storm:
        overhead = overhead * STORM_COST
    melee_overhead = overhead
    if fought_with_wok:
        overhead = overhead * MELEE_COST

    print('%s  (%s)' % (d.get('title', name), name))
    print('  guns %s%s' % (', '.join('%s%s' % (g, ' x%i' % rounds[g] if rounds.get(g) else '')
                                      for g in guns),
                            '   modifiers: %s' % shown_mods if shown_mods else ''))
    if crowd:
        print('  fought with the %s pack by pack%s, at %s%s'
              % (crowd[0], ' and the %s one at a time (%.1f a second)' % (plain[0], dps) if plain else '',
                 level.replace('_', ' '), ', in a storm' if storm else ''))
    else:
        print('  fought with the %s: %.1f damage a second sustained at %s%s'
              % (melee[0] if fought_with_wok else ranged[0] if ranged else melee[0], dps,
                 level.replace('_', ' '), ', in a storm' if storm else ''))
    worst, worst_wave = float('inf'), ''
    left = {g: n for g, n in rounds.items() if g in ranged and n < 999}
    spend = {}
    for brick in d['bricks']:
        wave = load(brick)
        if crowd:
            areas = [area_gun(g, level, flags) for g in crowd]
            single = (plain[0], dps, float((WEAPONS[plain[0]].get(level) or {}).get('damages') or 0)) \
                if plain else None
            margin, who, spent, deaf, used = area_pressure(wave, areas, single, swing, melee_overhead, left)
            for g, n in used.items():
                spend[g] = spend.get(g, 0) + n
        else:
            margin, who, spent = wave_pressure(wave, dps, overhead, per_shot,
                                               swing if fought_with_wok else None)
            deaf = tinnitus_for(wave)
        life = sum(life_of(k.split(' ')[0]) for k in wave['Enemies'])
        shown = 'nothing arrives' if margin == float('inf') else '%5.1fs' % margin
        print('    %-24s %2i enemies %5.0f life  %5.1fs work  margin %s  %s%s'
              % (brick.replace('port_', ''), len(wave['Enemies']), life, spent, shown, who,
                 '  [deaf %.0fs]' % deaf if deaf else ''))
        if margin < worst:
            worst, worst_wave = margin, brick.replace('port_', '')
    line = '  TIGHTEST %.1fs (%s)' % (worst, worst_wave)
    if crowd:
        # a round from a crowd-hitting gun is not worth its damage once, so the plan's own count is the test
        line += ', rounds spent ' + ', '.join('%s %i of %s' % (g, spend.get(g, 0), rounds.get(g) or '-')
                                             for g in ranged)
    elif not endless:
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
