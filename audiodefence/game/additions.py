"""PORT ADDITION: the port's own content, added to the original's data as that data is read.

The rule this file exists to keep: **the plists are the original, and everything the port adds is here.**
`game/` holds Somethin' Else's files and stays exactly as they shipped it - not re-encoded, not appended
to, not corrected - and anything the port invents is declared in this module instead.  `data._load` hands
each plist through whatever is registered for it, so a new card, a new level, a new weapon or a new wave
is seen by every one of the twenty-two places that read the original's data, without any of them knowing.

**Additions only, never replacements.**  `new_key` refuses to overwrite a key the original already has,
so an addition cannot quietly shadow the game.  That keeps the line legible: if a value is in `game/` it
is theirs, and if it is here it is ours.  Changing something the original has is a different kind of
change - it belongs in the code that reads the value, where a divergence can be seen and written down in
`docs/PORTING_NOTES.md`.

What this cannot do is sound.  A new enemy or weapon that makes a noise needs recordings, and the engine
finds those by name under `game/sounds/`, which is their folder.  Audible content needs a folder of the
port's own and an engine that looks in both; this module is for data.
"""
from __future__ import annotations

import logging
import math

log = logging.getLogger('game.additions')

#: plist name -> the functions that add to it, in the order they were written
ADDITIONS: dict = {}


def adds_to(plist_name: str):
    """Register a function that is given a freshly loaded plist and adds the port's own content to it."""
    def keep(fn):
        ADDITIONS.setdefault(plist_name, []).append(fn)
        return fn
    return keep


def apply_to(plist_name: str, data):
    """Every addition registered for that plist, applied in order.  Returns the data it was given."""
    if data is None:
        return data
    for fn in ADDITIONS.get(plist_name.replace('.plist', ''), ()):
        try:
            fn(data)
        except Exception:                                 # an addition must never stop the game loading
            log.exception('the port addition %s could not be applied to %s', fn.__name__, plist_name)
    return data


def new_key(where: dict, key: str, value) -> None:
    """Add a key the original does not have.  Raises if it does: see the module docstring."""
    if key in where:
        raise KeyError('%r is the original\'s own; an addition may not replace it' % key)
    where[key] = value


def new_entry(entries: list, entry: dict) -> None:
    """Add one entry to a list the original ships.  Raises if it already holds one by that title.

    `new_key`'s counterpart: several of their plists are lists of dictionaries - the tarot decks, the
    weapons, the power-ups - and adding to one is how the port gives the game new content.  The title is
    what a player hears, so two entries sharing one would be two cards nobody could tell apart.
    """
    for existing in entries:
        if isinstance(existing, dict) and existing.get('title') == entry.get('title'):
            raise KeyError('%r is already in this list; an addition may not replace it' % entry.get('title'))
    entries.append(dict(entry))


def named(entries, name: str):
    """The entry called `name` in one of the original's lists of dictionaries, or None.

    Several of its plists are lists rather than maps - the weapons, the power-ups - each entry carrying
    its own `name`."""
    for entry in entries or ():
        if isinstance(entry, dict) and entry.get('name') == name:
            return entry
    return None


# ================================================================================ the additions themselves

#: How far past level 4 each power-up's own progression is carried.  Two cards can ask for two levels -
#: Powered Power Ups in the level-1 deck and Emergency Supplies in the level-4 one - and a card that asks
#: and gets nothing is the fault this project has taken out twice, so the data goes further than the cards
#: can reach rather than exactly as far (user request).  Four is well past the two that are possible now.
EXTRA_POWER_UP_LEVELS = 4

#: The power-up levels past the highest that can be bought, which the tarot is the only way to reach.
#:
#: Powered Power Ups says "All Power Ups are fully levelled up for this game" and gives one level, and only
#: when the data has a next one - so a player who had bought every upgrade got nothing at all from it while
#: being told it was one of the best cards in the deck.  These are the levels that player gets instead.
#:
#: They cannot be bought: the armory stops at four in three places of its own (`upgrade_button_pressed`
#: tests `level > 3`, two more test `level >= 4`), all of which read the inventory rather than this data.
#:
#: How far to carry them: two cards can ask for two levels - Powered Power Ups in the level-1 deck and
#: Emergency Supplies in the level-4 one - and a card that asks and is given nothing is the fault this
#: project has taken out twice already.  So the data goes further than any hand can reach rather than
#: exactly as far (user request).  Four is well past the two that are possible today.
EXTRA_POWER_UP_LEVELS = 4

#: `frequency` is deliberately left out.  `resetPowerUpCooldown` 0x10004b640 reads its level straight
#: from the inventory rather than through `_level_dictionary`, so the tarot has never reached the cooldown,
#: in the original or here; giving it further levels would add tiers nothing reads.
NO_EXTRA_LEVELS = ('frequency',)


def _tidy(value: float):
    """15.0 as 15 and 17.5 as 17.5, which is how the original's own levels are written."""
    return int(value) if float(value) == int(value) else float(value)


#: The port's own tarot cards, by the deck they are dealt from (user request).
#:
#: Each deck has a subject the original kept to, and these keep to it as well: level 1 is the arena and
#: what you brought to it, level 2 is the zombies, and level 3 - the card that is dealt and kept - is your
#: guns.  A deck gains as many good cards as bad ones wherever it can, so the near-even split that makes
#: the third card close to a coin flip stays that way; level 3 stands at eight good to seven bad, because
#: Executioner's opposite was already in the deck as Black Cat and needed no card of its own.
#:
#: Every `selector` here is a flag something reads.  Two are the original's own and were never dealt:
#: `fasterReloadTime` and `slowerReloadTime` are set by nothing in the original, and `reloadTimeModifier`
#: 0x1000de77c computes 1.2 and 0.8 from them and only writes the number to the log.  The other four are
#: the port's (`modifiers.PORT_FLAGS`).  The icons are chosen from the set the original already ships, so
#: nothing here needs art that is not in `game/`.
NEW_CARDS = {
    'level_1': (
        {'title': 'Air Drop Inbound', 'goodbad': 'good', 'selector': 'earlyPowerUp',
         'icon': 'Roulette_icon_increase',
         'description': 'Your first Power Up is already on its way.'},
        {'title': 'Lucky Night', 'goodbad': 'good', 'selector': 'luckyNight',
         'icon': 'Roulette_icon_luck',
         'description': 'Diamond Droppers are feeling generous. Two Diamonds each!'},
        {'title': 'Supply Delay', 'goodbad': 'bad', 'selector': 'lessPowerUps',
         'icon': 'Roulette_icon_cogs',
         'description': 'Dr. Bastard held up the delivery. Power Ups take 10 seconds longer to arrive.'},
        {'title': 'Holes In Your Pockets', 'goodbad': 'bad', 'selector': 'lessCoins',
         'icon': 'Roulette_icon_sonar',
         'description': 'Something is torn. You earn 15% fewer Coins this game.'},
    ),
    #: What the Zombies do, which is the second deck's own subject: whether they go off when they die, and
    #: whether the Farties do.  These two were a deck of their own for a while and came back here
    #: (user request), where they can be changed for 2 diamonds like everything else in it.  Powder Keg
    #: went the other way and left the tarot entirely: it is a challenge now, under Play, Extra.
    'level_2': (
        {'title': 'Chain Reaction', 'goodbad': 'both', 'selector': 'everythingExplodes',
         'icon': 'Roulette_icon_threezombies',
         'description': 'Every Zombie explodes when it dies, taking its neighbours with it. '
                        'The blasts will leave your ears ringing.'},
        {'title': 'Damp Squib', 'goodbad': 'both', 'selector': 'noFartyBlast',
         'icon': 'Roulette_icon_glue',
         'description': 'Farties no longer explode, so nothing will deafen you. '
                        'They will not clear a crowd for you either.'},
    ),

    #: The fourth deck, and the only one a hand does not always hold: every card in it gives with one hand
    #: and takes with the other, which is what a card worth waiting for should do.  `goodbad` is 'both', a
    #: value the original never uses; nothing reads it but the card art that does not ship and the
    #: analytics dimension, where `is_good` coming back False is fair for a card that is half of each.
    #: The pairs are `modifiers.PAIRED_FLAGS`.
    'level_4': (
        {'title': 'Glass Cannon', 'goodbad': 'both', 'selector': 'glassCannon',
         'icon': 'Roulette_icon_headshot',
         'description': 'Every hit you land is a critical hit. The Zombies have 20% more hit points.'},
        {'title': 'Thunder Luck', 'goodbad': 'both', 'selector': 'thunderLuck',
         'icon': 'Roulette_icon_storm',
         'description': 'Half your shots deal critical damage. A strong storm will hinder your hearing.'},
        {'title': 'Berserker', 'goodbad': 'both', 'selector': 'berserker',
         'icon': 'Roulette_icon_inject',
         'description': 'Your Melee weapon deals 25% more damage. Your guns deal 10% less.'},
        {'title': 'Blood Money', 'goodbad': 'both', 'selector': 'bloodMoney',
         'icon': 'Roulette_icon_sonar',
         'description': 'You earn 15% more Coins. Zombies move 20% faster.'},
        {'title': 'Hair Trigger', 'goodbad': 'both', 'selector': 'hairTrigger',
         'icon': 'Roulette_icon_tripleshot',
         'description': 'Reloading takes far less time. Your guns hold 10% fewer bullets.'},
        {'title': 'Heavy Artillery', 'goodbad': 'both', 'selector': 'heavyArtillery',
         'icon': 'Roulette_icon_target',
         'description': 'Your guns deal 10% more damage. Reloading takes far longer.'},
        {'title': 'Cattle Market', 'goodbad': 'both', 'selector': 'cattleMarket',
         'icon': 'Roulette_icon_cow',
         'description': 'Diamond Droppers give two Diamonds each. Dr. Bastard releases cows in the arena.'},
        {'title': 'Steady Breath', 'goodbad': 'both', 'selector': 'steadyBreath',
         'icon': 'Roulette_icon_zen',
         'description': 'Hitting enemies will be easier. Landing critical hits is twice as hard.'},
        {'title': 'Emergency Supplies', 'goodbad': 'both', 'selector': 'emergencySupplies',
         'icon': 'Roulette_icon_increase',
         'description': 'All Power Ups go up a level. They take 10 seconds longer to arrive.'},
        {'title': 'Second Chance', 'goodbad': 'both', 'selector': 'secondChance',
         'icon': 'Roulette_icon_threezombies',
         'description': 'You can revive for free on your first death. The horde grows faster and tougher.'},
        {'title': 'Iron Sights', 'goodbad': 'both', 'selector': 'ironSights',
         'icon': 'Roulette_icon_headshot',
         'description': 'Your chance of a critical hit goes up by half. Your accuracy is slightly reduced.'},
        {'title': 'House Band', 'goodbad': 'both', 'selector': 'houseBand',
         'icon': 'Roulette_icon_music',
         'description': 'You start the game with double Combo. An old jukebox plays terrible music.'},
    ),
    'level_3': (
        {'title': 'Quick Hands', 'goodbad': 'good', 'selector': 'fasterReloadTime',
         'icon': 'Roulette_icon_tripleshot',
         'description': 'Your hands fly! Reloading takes far less time.'},
        {'title': 'Heavy Hands', 'goodbad': 'bad', 'selector': 'slowerReloadTime',
         'icon': 'Roulette_icon_cogs',
         'description': 'Your hands are like lead. Reloading takes far longer.'},
        {'title': 'Executioner', 'goodbad': 'good', 'selector': 'alwaysCritical',
         'icon': 'Roulette_icon_headshot',
         'description': 'Every hit you land is a critical hit, however you aim.'},
    ),
}


@adds_to('Tarot')
def new_tarot_cards(tarot: dict) -> None:
    """Deal the port's own cards from the original's decks, and from the deck it adds."""
    for level, cards in NEW_CARDS.items():
        deck = tarot.get(level)
        if deck is None:
            new_key(tarot, level, [])                  # a level the original has no cards for at all
            deck = tarot[level]
        if not isinstance(deck, list):
            continue
        for card in cards:
            new_entry(deck, card)


@adds_to('Weapons')
def extra_power_up_levels(weapons: dict) -> None:
    """Carry each power-up's own progression past the level that can be bought.

    The step is read from the original's own last two levels rather than written down here, so each
    power-up carries on as it was going: the Minigun's duration by 2.5 (10 to 12.5), the Fireworks' damage
    and the Tornado's reach by 2, the Tesla's kills by 1.  That reproduces exactly the hand-written
    `level_5` this replaced - 15 seconds, 9 damage, 5 kills, 7 of reach - and goes on from there.

    With the levels in the data, `_level_dictionary`'s own rule does the rest: it climbs one level for
    every card that asked, as far as there is a level to climb to.  The tiers past what any hand can
    reach are inert, since nothing reads a key nobody asks for, and they are there so that adding a card
    later cannot quietly leave one doing nothing (user request).
    """
    for entry in weapons.get('PowerUps') or ():
        if not isinstance(entry, dict) or entry.get('name') in NO_EXTRA_LEVELS:
            continue
        third, fourth = entry.get('level_3'), entry.get('level_4')
        if not isinstance(third, dict) or not isinstance(fourth, dict):
            continue
        stats = [k for k in fourth if k != 'upgradeCost' and k in third]
        if not stats:
            continue
        value = {k: float(fourth[k]) for k in stats}
        step = {k: float(fourth[k]) - float(third[k]) for k in stats}
        for n in range(5, 5 + EXTRA_POWER_UP_LEVELS):
            value = {k: value[k] + step[k] for k in stats}
            new_key(entry, 'level_%i' % n, {k: _tidy(value[k]) for k in stats})


# ============================================================== plists of the port's own
#: PORT ADDITION (user request): whole files the original does not have, rather than additions to files it
#: does.  `data._load` falls back to these when the bundle has nothing by that name, so a challenge the
#: port wrote and the waves it is made of are read exactly as the game's own are - by name, through the one
#: function, by every screen that asks.
#:
#: The waves are where the work is, and almost none of it is code.  A ring is a wave whose zombies stand at
#: one distance and even angles, which is what `spawn_angle` and `spawn_distance` have always meant; the
#: `Rigged` key gives each of them the blast the game gives a Farty, so one shot takes the ring; and
#: `NoBlast` on the crowd that follows promises the opposite, whatever a player is carrying.  The engine
#: does the rest: it activates the playlists a wave names, so a ring of four kinds is four kinds a player
#: can hear, and it moves to the next wave when one is cleared, which is what makes three rings a
#: challenge of three waves.
def _ring(kinds, count: int, distance: float, rigged: bool, every: float = 0.0) -> dict:
    """A wave standing in a circle at one distance, the kinds taken in turn round it.

    `every` staggers them: a ring arrives all at once, because a ring is one thing to be set off, while a
    crowd walks in one at a time, which is what makes it a crowd to be worked through rather than a
    second ring.
    """
    enemies = {}
    for i in range(count):
        one = {'spawn_angle': round(i * 360.0 / count, 2), 'spawn_distance': distance}
        if every:
            one['spawn_time'] = round(i * every, 2)
        enemies['%s %i' % (kinds[i % len(kinds)], i + 1)] = one
    wave = {'Enemies': enemies}
    wave['Rigged' if rigged else 'NoBlast'] = True
    return wave


#: A wave built from a list of places, for the shapes a plain ring cannot make.
#:
#: Each entry is `(kind, angle, distance)` or `(kind, angle, distance, spawn_time)`.  The names are numbered
#: as they go in, because `Enemies` is a dictionary and the kind is read back off the front of the key
#: (`name.split(' ')[0]`), so two of a kind need two keys.
def _wave(spec, rigged: bool = False, no_blast: bool = False, passers=None) -> dict:
    enemies = {}
    for i, one in enumerate(spec):
        d = {'spawn_angle': float(one[1]) % 360.0, 'spawn_distance': float(one[2])}
        if len(one) > 3:
            d['spawn_time'] = float(one[3])
        enemies['%s %i' % (one[0], i + 1)] = d
    wave = {'Enemies': enemies}
    if rigged:
        wave['Rigged'] = True
    elif no_blast:
        wave['NoBlast'] = True
    if passers:
        wave['PasserBy'] = {k: dict(v) for k, v in passers.items()}
    return wave


#: Bearings a crowd walks in from, well apart so a player has to turn to each in turn rather than sweep.
#: They are written down rather than worked out so that a wave is the same wave every time it is played:
#: a challenge has stars on it, and a star won against one arrangement has to mean the same as the next.
SCATTER = (0.0, 143.0, 71.0, 251.0, 35.0, 196.0, 108.0, 305.0, 161.0, 18.0, 233.0, 88.0, 278.0, 125.0,
           52.0, 214.0, 341.0, 97.0, 179.0, 263.0)


def _crowd(kinds, count: int, distance: float, every: float, first: float = 0.0,
           bearings=SCATTER, no_blast: bool = True) -> dict:
    """A crowd walking in one at a time from bearings all round, which is the shape of most of these.

    `every` is what makes a wave hard or not.  Nothing here has any health to lose - one enemy reaching the
    player ends the game (`attack` 0x100060304) - so a wave is not its total life but whether each of them
    can be killed before its own clock runs out, and `every` is what decides how much those clocks overlap.
    """
    return _wave([(kinds[i % len(kinds)], bearings[i % len(bearings)], distance,
                   round(first + i * every, 2)) for i in range(count)], no_blast=no_blast)


def _metronome(kinds, count: int, distance: float, every: float,
               bearings=(0.0, 90.0, 180.0, 270.0)) -> dict:
    """A crowd that keeps time, going round the same few bearings in turn - Clockwork, and nothing else."""
    return _crowd(kinds, count, distance, every, bearings=bearings)


def _ring_with_strays(kinds, count: int, distance: float, strays) -> dict:
    """A rigged ring, and enemies standing far enough out that the chain never reaches them.

    A ring is a free wave and is meant to be: `CHAIN_REACTION_BLAST` puts 37.5 into everything within three
    units (`hit_by_explosion` 0x100061284, dispersal 75), so one shot takes a ring of anything with 35 life
    or less and the player pays for it in **hearing** - a blast inside five units rings the ears for
    `intensity * 10 + 3` seconds and they add up to TINNITUS_MAX.  What a player does about the strays, deaf,
    is the arena.  Nothing tough ever goes in a ring: it would survive the chain three units from the
    player, which is close enough to be lethal before anything could be done about it.
    """
    spec = [(kinds[i % len(kinds)], round(i * 360.0 / count, 2), distance) for i in range(count)]
    return _wave(spec + list(strays), rigged=True)


#: A cow walks past and is worth nothing: 1 life, no explosion, and it leaves on its own once it is fifteen
#: units out.  `PasserBy` is keyed by the kind itself rather than by a numbered name, so a wave can hold one
#: of each - three cows, and the jukebox that cannot be killed at all (a hundred million life).
def _cows(*places) -> dict:
    return {'Cow%s' % (i + 1 if i else ''): {'spawn_angle': float(a), 'spawn_distance': float(d),
                                             'spawn_time': float(t)}
            for i, (a, d, t) in enumerate(places)}


PLISTS: dict = {}

# =========================================================================================== the arenas
#: The port's own arenas, in the order they were written rather than the order they are played: `CHAPTERS`
#: at the end of this file says which chapter each is in and where, and that order is the one
#: `tools/arena_pressure.py` puts them in.
#:
#: That tool exists because of how this game kills you.  There is no health: an enemy that reaches the
#: player ends the game there and then, so what makes a wave hard is not how much life is in it but whether
#: every one of them can be killed before its own clock runs out - and the clock of the one behind it is
#: already running.  It works that out wave by wave and prints the slack at the tightest moment, and the
#: arenas are tuned to one curve of it across every chapter.  Short is not impossible: the tool counts only
#: the gun, and a player also has a wok worth 25 a swing inside three units, headshots, and whatever they
#: have spent diamonds on.
#:
#: The first build of these was tuned by eye, and by eye every one of them was wrong.  Three Bullets could
#: not be lost - three rigged rings and a modifier that made every hit a kill, so firing in any direction at
#: all cleared a wave - and Powder Keg's third ring could not be won, because four Hulks stood inside it
#: surviving the chain three units from the player.  Neither was visible without measuring.

# ----------------------------------------------------------------------------------------- Barnyard
#: Listening, and nothing else.  Three cows walk through every wave and a jukebox plays in the last one;
#: QuietZombie is the one to find, 35 life and the softest walk in the game.  Forty-five rounds against 405
#: of life is 4.5 rounds of slack at level one, so a cow shot is a kill given away.
PLISTS['port_barnyard_1'] = _crowd(('WeakZombie', 'WeakZombieB', 'Zombie'), 3, 10.0, 6.0)
PLISTS['port_barnyard_1']['PasserBy'] = _cows((70, 11, 1), (210, 11, 5), (320, 11, 9))
PLISTS['port_barnyard_2'] = _crowd(('QuietZombie', 'WeakZombie', 'Zombie', 'ZombieB', 'WeakZombieB'),
                                   5, 10.0, 4.5)
PLISTS['port_barnyard_2']['PasserBy'] = _cows((10, 11, 2), (180, 11, 7), (260, 11, 12))
PLISTS['port_barnyard_3'] = _crowd(('QuietZombie', 'WeakZombie', 'ZombieB', 'QuietZombie', 'ZombieC',
                                    'WeakZombieB'), 6, 10.0, 3.0)
PLISTS['port_barnyard_3']['PasserBy'] = dict(
    _cows((60, 11, 1), (150, 11, 6), (290, 11, 11)),
    Jukebox={'spawn_angle': 215.0, 'spawn_distance': 9.0, 'spawn_time': 3.0})
PLISTS['port_barnyard'] = {
    'challenge_id': 'port_barnyard',
    'title': 'Barnyard',
    'objective': 'Not everything out here is dead, and you were not given much ammunition.',
    'tip': 'Listen before you fire. Some of what you can hear is only in the way, and the wok never runs '
           'out.',
    'icon': 'Challenge_icon_02', 'icon_title': 'BY',
    'weapons': [{'name': 'pistol', 'ammo': '42'}, {'name': 'wok'}],
    'bricks': ['port_barnyard_1', 'port_barnyard_2', 'port_barnyard_3'],
    'ambient': {'ambientPlaylist': 'ambient_roman', 'gain': 0.5},
    'time_limit_star': {'reward': 150, 'objective': 150},
    'accuracy_star': {'reward': 150, 'objective': 60},
}

# ----------------------------------------------------------------------------------------- The Wall
#: A revolver against things that do not die to a cylinder.  A Hulk has 100 life and walks at 0.75, which
#: is sixteen seconds from twelve units and six seconds of shooting - so one is nothing and three at once
#: are the arena.  The Riot Gear Zombie is the other half of it: 150 life, and `protect` 0x10005ff4c stops
#: it dead for five seconds every time it is hit, so it delays itself and the Hulks walk on past it.
PLISTS['port_wall_1'] = _wave([('Hulk', 90, 12), ('HulkB', 300, 12, 9)], no_blast=True)
PLISTS['port_wall_2'] = _wave([('Hulk', 40, 12), ('Shield', 175, 12, 8), ('HulkB', 290, 12, 16)],
                              no_blast=True)
PLISTS['port_wall_3'] = _wave([('Hulk', 20, 12), ('HulkB', 160, 12, 10), ('Shield', 95, 12, 20),
                               ('Hulk', 255, 12, 30), ('HulkB', 310, 12, 40)], no_blast=True)
PLISTS['port_wall'] = {
    'challenge_id': 'port_wall',
    'title': 'The Wall',
    'objective': 'Six rounds in the cylinder, and nothing out here dies to six rounds.',
    'tip': 'Reload before you need to, not when you find out. One of them will not let you hit it twice in '
           'a row, so leave it and come back to it.',
    'icon': 'Challenge_icon_02', 'icon_title': 'WL',
    'weapons': [{'name': 'pistol', 'ammo': '999'}, {'name': 'wok'}],
    'bricks': ['port_wall_1', 'port_wall_2', 'port_wall_3'],
    'ambient': {'ambientPlaylist': 'ambient_roman', 'gain': 0.5},
    'time_limit_star': {'reward': 150, 'objective': 170},
    'accuracy_star': {'reward': 200, 'objective': 55},
}

# ---------------------------------------------------------------------------------------- Clockwork
#: The same four bearings over and over, on a beat that tightens.  Nothing here is hard to kill and the
#: pistol never runs dry; the whole of it is whether a player works out that the next one is already coming
#: from where the last one did, and is turned that way before it arrives.  The last wave opens out to eight
#: bearings, so the pattern is still a pattern but twice as long to learn.
PLISTS['port_clockwork_1'] = _metronome(('WeakZombie', 'Zombie'), 8, 10.0, 3.0)
PLISTS['port_clockwork_2'] = _metronome(('WeakZombie', 'Zombie', 'ZombieB', 'QuietZombie'), 12, 10.0, 2.2)
PLISTS['port_clockwork_3'] = _metronome(('Zombie', 'QuietZombie', 'ZombieB', 'WeakZombie'), 16, 11.0, 1.9,
                                        bearings=(0.0, 90.0, 180.0, 270.0, 45.0, 135.0, 225.0, 315.0))
PLISTS['port_clockwork'] = {
    'challenge_id': 'port_clockwork',
    'title': 'Clockwork',
    'objective': 'Something out here is keeping time. You will hear it before you can use it.',
    'tip': 'They are not choosing where to come from. Once you know that, you can be pointing the right '
           'way before the next one arrives.',
    'icon': 'Challenge_icon_02', 'icon_title': 'CW',
    'weapons': [{'name': 'pistol', 'ammo': '999'}, {'name': 'microsmg', 'ammo': '300'}, {'name': 'wok'}],
    'bricks': ['port_clockwork_1', 'port_clockwork_2', 'port_clockwork_3'],
    'ambient': {'ambientPlaylist': 'ambient_roman', 'gain': 0.5},
    'time_limit_star': {'reward': 150, 'objective': 150},
    'accuracy_star': {'reward': 150, 'objective': 45},
}

# ------------------------------------------------------------------------------------- The Survivor
#: Setting off the ring is free and is meant to be.  What it costs is twenty seconds of hearing, and what
#: walks in during those twenty seconds is the arena: QuietZombies, which are hard enough to place with
#: ears that work, and a Runner that gives no time to hunt.
PLISTS['port_survivor_1'] = _ring_with_strays(
    ('WeakZombie', 'WeakZombieB'), 8, 2.8,
    [('Zombie', 135, 9.0, 1.0), ('QuietZombie', 300, 9.5, 5.0), ('Zombie', 40, 9.0, 9.0),
     ('Runner', 210, 11.0, 12.0)])
PLISTS['port_survivor_2'] = _ring_with_strays(
    ('WeakZombie', 'Zombie', 'WeakZombieB'), 10, 2.7,
    [('QuietZombie', 250, 9.5, 1.0), ('Zombie', 20, 9.0, 4.0), ('QuietZombie', 160, 9.5, 7.0),
     ('ZombieB', 300, 9.0, 10.0), ('Runner', 85, 11.0, 13.0), ('QuietZombie', 130, 9.5, 17.0)])
PLISTS['port_survivor_3'] = _ring_with_strays(
    ('WeakZombie', 'Zombie', 'ZombieB', 'WeakZombieC'), 12, 2.6,
    [('QuietZombie', 20, 9.5, 1.0), ('Zombie', 190, 9.0, 3.5), ('QuietZombie', 110, 9.5, 6.0),
     ('ZombieB', 250, 9.0, 8.5), ('Runner', 290, 11.0, 11.0), ('QuietZombie', 60, 9.5, 14.0),
     ('ZombieC', 330, 9.0, 16.5), ('RunnerB', 225, 11.0, 19.0)])
PLISTS['port_survivor'] = {
    'challenge_id': 'port_survivor',
    'title': 'The Survivor',
    'objective': 'They are all standing close together. Except the ones that are not.',
    'tip': 'It will be quiet for a while afterwards, and that is not a fault. Something is still walking, '
           'and one of them is not walking slowly.',
    'icon': 'Challenge_icon_02', 'icon_title': 'SV',
    'weapons': [{'name': 'pistol', 'ammo': '999'}, {'name': 'microsmg', 'ammo': '150'}, {'name': 'wok'}],
    'bricks': ['port_survivor_1', 'port_survivor_2', 'port_survivor_3'],
    'ambient': {'ambientPlaylist': 'ambient_roman', 'gain': 0.5},
    'time_limit_star': {'reward': 200, 'objective': 140},
    'accuracy_star': {'reward': 150, 'objective': 40},
}

# ----------------------------------------------------------------------------------------- Stampede
#: Everything that runs.  A Runner covers 1.3 units a second, a Chainsaw 1.45 and a Clown 2, so from twelve
#: units the first one is on a player in six seconds and they keep arriving closer together.  And the arena
#: asks to be played with `fasterEnemies`, which is `enemi_speed_modifier` at 1.2 on the walk (the charge is
#: read before it): the same crowd, a sixth less time to deal with it.
PLISTS['port_stampede_1'] = _crowd(('Runner', 'RunnerB'), 4, 12.0, 4.0)
PLISTS['port_stampede_2'] = _crowd(('Runner', 'Chainsaw', 'RunnerB', 'RunnerC'), 8, 12.0, 2.4)
PLISTS['port_stampede_3'] = _crowd(('Runner', 'Chainsaw', 'RunnerB', 'Clown', 'RunnerC'), 11, 12.0, 2.1)
PLISTS['port_stampede'] = {
    'challenge_id': 'port_stampede',
    'title': 'Stampede',
    'objective': 'You will hear them before you are ready for them.',
    'tip': 'Whichever one is closest, whatever it is. Turning to the loudest one is how this is lost.',
    'icon': 'Challenge_icon_02', 'icon_title': 'ST',
    'weapons': [{'name': 'pistol', 'ammo': '999'}, {'name': 'microsmg', 'ammo': '400'}, {'name': 'wok'}],
    'bricks': ['port_stampede_1', 'port_stampede_2', 'port_stampede_3'],
    'ambient': {'ambientPlaylist': 'ambient_roman', 'gain': 0.5},
    #: PORT ADDITION (user request): the modifiers this arena is played with, whatever the deck last did.
    #: A flag written twice is applied twice, and `times()` counts the stack; this one is written once, +20%.
    'Modifiers': ['fasterEnemies'],
    'time_limit_star': {'reward': 200, 'objective': 120},
    'accuracy_star': {'reward': 200, 'objective': 35},
}

# ------------------------------------------------------------------------------------ Three Bullets
#: Three rounds, and three things out there that no number of rounds will reach any other way.
#:
#: Ted, Jim and Bob are zombies with the whole sound set - spawn, approach, aggressive, hit, death - and a
#: speed of 0.  They stand where they spawn and never come, so the wok cannot touch them (it reaches 3) and
#: `brickIsCleared` 0x1000a1658 will not pass the wave until they are dead.  So: one round each, three of
#: them, three rounds, and no modifier propping it up.
#:
#: They are Bob, who has 1 life, and not Ted and Jim, who have 10 (2026-09-30).  The revolver's `dispersal`
#: is 90, so at level one a round does 9 and a fraction of a point anywhere but at the muzzle, and only a
#: hit within its ten-degree `criticalSpread` (x1.3) or a critical made 10: a round on target that was a
#: few degrees off left Ted standing on under one life, with nothing left to finish him and nothing to say
#: why.  Bob dies to any round that finds him, which is what the arena always claimed.
#:
#: Everything else in here walks, and has to be met with the wok at arm's length, because there is nothing
#: left to shoot it with.  A WeakZombie is one swing and a Zombie is two; they arrive far enough apart to be
#: taken one at a time and near enough together that there is no time to think between them.  Spend a round
#: on one of them and the wave it belongs to cannot be finished at all.
#:
#: The last wave had a Runner in it until 2026-09-28, arriving at arm's length a second before two Zombies
#: did.  A Runner is two seconds inside the wok's reach and two swings, so it leaves one second to spare at
#: the very best, and with two more behind it that was a chapter 2 moment in the fourth arena of chapter 1 -
#: invisible while the tool let the wok swing at things ten units away (`wave_pressure`'s `swing`).
PLISTS['port_three_bullets_1'] = _wave(
    [('Bob', 200, 9.0), ('WeakZombie', 0, 9.0, 2.0), ('Zombie', 120, 9.0, 8.0)], no_blast=True)
PLISTS['port_three_bullets_2'] = _wave(
    [('Bob', 60, 10.0), ('Zombie', 250, 9.0, 1.0), ('WeakZombie', 140, 9.0, 4.0),
     ('ZombieB', 20, 9.0, 8.0)], no_blast=True)
PLISTS['port_three_bullets_3'] = _wave(
    [('Bob', 310, 10.0), ('Zombie', 45, 9.0, 1.0), ('ZombieB', 190, 9.0, 5.0),
     ('ZombieC', 105, 9.0, 10.0), ('WeakZombieB', 265, 9.0, 14.0), ('Zombie', 330, 9.0, 18.0)],
    no_blast=True)
PLISTS['port_three_bullets'] = {
    'challenge_id': 'port_three_bullets',
    'title': 'Three Bullets',
    'objective': 'Three rounds is all you are given, and three of them will not come to you.',
    'tip': 'Work out which ones you cannot reach with the wok, and save your rounds for those. There are '
           'exactly enough and not one spare, so if the arena goes quiet and will not end, a round went '
           'somewhere it should not have. End the challenge and start again.',
    'icon': 'Challenge_icon_02', 'icon_title': '3B',
    'weapons': [{'name': 'pistol', 'ammo': '3'}, {'name': 'wok'}],
    'bricks': ['port_three_bullets_1', 'port_three_bullets_2', 'port_three_bullets_3'],
    'ambient': {'ambientPlaylist': 'ambient_roman', 'gain': 0.5},
    'time_limit_star': {'reward': 200, 'objective': 150},
    'accuracy_star': {'reward': 200, 'objective': 80},
}

# --------------------------------------------------------------------------------------- Powder Keg
#: All of it at once.
#:
#: Three rings, and a crowd walking in behind each while the ring is still ringing in the player's ears.
#: The rings are free and deafening - nothing tough stands in one, because a Hulk three units away that
#: survived the chain is a death nobody could have prevented - and the crowds are where the work is: nothing
#: in them explodes, whatever a player is carrying, so every one of them has to be killed, and the third one
#: is nine of them with the Hulks in it, arriving one every second and a half from eight units.
RINGS = (
    (('WeakZombie', 'WeakZombieB', 'Zombie', 'ZombieB'), 10, 3.5),
    (('WeakZombie', 'Zombie', 'ZombieB', 'ZombieC'), 12, 3.2),
    (('WeakZombie', 'Zombie', 'ZombieB', 'WeakZombieC', 'ZombieC'), 12, 3.0),
)
CROWDS = (
    (('WeakZombie', 'Zombie', 'Farty', 'ZombieB'), 5, 10.0, 2.0),
    (('Zombie', 'Runner', 'Farty', 'ZombieB', 'QuietZombie'), 7, 9.0, 1.8),
    (('Runner', 'Zombie', 'Hulk', 'RunnerB', 'Farty', 'ZombieB', 'HulkB'), 9, 9.0, 1.6),
)
for _n, (_k, _c, _d) in enumerate(RINGS, start=1):
    PLISTS['port_keg_ring_%i' % _n] = _ring(_k, _c, _d, rigged=True)
for _n, (_k, _c, _d, _e) in enumerate(CROWDS, start=1):
    PLISTS['port_keg_crowd_%i' % _n] = _crowd(_k, _c, _d, _e)
del _n, _k, _c, _d, _e

PLISTS['port_keg'] = {
    'challenge_id': 'port_keg',
    'title': 'Powder Keg',
    'objective': 'Six crowds, and half of them came standing far too close together.',
    'tip': 'Find out what a crowd that close is good for, and then be quick about it, because the rest are '
           'already walking in and you will not hear them coming.',
    'icon': 'Challenge_icon_02', 'icon_title': 'PK',
    'weapons': [{'name': 'pistol', 'ammo': '999'}, {'name': 'microsmg', 'ammo': '200'},
                {'name': 'wok'}],
    'bricks': ['port_keg_ring_1', 'port_keg_crowd_1',
               'port_keg_ring_2', 'port_keg_crowd_2',
               'port_keg_ring_3', 'port_keg_crowd_3'],
    'ambient': {'ambientPlaylist': 'ambient_roman', 'gain': 0.5},
    'time_limit_star': {'reward': 200, 'objective': 180},
    'accuracy_star': {'reward': 200, 'objective': 40},
}


# =========================================================================================== chapter 2
#: Chapter 2, which carries on from where Powder Keg left off (user request) and is built out of the parts of
#: this engine chapter 1 never touched: the enemies that dodge, the one that runs away, the static bombs, the
#: 500-life one, and `spawn_after`, which lets a wave answer a kill with more of itself.

# ---------------------------------------------------------------------------------------- Scrapyard
#: Parked cars, and an economy.
#:
#: A Car keeps its own explosion out of `enemies.plist` - radius 3, 30 damage, dispersal 50, which by
#: `hit_by_explosion` is 15 flat plus 15 more falling off inside one unit.  So a car kills nothing outright
#: and takes 15 off everything within three units of it, and the question is whether the zombies walking past
#: are worth the rounds the car itself costs: 35 for a Car, 50 and 80 for the other two.  Thirty-six rounds
#: against four hundred of life says: only if you wait for two or three of them.
#:
#: They go in as `PasserBy` and not as enemies, which is where the game puts them and the only place they
#: work.  `sounds/passerBy/Car` holds an alarm, a spawn, an impact and a death and **no `_approach_`**, so a
#: Car driven by the enemy state machine would fall silent the moment it finished spawning - an invisible,
#: inaudible thing that `brickIsCleared` would still wait for.  As a passer-by, `CarAlarm` loops the alarm so
#: it can be found, it can be shot like anything else, it explodes when it dies, and it holds nothing up if a
#: player decides it is not worth a round.
#:
#: The zombies spawn on the cars' own bearings, further out, so they walk onto them.
def _scrap(cars, crowd) -> dict:
    wave = _wave(crowd, no_blast=True)
    wave['PasserBy'] = {kind: {'spawn_angle': float(a), 'spawn_distance': 6.0, 'spawn_time': 0.5}
                        for kind, a in cars}
    return wave


PLISTS['port_scrap_1'] = _scrap(
    (('Car', 70), ('Machine', 250)),
    [('WeakZombie', 70, 10.0, 1.0), ('Zombie', 70, 11.0, 3.0), ('WeakZombieB', 68, 12.0, 5.0),
     ('Zombie', 250, 10.0, 8.0), ('ZombieB', 252, 11.0, 10.0), ('WeakZombieC', 248, 12.0, 12.0)])
PLISTS['port_scrap_2'] = _scrap(
    (('Car', 40), ('Car2', 200), ('Machine', 310)),
    [('WeakZombie', 40, 10.0, 1.0), ('Zombie', 42, 11.0, 2.6), ('ZombieB', 38, 12.0, 4.2),
     ('WeakZombieB', 200, 10.0, 5.8), ('Zombie', 202, 11.0, 7.4), ('QuietZombie', 198, 12.0, 9.0),
     ('ZombieC', 310, 10.0, 10.6), ('WeakZombieC', 312, 11.0, 12.2), ('Zombie', 120, 11.0, 13.8)])
PLISTS['port_scrap_3'] = _scrap(
    (('Car', 20), ('Car2', 140), ('Car3', 260)),
    [('WeakZombie', 20, 10.0, 1.0), ('Zombie', 22, 11.0, 2.4), ('ZombieB', 18, 12.0, 3.8),
     ('WeakZombieB', 140, 10.0, 5.2), ('Zombie', 142, 11.0, 6.6), ('QuietZombie', 138, 12.0, 8.0),
     ('WeakZombieC', 260, 10.0, 9.4), ('ZombieC', 262, 11.0, 10.8), ('QuietZombie', 258, 12.0, 12.2),
     ('Runner', 330, 11.0, 14.0), ('ZombieB', 60, 11.0, 15.4), ('QuietZombie', 180, 11.0, 16.8)])
PLISTS['port_scrap'] = {
    'challenge_id': 'port_scrap',
    'title': 'Scrapyard',
    'objective': 'Sixty rounds, and a good deal more than sixty of them out there.',
    'tip': 'Not everything making a noise out here is a zombie, and some of it is worth more to you than '
           'the rounds it costs. Wait until it is worth it.',
    'icon': 'Challenge_icon_02', 'icon_title': 'SY',
    'weapons': [{'name': 'pistol', 'ammo': '60'}, {'name': 'wok'}],
    'bricks': ['port_scrap_1', 'port_scrap_2', 'port_scrap_3'],
    'ambient': {'ambientPlaylist': 'ambient_roman', 'gain': 0.5},
    'time_limit_star': {'reward': 250, 'objective': 190},
    'accuracy_star': {'reward': 250, 'objective': 55},
}

# ----------------------------------------------------------------------------------------- Sidestep
#: The target that will not stay found.  A Dodge has 80 life and `dodge` {dodgeTime 0.7, dodgeSpeed 5}, and
#: `hit_by_weapon` 0x100060b30 sends it into state 7 every time it is hit and survives: 3.5 units sideways, at
#: random to one side, which at ten units out is nineteen degrees.  That is still inside the thirty either
#: side the revolver reaches, but outside the ten either side where a hit is lined up, and two the same way
#: are outside both - so eight rounds at level one means being found again, near enough eight times.
#:
#: What it costs the Dodge is ground: case 7 of `update:` does not walk it in, and a step square to its line
#: puts it further out than it was.  Until 2026-09-28 the tool only counted what it cost the player, and on
#: that half of the sum this arena measured five seconds short; on the whole of it, four to spare, which is
#: chapter 1.  So it has more walkers and a third Dodge now, to be the arena it was placed as.
PLISTS['port_sidestep_1'] = _wave(
    [('Dodge', 60, 12.0), ('WeakZombie', 200, 10.0, 3.0), ('Zombie', 300, 10.0, 7.0),
     ('ZombieB', 140, 10.0, 11.0)], no_blast=True)
PLISTS['port_sidestep_2'] = _wave(
    [('Dodge', 30, 12.0), ('DodgeB', 210, 12.0, 9.0), ('Zombie', 120, 10.0, 2.0),
     ('WeakZombie', 280, 10.0, 7.0), ('ZombieB', 160, 10.0, 12.0), ('QuietZombie', 330, 10.0, 17.0)],
    no_blast=True)
PLISTS['port_sidestep_3'] = _wave(
    [('Dodge', 20, 12.0), ('DodgeB', 150, 12.0, 7.0), ('Dodge', 270, 12.0, 18.0),
     ('Zombie', 90, 10.0, 2.0), ('Runner', 330, 11.0, 6.0), ('ZombieB', 190, 10.0, 11.0),
     ('QuietZombie', 60, 10.0, 15.0), ('Zombie', 230, 10.0, 22.0)], no_blast=True)
PLISTS['port_sidestep'] = {
    'challenge_id': 'port_sidestep',
    'title': 'Sidestep',
    'objective': 'One of them will not be where you left it.',
    'tip': 'Every time you hit it, it is somewhere else. Listen for where it went before you fire again, '
           'because the rest are still coming.',
    'icon': 'Challenge_icon_02', 'icon_title': 'SS',
    'weapons': [{'name': 'pistol', 'ammo': '999'}, {'name': 'microsmg', 'ammo': '250'}, {'name': 'wok'}],
    'bricks': ['port_sidestep_1', 'port_sidestep_2', 'port_sidestep_3'],
    'ambient': {'ambientPlaylist': 'ambient_roman', 'gain': 0.5},
    'time_limit_star': {'reward': 250, 'objective': 180},
    'accuracy_star': {'reward': 250, 'objective': 45},
}

# ----------------------------------------------------------------------------------- Do Not Wake It
#: The arena that punishes shooting.
#:
#: A Berserk has 225 life and a `berserk` dict, and everything about it runs backwards.  In its walking state
#: the orientation is negated, so it walks *away*; `berserk_go_away` 0x100060944 sets its life to nought once
#: `disappearAfter` (15 seconds) is up, so the wave counts it as cleared and the player never fires a shot.
#: But `set_life` sends it to `transition_to_berserk` the moment it is hit and survives, and then it comes
#: back at `berserkSpeed` with whatever is left of 225 life - which at level one is thirteen seconds of
#: shooting, and it arrives long before that.
#:
#: So each wave puts the Berserks on bearings between the zombies that do have to be killed, close enough
#: that a shot thirty degrees wide might find the wrong one.  The whole arena is fire discipline, and it is
#: the only one in either chapter where the right move is sometimes to not shoot at all.
PLISTS['port_nowake_1'] = _wave(
    [('Berserk', 90, 7.0), ('WeakZombie', 70, 10.0, 1.0), ('Zombie', 110, 10.0, 5.0),
     ('WeakZombieB', 250, 10.0, 9.0), ('Zombie', 280, 10.0, 13.0),
     ('ZombieB', 30, 10.0, 17.0), ('QuietZombie', 200, 10.0, 21.0)], no_blast=True)
PLISTS['port_nowake_2'] = _wave(
    [('Berserk', 60, 7.0), ('Berserk', 240, 7.0, 8.0),
     ('Zombie', 40, 10.0, 1.0), ('WeakZombie', 80, 10.0, 3.0), ('ZombieB', 220, 10.0, 5.0),
     ('Zombie', 260, 10.0, 7.0), ('QuietZombie', 150, 10.0, 9.0), ('ZombieC', 110, 10.0, 11.0),
     ('Zombie', 300, 10.0, 13.0), ('QuietZombie', 20, 10.0, 15.0)], no_blast=True)
PLISTS['port_nowake_3'] = _wave(
    [('Berserk', 30, 6.5), ('Berserk', 150, 6.5, 6.0), ('Berserk', 270, 6.5, 12.0),
     ('Zombie', 15, 10.0, 1.0), ('WeakZombie', 45, 10.0, 2.6), ('ZombieB', 135, 10.0, 4.2),
     ('QuietZombie', 165, 10.0, 5.8), ('Zombie', 255, 10.0, 7.4), ('ZombieC', 285, 10.0, 9.0),
     ('Runner', 200, 11.0, 10.6), ('ZombieB', 100, 10.0, 12.2), ('QuietZombie', 300, 10.0, 13.8),
     ('Zombie', 60, 10.0, 15.4), ('RunnerB', 240, 11.0, 17.0)], no_blast=True)
PLISTS['port_nowake'] = {
    'challenge_id': 'port_nowake',
    'title': 'Do Not Wake It',
    'objective': 'One of the things out there is leaving on its own. It would rather you did not interrupt.',
    'tip': 'It walks away from you and it does not need killing. What it needs is to be missed, and a shot '
           'is thirty degrees wide.',
    'icon': 'Challenge_icon_02', 'icon_title': 'NW',
    'weapons': [{'name': 'pistol', 'ammo': '999'}, {'name': 'wok'}],
    'bricks': ['port_nowake_1', 'port_nowake_2', 'port_nowake_3'],
    'ambient': {'ambientPlaylist': 'ambient_roman', 'gain': 0.5},
    'time_limit_star': {'reward': 250, 'objective': 200},
    'accuracy_star': {'reward': 300, 'objective': 70},
}

# -------------------------------------------------------------------------------------------- Hydra
#: A wave that answers a kill with more of itself, and hands the player the timer.
#:
#: `spawn_after` is the original's own key - `challenge_arena1_1` uses it - and `checkSpawnAfterKill:`
#: 0x1000a20ac reads it: an enemy whose `spawn_after` names another by the key it is written under spawns
#: that many seconds after the named one **dies**.  So a few heads stand out there, each with more behind it,
#: and nothing else happens until a head is cut off.  Which means the player decides when the next ones come,
#: and the arena is really a question about pacing: kill them one at a time and the wave takes for ever
#: against the clock, kill them together and they all come back at once.
#:
#: Until 2026-09-28 each head had one brood of two, walking in from eleven units, and the tool counted every
#: brood as standing there from the first second - so it called the arena nine seconds short when it had
#: three to spare.  Measured as it plays, it was a chapter 1 arena.  So what grows back now grows back
#: closer, two seconds after the cut, and some of what grows back has heads of its own.
def _heads(tree, after: float = 2.0) -> dict:
    """A hydra, as a tree of `(kind, angle, distance, [what grows back when it dies])`.

    `spawn_after` names another enemy by the key it is written under, so the numbering `_wave` gives has to
    be worked out here: the tree is laid out depth first and each head is pointed at the one above it.  An
    enemy with a `spawn_after` and no `spawn_time` is built and then left alone by `Brick.__init__`, and
    `checkSpawnAfterKill:` 0x1000a20ac is what eventually starts its clock.
    """
    spec, above = [], []

    def lay(node, parent):
        spec.append(tuple(node[:3]))
        above.append(parent)
        me = len(spec) - 1
        for child in (node[3] if len(node) > 3 else ()):
            lay(child, me)
    for root in tree:
        lay(root, None)
    wave = _wave(spec, no_blast=True)
    keys = list(wave['Enemies'])
    for i, parent in enumerate(above):
        if parent is not None:
            one = dict(wave['Enemies'][keys[i]], spawn_after={'enemy': keys[parent], 'time': after})
            one.pop('spawn_time', None)
            wave['Enemies'][keys[i]] = one
    return wave


PLISTS['port_hydra_1'] = _heads([
    ('Zombie', 45, 9.0, [('WeakZombie', 20, 8.0), ('WeakZombieB', 70, 8.0)]),
    ('Zombie', 225, 9.0, [('WeakZombieC', 200, 8.0), ('WeakZombieD', 250, 8.0)])])
PLISTS['port_hydra_2'] = _heads([
    ('Zombie', 30, 9.0, [('Zombie', 10, 7.5, [('WeakZombie', 350, 7.0)]), ('WeakZombieB', 50, 7.5)]),
    ('Zombie', 150, 9.0, [('ZombieB', 130, 7.5, [('WeakZombieC', 110, 7.0)]), ('WeakZombieD', 170, 7.5)]),
    ('Zombie', 270, 9.0, [('Zombie', 250, 7.5), ('Runner', 290, 9.0)])])
PLISTS['port_hydra_3'] = _heads([
    ('Zombie', 20, 8.5, [('ZombieB', 0, 7.0, [('Runner', 340, 9.0)]),
                         ('Zombie', 40, 7.0, [('WeakZombieB', 60, 6.5)])]),
    ('Zombie', 110, 8.5, [('ZombieC', 90, 7.0, [('RunnerB', 70, 9.0)]),
                          ('Zombie', 130, 7.0, [('WeakZombieC', 150, 6.5)])]),
    ('Zombie', 200, 8.5, [('ZombieB', 180, 7.0, [('Runner', 160, 9.0)]), ('QuietZombie', 220, 7.0)]),
    ('Zombie', 290, 8.5, [('Zombie', 270, 7.0, [('WeakZombie', 250, 6.5)]), ('ZombieC', 310, 7.0)])])
PLISTS['port_hydra'] = {
    'challenge_id': 'port_hydra',
    'title': 'Hydra',
    'objective': 'Nothing out there is in any hurry. That part is up to you.',
    'tip': 'The arena is waiting for you, and every one you finish is an invitation. Finish them one at a '
           'time and watch the clock; finish them together and do not.',
    'icon': 'Challenge_icon_02', 'icon_title': 'HY',
    'weapons': [{'name': 'pistol', 'ammo': '999'}, {'name': 'microsmg', 'ammo': '200'}, {'name': 'wok'}],
    'bricks': ['port_hydra_1', 'port_hydra_2', 'port_hydra_3'],
    'ambient': {'ambientPlaylist': 'ambient_roman', 'gain': 0.5},
    'time_limit_star': {'reward': 300, 'objective': 150},
    'accuracy_star': {'reward': 250, 'objective': 50},
}

# ------------------------------------------------------------------------------------ The Long Walk
#: Five hundred life at a quarter of a unit a second.  A Colossus spawned twelve units out takes
#: forty-eight seconds to arrive and thirty seconds of level-one shooting to put down, so it is not a
#: question of whether it can be killed but of what else happens in the half minute it takes - and what
#: else is a crowd, walking in on the other side of the player while their back is turned.
PLISTS['port_longwalk_1'] = _wave(
    [('Colossus', 0, 12.0), ('WeakZombie', 160, 10.0, 6.0), ('Zombie', 200, 10.0, 14.0),
     ('ZombieB', 180, 10.0, 22.0)], no_blast=True)
PLISTS['port_longwalk_2'] = _wave(
    [('Colossus', 0, 12.0), ('Zombie', 150, 10.0, 5.0), ('WeakZombie', 190, 10.0, 11.0),
     ('ZombieB', 210, 10.0, 17.0), ('QuietZombie', 170, 10.0, 23.0), ('Zombie', 230, 10.0, 29.0)],
    no_blast=True)
PLISTS['port_longwalk_3'] = _wave(
    [('Colossus', 0, 12.0), ('Zombie', 140, 10.0, 4.0), ('WeakZombie', 180, 10.0, 9.0),
     ('ZombieB', 220, 10.0, 14.0), ('QuietZombie', 160, 10.0, 19.0), ('Runner', 200, 11.0, 24.0),
     ('ZombieC', 240, 10.0, 29.0), ('RunnerB', 120, 11.0, 34.0)], no_blast=True)
PLISTS['port_longwalk'] = {
    'challenge_id': 'port_longwalk',
    'title': 'The Long Walk',
    'objective': 'Something very large is on its way, and it is in no hurry at all.',
    'tip': 'It will take everything you have got for half a minute. Decide whether it gets that half '
           'minute now or later, because the rest are coming from behind you.',
    'icon': 'Challenge_icon_02', 'icon_title': 'LW',
    'weapons': [{'name': 'pistol', 'ammo': '999'}, {'name': 'microsmg', 'ammo': '400'}, {'name': 'wok'}],
    'bricks': ['port_longwalk_1', 'port_longwalk_2', 'port_longwalk_3'],
    'ambient': {'ambientPlaylist': 'ambient_roman', 'gain': 0.5},
    'time_limit_star': {'reward': 300, 'objective': 220},
    'accuracy_star': {'reward': 300, 'objective': 45},
}

# ----------------------------------------------------------------------------------------- Big Game
#: The first arena of either chapter that wants a gun the player has to buy (user request).  A Hunting Rifle
#: is 8500 coins and does 15 a shot at level one against the revolver's 10, and this asks for it by name:
#: `hasWeaponForChallengeWithName:` 0x10001f868 is what the overview checks, and a player who has not bought
#: one is told to go to the armory instead of being let in.  Everything in here is something the revolver was
#: never going to be enough for - a Colossus, the Hulks, and two Berserks that had better be left where they
#: are - and by what the tool measures it is the hardest thing in either chapter.
PLISTS['port_biggame_1'] = _wave(
    [('Hulk', 60, 12.0), ('HulkB', 300, 12.0, 8.0), ('Berserk', 180, 7.0, 2.0),
     ('Zombie', 120, 10.0, 14.0), ('ZombieB', 240, 10.0, 20.0)], no_blast=True)
PLISTS['port_biggame_2'] = _wave(
    [('Colossus', 90, 12.0), ('Hulk', 30, 12.0, 12.0), ('HulkB', 150, 12.0, 24.0),
     ('Berserk', 270, 7.0, 3.0), ('Runner', 210, 11.0, 34.0), ('Zombie', 330, 10.0, 40.0)],
    no_blast=True)
PLISTS['port_biggame_3'] = _wave(
    [('Colossus', 0, 12.0), ('Hulk', 80, 12.0, 10.0), ('HulkB', 280, 12.0, 20.0),
     ('Shield', 160, 12.0, 28.0), ('Berserk', 40, 6.5, 2.0), ('Berserk', 320, 6.5, 9.0),
     ('Runner', 200, 11.0, 34.0), ('RunnerB', 120, 11.0, 39.0), ('Chainsaw', 240, 11.0, 40.0),
     ('Chainsaw', 60, 11.0, 45.0), ('Runner', 150, 11.0, 50.0)], no_blast=True)
PLISTS['port_biggame'] = {
    'challenge_id': 'port_biggame',
    'title': 'Big Game',
    'objective': 'A revolver was never going to be enough for this, and Dr. Bastard knows it.',
    'tip': 'Buy the rifle. Then work out which of them you are meant to shoot with it, because one of them '
           'is not on the list.',
    'icon': 'Challenge_icon_02', 'icon_title': 'BG',
    'weapons': [{'name': 'hunting', 'ammo': '120'}, {'name': 'pistol', 'ammo': '999'}, {'name': 'wok'}],
    'bricks': ['port_biggame_1', 'port_biggame_2', 'port_biggame_3'],
    'ambient': {'ambientPlaylist': 'ambient_roman', 'gain': 0.5},
    'time_limit_star': {'reward': 300, 'objective': 240},
    'accuracy_star': {'reward': 300, 'objective': 60},
}



# =========================================================================================== chapter 3
#: Chapter 3, harder than chapter 2 at the user's asking, and built on the last levers in the engine: the
#: storm, the modifiers that take a gun apart, the power-up a wave can hand over on cue, and the enemies that
#: circle rather than walk.
#:
#: What it cannot have is Dr. Bastard.  `Brick.init_sounds` asks the engine for a playlist named after the
#: brick (`play_list_with_name(self.name)`), and all ninety-two of those belong to their challenges, each
#: with its own folder under `game/sounds/challenges/`.  A brick of ours has no playlist and no folder, so a
#: `Sounds` entry on one would load nothing - `brickIsCleared`'s guard keeps that from hanging the wave, but
#: the line would never be heard.  Their arenas talk; ours cannot, without adding recordings to their data.

# ------------------------------------------------------------------------------------------------ Thunder
#: The storm, which is the original's own idea: `maya_2`, "A storm is coming!", whose tip says plainly that
#: it is hard to hear zombies through one.  Naming `ambient_storm` as the arena's ambient is all it takes -
#: `AmbientManager.start_with_ambient` starts the storm playlist on that name alone, and stops the random
#: scare sounds while it runs - and everything in here has to be found through it.
#:
#: So nothing in it is hard to kill.  Weak and ordinary Zombies, and the QuietZombie that is difficult to
#: place on a still night, and the noise of a jukebox and a machine on top of the weather.
PLISTS['port_thunder_1'] = _crowd(('WeakZombie', 'QuietZombie', 'Zombie'), 8, 10.0, 2.4)
PLISTS['port_thunder_1']['PasserBy'] = {
    'Jukebox': {'spawn_angle': 200.0, 'spawn_distance': 9.0, 'spawn_time': 2.0}}
PLISTS['port_thunder_2'] = _crowd(('QuietZombie', 'WeakZombie', 'ZombieB', 'QuietZombie'), 12, 10.0, 2.0)
PLISTS['port_thunder_2']['PasserBy'] = {
    'Jukebox': {'spawn_angle': 60.0, 'spawn_distance': 9.0, 'spawn_time': 2.0},
    'Machine': {'spawn_angle': 280.0, 'spawn_distance': 8.0, 'spawn_time': 5.0}}
PLISTS['port_thunder_3'] = _crowd(('QuietZombie', 'ZombieB', 'QuietZombie', 'WeakZombieB', 'ZombieC'),
                                  18, 10.0, 1.5)
PLISTS['port_thunder_3']['PasserBy'] = {
    'Jukebox': {'spawn_angle': 140.0, 'spawn_distance': 9.0, 'spawn_time': 2.0},
    'Machine': {'spawn_angle': 320.0, 'spawn_distance': 8.0, 'spawn_time': 4.0},
    'Cow': {'spawn_angle': 30.0, 'spawn_distance': 11.0, 'spawn_time': 7.0}}
PLISTS['port_thunder'] = {
    'challenge_id': 'port_thunder',
    'title': 'Thunder',
    'objective': 'Nothing out here is dangerous. Good luck finding any of it.',
    'tip': 'Wait for the weather. It is not constant, and neither are they.',
    'icon': 'Challenge_icon_02', 'icon_title': 'TH',
    'weapons': [{'name': 'pistol', 'ammo': '999'}, {'name': 'microsmg', 'ammo': '250'}, {'name': 'wok'}],
    'bricks': ['port_thunder_1', 'port_thunder_2', 'port_thunder_3'],
    'ambient': {'ambientPlaylist': 'ambient_storm', 'gain': 0.5},
    'time_limit_star': {'reward': 300, 'objective': 200},
    'accuracy_star': {'reward': 350, 'objective': 60},
}

# --------------------------------------------------------------------------------------------- Iron Sights
#: A narrower cone and nothing forgiven.  `spread_modifier` is five degrees a card and `Weapon.__init__` adds
#: it to the weapon's own, so `narrowedSpread` twice takes the revolver from thirty degrees to twenty - a
#: third less arena to find a zombie in by ear.  `noCritical` takes the doubling away on top, so a shot lined
#: up perfectly is worth no more than one that merely landed.
#:
#: And the things in it move when hit: Dodges strafe 3.5 units every time, which in a twenty degree cone is
#: further outside it than in a thirty.  (Every strafe also loses them ground, which the tool did not count
#: until 2026-09-28; counted, this was a chapter 2 arena, and it has a walker more in each wave now and a
#: tighter last one.)
PLISTS['port_ironsights_1'] = _wave(
    [('Dodge', 40, 12.0), ('Zombie', 200, 10.0, 3.0), ('WeakZombie', 300, 10.0, 7.0),
     ('ZombieB', 120, 10.0, 11.0), ('QuietZombie', 250, 10.0, 15.0)], no_blast=True)
PLISTS['port_ironsights_2'] = _wave(
    [('Dodge', 20, 12.0), ('DodgeB', 190, 12.0, 7.0), ('Zombie', 90, 10.0, 2.0),
     ('QuietZombie', 280, 10.0, 5.0), ('ZombieB', 140, 10.0, 9.0), ('WeakZombieB', 330, 10.0, 13.0),
     ('Zombie', 240, 10.0, 17.0)], no_blast=True)
PLISTS['port_ironsights_3'] = _wave(
    [('Dodge', 30, 12.0), ('DodgeB', 150, 12.0, 10.0),
     ('QuietZombie', 80, 10.0, 2.0), ('ZombieB', 200, 10.0, 5.0), ('Runner', 320, 11.0, 9.0),
     ('QuietZombie', 110, 10.0, 12.0), ('ZombieC', 280, 10.0, 15.0),
     ('ZombieB', 60, 10.0, 17.5), ('QuietZombie', 240, 10.0, 20.0), ('Zombie', 170, 10.0, 22.5)],
    no_blast=True)
PLISTS['port_ironsights'] = {
    'challenge_id': 'port_ironsights',
    'title': 'Iron Sights',
    'objective': 'Your aim has to be better than it has ever needed to be.',
    'tip': 'There is less room for error in every shot, and no reward for a perfect one. Take the time to '
           'be right.',
    'icon': 'Challenge_icon_02', 'icon_title': 'IS',
    'weapons': [{'name': 'pistol', 'ammo': '999'}, {'name': 'wok'}],
    'bricks': ['port_ironsights_1', 'port_ironsights_2', 'port_ironsights_3'],
    'ambient': {'ambientPlaylist': 'ambient_ruins', 'gain': 0.5},
    'Modifiers': ['narrowedSpread', 'narrowedSpread', 'noCritical'],
    'time_limit_star': {'reward': 300, 'objective': 200},
    'accuracy_star': {'reward': 350, 'objective': 65},
}

# ---------------------------------------------------------------------------------------------------- Rust
#: The gun itself is the arena.  `rustyWeapons` gives every shot a chance of jamming; `lessBullets` twice
#: takes a tenth off the cylinder each time, six rounds down to four; and `slowerReloadTime` twice makes the
#: 1.8 second reload two and a half.  Between them the revolver's sustained damage falls from 16.7 a second
#: to 9.5, which is a different weapon.
#:
#: So the crowd is an ordinary crowd and the answer is entirely in when to reload.
PLISTS['port_rust_1'] = _crowd(('WeakZombie', 'Zombie', 'WeakZombieB'), 8, 10.0, 2.6)
PLISTS['port_rust_2'] = _crowd(('Zombie', 'WeakZombie', 'ZombieB', 'QuietZombie'), 11, 10.0, 2.2)
PLISTS['port_rust_3'] = _crowd(('Zombie', 'ZombieB', 'WeakZombie', 'QuietZombie', 'ZombieC'), 15, 10.0, 1.7)
PLISTS['port_rust'] = {
    'challenge_id': 'port_rust',
    'title': 'Rust',
    'objective': 'The crowd is the easy part. What Dr. Bastard has done to your revolver is not.',
    'tip': 'It holds less, it takes longer to fill, and sometimes it does nothing at all. Reload on your '
           'terms or it will happen on theirs.',
    'icon': 'Challenge_icon_02', 'icon_title': 'RU',
    'weapons': [{'name': 'pistol', 'ammo': '999'}, {'name': 'wok'}],
    'bricks': ['port_rust_1', 'port_rust_2', 'port_rust_3'],
    'ambient': {'ambientPlaylist': 'ambient_ghosttown', 'gain': 0.5},
    'Modifiers': ['rustyWeapons', 'lessBullets', 'lessBullets',
                  'slowerReloadTime', 'slowerReloadTime'],
    'time_limit_star': {'reward': 300, 'objective': 210},
    'accuracy_star': {'reward': 350, 'objective': 55},
}

# ------------------------------------------------------------------------------------------------ Carousel
#: The ones that do not come straight at you.  A Chainsaw carries `circling` {circlingFactor 0.5} and a Clown
#: {circlingFactor 0.9}, and state 2 mixes that fraction of a sideways heading into its approach - so a Clown
#: at 0.9 is very nearly orbiting, and closes so slowly that the arena is long rather than sharp.  Which is
#: the point: they are never where the ear last put them, and there is no moment when they are not moving.
#:
#: Played with `fasterEnemies` twice, because a circling enemy that is not quick is barely an enemy at all.
PLISTS['port_carousel_1'] = _crowd(('Chainsaw', 'Clown', 'Chainsaw'), 7, 10.0, 2.6)
PLISTS['port_carousel_2'] = _crowd(('Chainsaw', 'Clown', 'Chainsaw', 'Clown'), 10, 10.0, 2.2)
PLISTS['port_carousel_3'] = _crowd(('Chainsaw', 'Clown', 'Chainsaw', 'Runner', 'Clown'), 16, 10.0, 1.6)
PLISTS['port_carousel'] = {
    'challenge_id': 'port_carousel',
    'title': 'Carousel',
    'objective': 'They are not walking towards you. They are going around you.',
    'tip': 'Where it was is not where it is. Lead it, or wait for it to come round.',
    'icon': 'Challenge_icon_02', 'icon_title': 'CR',
    'weapons': [{'name': 'pistol', 'ammo': '999'}, {'name': 'microsmg', 'ammo': '350'}, {'name': 'wok'}],
    'bricks': ['port_carousel_1', 'port_carousel_2', 'port_carousel_3'],
    'ambient': {'ambientPlaylist': 'ambient_ghosttown', 'gain': 0.5},
    'Modifiers': ['fasterEnemies', 'fasterEnemies'],
    'time_limit_star': {'reward': 350, 'objective': 220},
    'accuracy_star': {'reward': 350, 'objective': 40},
}

# ------------------------------------------------------------------------------------------------ The Drop
#: A wave with more in it than the gun can answer, and one thing coming that can.
#:
#: `PowerUp` is the original's own key and `Brick.update` reads it: at `force_spawn_time` it calls
#: `forceToPopPowerUpContainerWithType:` 0x1000c7b68, which puts a PowerUpContainer on a random bearing five
#: units out with one life on it.  It has to be **found and shot** to be collected, in the middle of
#: everything else, and it is the only reason the last wave can be finished at all.
#:
#: The rounds are counted to make that true: 90 of them against nearly a thousand of life.
def _drop(kinds, count: int, distance: float, every: float, at: float, kind: str) -> dict:
    wave = _crowd(kinds, count, distance, every)
    wave['PowerUp'] = {'force_spawn_time': at, 'type': kind}
    return wave


PLISTS['port_drop_1'] = _drop(('Zombie', 'WeakZombie', 'ZombieB'), 7, 10.0, 3.0, 12.0, 'minigun')
PLISTS['port_drop_2'] = _drop(('Zombie', 'ZombieB', 'Runner', 'QuietZombie'), 12, 10.0, 2.2, 14.0, 'tesla')
PLISTS['port_drop_3'] = _drop(('Zombie', 'Hulk', 'ZombieB', 'Runner', 'HulkB'), 14, 10.0, 1.9, 16.0,
                              'minigun')
PLISTS['port_drop'] = {
    'challenge_id': 'port_drop',
    'title': 'The Drop',
    'objective': 'Ninety rounds against all of that. Something else is on its way.',
    'tip': 'Do not spend everything before it arrives, and do not miss it when it does. It has one life and '
           'it will not come to you.',
    'icon': 'Challenge_icon_02', 'icon_title': 'DR',
    'weapons': [{'name': 'pistol', 'ammo': '90'}, {'name': 'wok'}],
    'bricks': ['port_drop_1', 'port_drop_2', 'port_drop_3'],
    'ambient': {'ambientPlaylist': 'ambient_ruins', 'gain': 0.5},
    'time_limit_star': {'reward': 350, 'objective': 230},
    'accuracy_star': {'reward': 400, 'objective': 60},
}

# -------------------------------------------------------------------------------------------- The Last Word
#: Everything, in a storm, with the zombies a fifth tougher than they have ever been.
#:
#: Two Colossus at 500 life each, Hulks, the Riot Gear Zombie, Berserks that had better be left alone, a
#: Dodge that will not stay found, and Clowns circling - all of it through `ambient_storm`, and all of it
#: with `strongerEnemies`.  It closes chapter 3 and is meant to be the hardest thing in it; the rifle is here
#: because nothing else would be honest.
#:
#: Counting what a hit costs a Dodge (2026-09-28) took six seconds off it and left Carousel harder, so the
#: last wave's Hulks and the four after them come in sooner, and a second Chainsaw closes it.
PLISTS['port_last_1'] = _wave(
    [('Colossus', 0, 12.0), ('Hulk', 120, 12.0, 20.0), ('Berserk', 240, 7.0, 3.0),
     ('Dodge', 300, 12.0, 34.0), ('Clown', 60, 11.0, 44.0), ('Zombie', 180, 10.0, 52.0)], no_blast=True)
PLISTS['port_last_2'] = _wave(
    [('Colossus', 90, 12.0), ('HulkB', 210, 12.0, 22.0), ('Shield', 330, 12.0, 38.0),
     ('Berserk', 30, 7.0, 3.0), ('DodgeB', 150, 12.0, 50.0), ('Chainsaw', 270, 11.0, 60.0),
     ('Clown', 60, 11.0, 68.0)], no_blast=True)
PLISTS['port_last_3'] = _wave(
    [('Colossus', 0, 12.0), ('Colossus', 180, 12.0, 20.0), ('Hulk', 90, 12.0, 34.0),
     ('HulkB', 270, 12.0, 46.0), ('Berserk', 45, 6.5, 3.0), ('Berserk', 315, 6.5, 10.0),
     ('Dodge', 135, 12.0, 60.0), ('Clown', 225, 11.0, 68.0), ('Chainsaw', 300, 11.0, 76.0),
     ('Runner', 60, 11.0, 80.0), ('Chainsaw', 120, 11.0, 84.0)], no_blast=True)
PLISTS['port_last'] = {
    'challenge_id': 'port_last',
    'title': 'The Last Word',
    'objective': 'All of it, in weather, and none of it is the size it was.',
    'tip': 'Two of them will take half a minute each and one of them will take nothing at all if you leave '
           'it be. Choose in that order.',
    'icon': 'Challenge_icon_02', 'icon_title': 'LD',
    'weapons': [{'name': 'hunting', 'ammo': '220'}, {'name': 'pistol', 'ammo': '999'},
                {'name': 'wok'}],
    'bricks': ['port_last_1', 'port_last_2', 'port_last_3'],
    'ambient': {'ambientPlaylist': 'ambient_storm', 'gain': 0.5},
    'Modifiers': ['strongerEnemies'],
    'time_limit_star': {'reward': 400, 'objective': 300},
    'accuracy_star': {'reward': 400, 'objective': 65},
}


# =========================================================================================== chapter 4
#: Chapter 4, the armory (user request): every arena is fought with a weapon no arena before it used, and is
#: built against what that weapon is bad at.  Harder than chapter 3 again, by the one measure the chapters
#: are ordered on.
#:
#: Three of them have to be bought - the Sawn-off, the Grenade Launcher and the Claymore - and
#: `hasWeaponForChallengeWithName:` 0x10001f868 sends a player without one to the armory, as it does for the
#: original's own challenges.  The Sawn-off and the Hunting Rifle are ones the original's own worlds make a
#: player buy anyway (Roman Theater, City Crossroad); the Grenade Launcher and the Claymore are the chapter's
#: price.  The Bazooka, the Police Shotgun, the Machine Gun and the Sonic Cannon are not used: between them
#: they cost more than eighty thousand coins and a hundred diamonds, which is not a challenge but a bill.
#:
#: These are crowds, and crowds of a size the original never sent - its biggest wave is fifteen, and some of
#: these are forty.  Measured in the real engine on 2026-09-28 (a scratch test, listener silenced), the
#: busiest of them holds 84 voices at once against the 255 the device is asked for, so none of them is ever
#: silent for want of one.
#:
#: What makes a crowd weapon's arena hard is not how many there are but how they arrive, and three shapes
#: carry it: a **pack** walks in together and is one shot to a gun that hits a crowd; an **escort** is a pack
#: with something in the middle of it a bullet should not find; and a **pair** is two packs at once from
#: opposite sides, which no shotgun can face together.
def _pack(kinds, bearing: float, distance: float, at: float, spread: float = 6.0, depth: float = 0.7):
    """A few walking together: bearings `spread` degrees apart, every other one a little behind, and a
    third of a second between them, so that each can still be heard arriving."""
    n = len(kinds)
    return [(k, bearing + (i - (n - 1) / 2.0) * spread, distance + (i % 2) * depth, at + 0.3 * i)
            for i, k in enumerate(kinds)]


def _escort(kinds, special: str, bearing: float, distance: float, at: float):
    """A pack with `special` in the middle of it, half a unit ahead: the one a shot aimed at the pack's
    sound finds first."""
    pack = _pack(kinds, bearing, distance, at, spread=8.0)
    return pack[:len(pack) // 2] + [(special, bearing, distance - 0.5, at)] + pack[len(pack) // 2:]


def _pair(near, far, bearing: float, at: float, runners: bool = False):
    """Two packs at once, from opposite sides."""
    spread, distance = (5.0, 11.0) if runners else (6.0, 10.0)
    return (_pack(near, bearing, distance, at, spread=spread)
            + _pack(far, bearing + 180.0, distance, at + 0.3, spread=spread))


def _turned(k: int):
    """SCATTER, starting somewhere else in it, so two waves built from it do not open on the same bearing."""
    return SCATTER[k:] + SCATTER[:k]


_Z4 = ('Zombie', 'ZombieB', 'ZombieC', 'Zombie')
_Z4B = ('ZombieB', 'Zombie', 'ZombieC', 'QuietZombie')
_R3 = ('Runner', 'RunnerB', 'RunnerC')
_R4 = ('Runner', 'RunnerB', 'RunnerC', 'Runner')

# -------------------------------------------------------------------------------------------- Point Blank
#: Two shells, a hundred and twenty degrees of spread, and damage that is almost all distance.  The Sawn-off
#: has `dispersal` 1, so `hit_by_weapon` 0x100060b30 scales nearly all of its 30 by `1 - d^2 / 121`: 5 at ten
#: units, 21 at six, 28 at three.  Fired at a pack as it arrives it is wasted; fired at a pack that has been
#: let in to arm's length it takes the whole of it, and every one beside it in a cone that wide.  So the
#: arena is the wait, and it is packs all the way down - with Runners, which leave very little of one, and
#: Hulks, which need four shells at the best distance there is.
PLISTS['port_pointblank_1'] = _wave(
    _pack(('Zombie', 'WeakZombie', 'ZombieB'), 0, 10.0, 0.0)
    + _pack(('WeakZombieB', 'Zombie', 'ZombieC', 'Zombie'), 130, 10.0, 5.0)
    + _pack(('Zombie', 'ZombieB', 'WeakZombieC'), 250, 10.0, 10.0)
    + _pack(('ZombieC', 'Zombie', 'ZombieB', 'WeakZombie'), 70, 10.0, 15.0), no_blast=True)
PLISTS['port_pointblank_2'] = _wave(
    _pack(('Zombie', 'ZombieB', 'ZombieC', 'WeakZombie'), 40, 10.0, 0.0)
    + _pack(_R3, 200, 11.0, 4.0, spread=5.0)
    + _pack(_Z4B, 300, 10.0, 7.0)
    + _pack(('Zombie', 'ZombieC', 'ZombieB', 'Zombie'), 120, 10.0, 11.0)
    + _pack(('Runner', 'RunnerB'), 330, 11.0, 14.0, spread=5.0)
    + _pack(('QuietZombie', 'Zombie', 'ZombieB', 'QuietZombie'), 170, 10.0, 17.0), no_blast=True)
PLISTS['port_pointblank_3'] = _wave(
    _pack(_Z4, 10, 10.0, 0.0) + _pack(_Z4B, 190, 10.0, 0.5)
    + _pack(_R3, 100, 11.0, 4.0, spread=5.0) + _pack(_R3, 280, 11.0, 4.5, spread=5.0)
    + _pack(('Hulk', 'HulkB'), 330, 10.0, 7.0)
    + _pack(('Zombie', 'ZombieC', 'ZombieB', 'Zombie'), 60, 10.0, 9.0)
    + _pack(('Zombie', 'ZombieC', 'ZombieB', 'QuietZombie'), 240, 10.0, 9.5)
    + _pack(_R3, 150, 11.0, 12.0, spread=5.0)
    + _pack(('Hulk', 'HulkB'), 30, 10.0, 14.0)
    + _pack(_Z4B, 210, 10.0, 15.0) + _pack(_Z4, 120, 10.0, 17.0)
    + _pack(_R3, 300, 11.0, 18.0, spread=5.0), no_blast=True)
PLISTS['port_pointblank'] = {
    'challenge_id': 'port_pointblank',
    'title': 'Point Blank',
    'objective': 'Sixty shells, and far more than sixty of them. Every shell will have to count for several.',
    'tip': 'The closer they are, the more each shell is worth. Find out how close you can bear to let them '
           'come.',
    'icon': 'Challenge_icon_02', 'icon_title': 'PB',
    'weapons': [{'name': 'sawnoff', 'ammo': '60'}, {'name': 'wok'}],
    'bricks': ['port_pointblank_1', 'port_pointblank_2', 'port_pointblank_3'],
    'ambient': {'ambientPlaylist': 'ambient_ruins', 'gain': 0.5},
    'time_limit_star': {'reward': 400, 'objective': 190},
    'accuracy_star': {'reward': 400, 'objective': 70},
}

# -------------------------------------------------------------------------------------------- One Swing
#: The Claymore: 70 a swing, which is anything but a Hulk in one, and two and a half seconds between swings.
#: And for those seconds nothing else can be used either - `isWeaponReadyToShoot` 0x1000aa350 answers no
#: while the melee weapon is mid-swing, so the six rounds in the revolver wait for it too.  The arena is
#: nothing but arrivals, one after another from bearings all round, closer together each wave, until two of
#: them come inside the same two and a half seconds.
PLISTS['port_oneswing_1'] = _crowd(('Zombie', 'WeakZombie', 'ZombieB', 'Runner'), 8, 9.0, 3.5)
PLISTS['port_oneswing_2'] = _crowd(('Zombie', 'Runner', 'ZombieB', 'QuietZombie', 'Chainsaw'), 12, 9.0, 2.9,
                                   bearings=_turned(3))
PLISTS['port_oneswing_3'] = _crowd(('Zombie', 'Runner', 'Hulk', 'Chainsaw', 'ZombieB', 'RunnerB', 'Clown',
                                    'QuietZombie'), 19, 9.0, 2.4, bearings=_turned(7))
#: The second Runner of each group walks in three and a half seconds after its place in the crowd (user
#: request, 2026-09-29).  A Hulk's arrival roar is one of two recordings, 3.7 or 5.7 seconds, and it does not
#: walk until the roar ends, so it came into reach anywhere in the two seconds the Runner behind it was
#: arriving in, with the Chainsaw a second and a half after: three inside one swing of the Claymore, won or
#: lost on which roar was played.  Later by 3.5, the Runner comes after the Chainsaw rather than with it
#: (2 seconds later puts it on the Chainsaw instead).  Played out a thousand times with the game's own
#: movement, a player a second slow on every enemy never lost wave 3 for it, and had under a second to spare.
for _key, _one in PLISTS['port_oneswing_3']['Enemies'].items():
    if _key.startswith('RunnerB'):
        _one['spawn_time'] = round(_one['spawn_time'] + 3.5, 2)
PLISTS['port_oneswing'] = {
    'challenge_id': 'port_oneswing',
    'title': 'One Swing',
    'objective': 'One blade, one swing at a time, and six rounds for the moment that is not enough.',
    'tip': 'After every swing there is a long moment when you can do nothing at all. Listen for who will '
           'arrive in it.',
    'icon': 'Challenge_icon_02', 'icon_title': 'OS',
    'weapons': [{'name': 'pistol', 'ammo': '6'}, {'name': 'claymore'}],
    'bricks': ['port_oneswing_1', 'port_oneswing_2', 'port_oneswing_3'],
    'ambient': {'ambientPlaylist': 'ambient_roman', 'gain': 0.5},
    'time_limit_star': {'reward': 400, 'objective': 240},
    'accuracy_star': {'reward': 450, 'objective': 50},
}

# ------------------------------------------------------------------------------------------------- Fuse
#: The Grenade Launcher: 45 into whatever it lands on and 22.5 into everything else inside five units, which
#: is a pack in two.  Two things make it an arena rather than a massacre, and both are the original's own.
#: `targetEnemiForExplosiveWeapon:` 0x1000c57b8 aims the grenade at the **nearest** thing in front of the
#: player, not the one they meant, and a blast inside five units rings the ears like any other.  So every
#: pack here walks in behind something that got there first, a little to one side of it - close enough to be
#: in front when the pack is, and near enough that a grenade meant for the pack lands at the player's feet.
#:
#: The one that gets there first is an ordinary Zombie (user request, 2026-09-29).  They were Quiet Zombies,
#: whose walking recordings are 25 dB under a Zombie's (-46 against -21), a whisper beside a crowd - so the
#: thing stealing the grenade could not be heard, and the arena could not be played by listening for it.
#: The Quiet Zombies inside the crowds are kept: they die with the crowd.
PLISTS['port_fuse_1'] = _wave(
    _pack(('WeakZombie', 'Zombie', 'WeakZombieB', 'ZombieB'), 20, 11.0, 0.0)
    + _pack(('Zombie', 'WeakZombieC', 'ZombieC', 'WeakZombie'), 150, 11.0, 5.0)
    + _pack(('ZombieB', 'Zombie', 'WeakZombieB', 'ZombieC'), 270, 11.0, 10.0)
    + [('Zombie', 90, 9.0, 14.0)], no_blast=True)
#: The crowds are weak ones round an ordinary Zombie (user request, 2026-09-29: "too many, and the weapon is
#: not strong enough for that").  A blast puts 30 into everything within five units and a WeakZombie has
#: 20, and the Zombie walks in the middle half a unit ahead, so it is always the nearest - where the grenade
#: goes - and takes the whole of the blast, up to 60.  One grenade on target is a crowd; the one that gets
#: there first is still the arena.
_W4 = ('WeakZombie', 'WeakZombieB', 'WeakZombieC', 'WeakZombie')
PLISTS['port_fuse_2'] = _wave(
    [('WeakZombieB', 60, 7.0, 0.0)] + _escort(('WeakZombie', 'WeakZombieB', 'WeakZombieC'), 'Zombie', 40, 11.0, 1.0)
    + [('WeakZombieC', 220, 7.0, 3.0)] + _escort(('WeakZombieB', 'WeakZombie', 'WeakZombieC'), 'ZombieB', 200, 11.0, 4.0)
    + _pack(_R3, 320, 11.0, 7.0, spread=5.0)
    + [('WeakZombieB', 110, 7.0, 8.0)] + _escort(('WeakZombieC', 'WeakZombie', 'WeakZombieB'), 'ZombieC', 130, 11.0, 9.0)
    + _escort(('WeakZombie', 'WeakZombieC', 'WeakZombieB'), 'Zombie', 280, 11.0, 12.0), no_blast=True)
PLISTS['port_fuse_3'] = _wave(
    [('WeakZombieB', 30, 7.0, 0.0)] + _escort(_W4, 'Zombie', 10, 11.0, 1.0)
    + _pack(('Hulk', 'HulkB'), 230, 11.0, 3.0)
    + _pack(_R3, 120, 11.0, 5.0, spread=5.0)
    + [('WeakZombieC', 160, 7.0, 6.0)] + _escort(('WeakZombieB', 'WeakZombieC', 'WeakZombie'), 'ZombieB', 180, 11.0, 7.0)
    + _escort(('WeakZombieC', 'WeakZombie', 'WeakZombieB'), 'Zombie', 300, 11.0, 9.0)
    + [('Runner', 330, 9.0, 10.0)]
    + [('WeakZombieB', 270, 7.0, 13.0)]
    + _escort(('WeakZombieB', 'WeakZombie', 'WeakZombieC', 'WeakZombieB'), 'ZombieC', 210, 11.0, 15.0), no_blast=True)
PLISTS['port_fuse'] = {
    'challenge_id': 'port_fuse',
    'title': 'Fuse',
    'objective': 'Forty-five grenades, and a crowd for every few of them. Something always gets there first.',
    'tip': 'A grenade goes to whatever is nearest in front of you, not to what you meant, and it is loud '
           'wherever it lands. The near one is not worth a grenade.',
    'icon': 'Challenge_icon_02', 'icon_title': 'FU',
    'weapons': [{'name': 'grenade', 'ammo': '45'}, {'name': 'pistol', 'ammo': '999'}, {'name': 'wok'}],
    'bricks': ['port_fuse_1', 'port_fuse_2', 'port_fuse_3'],
    'ambient': {'ambientPlaylist': 'ambient_ghosttown', 'gain': 0.5},
    'time_limit_star': {'reward': 400, 'objective': 200},
    # 70, not 80 (user request, 2026-09-29): played well, the player reached 62, so this is a reach and not
    # a wall.  A wok swing and a grenade count as shots as a revolver's does (`update_melee_weapons`, and
    # the explosion's UPDATE_WEAPON_DATA), and they seldom miss, so it is won by taking the near ones with
    # the wok and keeping the revolver for when there is no time.
    'accuracy_star': {'reward': 450, 'objective': 70},
}

# ------------------------------------------------------------------------------------------- Collateral
#: What a blast does not do.  `hit_by_explosion` 0x100061284 takes the life off and nothing else: it does not
#: send a Dodge sideways and it does not wake a Berserk, both of which are `hit_by_weapon`'s doing (0x100060b30),
#: and it never asks whether a Riot Gear Zombie's shield is up - though the hit sound it schedules raises a
#: walking one's shield a moment later, as a bullet's would, which stops the next bullet and not the next
#: blast.  A Berserk woken is 225 life charging, a Dodge shot steps aside, a shield raised is a wall - so the
#: grenades are the way through.
#:
#: Rebuilt so that each of the three is somewhere it can really be (user request, 2026-09-29: "too many, and
#: does it make sense").  The first draft had every one of them escorted in the middle of a crowd, and two of
#: the three cannot stay there: a Berserk left alone walks *away* (state 2 of `update:` heads along
#: -orientation) and leaves after 15 seconds, and a Dodge at 0.9 outruns a crowd at 0.5 - and some of the
#: crowds were Runners, the fastest thing in the arena, round a Berserk walking the other way.  Now:
#:
#: * a Berserk rests seven units out on a crowd's way in (`_resting`), and the crowd walks past it, crossing
#:   about eight units out.  A revolver aimed at the crowd's sound can find the Berserk; a grenade cannot
#:   wake it, and one landing on it still takes the crowd, four units behind, with its flat thirty.  It never
#:   has to be killed: left alone, it goes.
#: * a Shield walks in the middle of its crowd, at its pace, half a unit ahead (`_escort`): the first
#:   grenade takes the crowd and two more the Shield, whichever of them the first one lands on.
#: * a Dodge comes on its own, or two together: grenaded, it does not step aside.
#:
#: The crowds are weak ones (20 of life), so one blast of thirty takes a crowd, as in Fuse.  Runners come in
#: a small pack of their own, with nothing in it to disturb.  The last wave went from seven crowds and 38
#: enemies to five groups and 27.
_WEAK4 = ('WeakZombie', 'WeakZombieB', 'WeakZombieC', 'WeakZombie')


def _resting(kinds, bearing: float, distance: float, at: float) -> list:
    """A crowd walking in past a Berserk resting on its way, seven units out, there a second before it."""
    return [('Berserk', bearing, 7.0, max(0.0, at - 1.0))] + _pack(kinds, bearing, distance, at, spread=8.0)


PLISTS['port_collateral_1'] = _wave(
    _resting(_WEAK4, 30, 10.0, 1.0)
    + _resting(('WeakZombieB', 'WeakZombieC', 'WeakZombie', 'WeakZombieB'), 170, 10.0, 8.0)
    + _resting(('WeakZombieC', 'WeakZombie', 'WeakZombieB', 'WeakZombieC'), 290, 10.0, 15.0), no_blast=True)
PLISTS['port_collateral_2'] = _wave(
    _escort(('WeakZombie', 'WeakZombieB', 'WeakZombieC'), 'Shield', 60, 10.0, 0.0)
    + _resting(('WeakZombieB', 'WeakZombie', 'WeakZombieC', 'WeakZombie'), 200, 10.0, 4.0)
    + [('Zombie', 130, 10.0, 6.0), ('Dodge', 320, 11.0, 7.0)]
    + _pack(_R3, 100, 11.0, 11.0, spread=5.0)
    + [('ZombieB', 250, 10.0, 12.0)], no_blast=True)
PLISTS['port_collateral_3'] = _wave(
    _escort(_WEAK4, 'Shield', 0, 10.0, 0.0)
    + _resting(('WeakZombieB', 'WeakZombieC', 'WeakZombie', 'WeakZombieB'), 120, 10.0, 2.0)
    + [('Dodge', 235, 11.0, 5.0), ('DodgeB', 245, 11.0, 5.3), ('Zombie', 330, 10.0, 6.0)]
    + _escort(('WeakZombieC', 'WeakZombie', 'WeakZombieB'), 'Shield', 180, 10.0, 10.0)
    + _pack(_R3, 60, 11.0, 12.0, spread=5.0)
    + [('ZombieC', 90, 10.0, 13.0)]
    + _resting(('WeakZombie', 'WeakZombieC', 'WeakZombieB', 'WeakZombie'), 270, 10.0, 16.0), no_blast=True)
PLISTS['port_collateral'] = {
    'challenge_id': 'port_collateral',
    'title': 'Collateral',
    'objective': 'Every crowd out here has something in the middle of it, and none of them should be '
                 'disturbed.',
    'tip': 'Some of them take a bullet personally. Nothing out here seems to take a blast that way.',
    'icon': 'Challenge_icon_02', 'icon_title': 'CL',
    'weapons': [{'name': 'grenade', 'ammo': '50'}, {'name': 'pistol', 'ammo': '999'}, {'name': 'wok'}],
    'bricks': ['port_collateral_1', 'port_collateral_2', 'port_collateral_3'],
    'ambient': {'ambientPlaylist': 'ambient_ruins', 'gain': 0.5},
    'time_limit_star': {'reward': 450, 'objective': 210},
    'accuracy_star': {'reward': 450, 'objective': 75},
}

# -------------------------------------------------------------------------------------------- Crossfire
#: Point Blank's shotgun, facing both ways at once.  Its cone is sixty degrees either side, which is a third
#: of the arena and never the half behind, so every pack here comes with another from the opposite side at the
#: same moment.  The Hunting Rifle is the other half of the answer: it reaches what the shotgun cannot, one at
#: a time, and forty rounds of it is not much.
#:
#: The player's choice, after three rebuilds in one afternoon (2026-09-29): this first version, with more room
#: in the one place it was lost.  `_pair` sends the far pack three tenths of a second behind the near one,
#: and for Runners that is both packs inside five units at once - two shells, a half-turn and nothing left.
#: So in the last wave the far pack of each Runner pair comes 2.3 seconds behind the near one: a shell into
#: the first, turn, a shell into the second.
PLISTS['port_crossfire_1'] = _wave(
    _pack(('Zombie', 'ZombieB', 'ZombieC'), 0, 10.0, 0.0) + _pack(('Zombie', 'ZombieC', 'ZombieB'), 180, 10.0, 0.5)
    + _pack(('ZombieB', 'Zombie', 'WeakZombie'), 90, 10.0, 10.0)
    + _pack(('ZombieC', 'Zombie', 'ZombieB'), 270, 10.0, 10.5)
    + [('Zombie', 45, 11.0, 5.0), ('ZombieB', 225, 11.0, 14.0)], no_blast=True)
PLISTS['port_crossfire_2'] = _wave(
    _pack(_Z4, 30, 10.0, 0.0) + _pack(_R3, 210, 11.0, 2.0, spread=5.0)
    + _pack(_Z4B, 120, 10.0, 8.0) + _pack(('Zombie', 'ZombieC', 'ZombieB', 'Zombie'), 300, 10.0, 8.5)
    + [('Hulk', 75, 11.0, 4.0), ('Zombie', 255, 11.0, 12.0)]
    + _pack(_R3, 345, 11.0, 15.0, spread=5.0) + _pack(('Zombie', 'ZombieB', 'ZombieC'), 165, 10.0, 15.5),
    no_blast=True)
PLISTS['port_crossfire_3'] = _wave(
    _pair(_Z4, _Z4B, 10, 0.0)
    + _pack(_R3, 100, 11.0, 4.0, spread=5.0) + _pack(_R3, 280, 11.0, 6.3, spread=5.0)
    + _pack(('Hulk', 'HulkB'), 55, 10.0, 7.0) + _pack(_Z4, 235, 10.0, 7.3)
    + _pair(_Z4B, _Z4, 150, 10.0) + [('Hulk', 330, 11.0, 11.0)]
    + _pack(_R3, 20, 11.0, 14.0, spread=5.0) + _pack(_R3, 200, 11.0, 16.3, spread=5.0)
    + _pair(_Z4, _Z4B, 70, 17.0)
    + _pack(_R3, 300, 11.0, 20.0, spread=5.0), no_blast=True)
PLISTS['port_crossfire'] = {
    'challenge_id': 'port_crossfire',
    'title': 'Crossfire',
    'objective': 'They come two crowds at a time, from opposite sides, and a shotgun only faces one way.',
    'tip': 'One side can wait a moment, as long as you choose which. What comes alone can be met further '
           'out.',
    'icon': 'Challenge_icon_02', 'icon_title': 'CF',
    'weapons': [{'name': 'sawnoff', 'ammo': '70'}, {'name': 'hunting', 'ammo': '40'}, {'name': 'wok'}],
    'bricks': ['port_crossfire_1', 'port_crossfire_2', 'port_crossfire_3'],
    'ambient': {'ambientPlaylist': 'ambient_ghosttown', 'gain': 0.5},
    'time_limit_star': {'reward': 450, 'objective': 220},
    'accuracy_star': {'reward': 450, 'objective': 70},
}

# ------------------------------------------------------------------------------------------- The Armory
#: All three of the chapter's weapons, and everything each of them was bought for: packs for the grenades
#: far out and the shotgun close in, escorts that only a blast should touch, Hulks in pairs, and the
#: Chainsaws and Clowns that come round the side for the Claymore.  The Colossus was here in the first draft
#: and came out: five hundred life is twelve direct grenades or twenty-four shells, which none of these
#: weapons is for, and an arena about choosing the right tool should not have a target that has none.
#:
#: Thinned where it was too crowded or made no sense (user request, 2026-09-29), as Collateral and Crossfire
#: were: a Berserk rested on a crowd's way in rather than being escorted by it (it walks away) - and then
#: went, below - a Dodge comes on its own (it outruns a crowd, and a pack of Runners outruns it), wave 2's
#: Runner packs from opposite sides come 2.3 seconds apart rather than half a second, wave 2 has one Hulk pair
#: and a single Hulk rather than two pairs, and wave 3 two pairs rather than three, and its opening crowds
#: are fours.
#: And again, still too many (the same day): every crowd a three, no single Hulk in wave 2, one Hulk pair
#: in wave 3, and a crowd fewer at the end of waves 2 and 3.  Measured so that no eight seconds bring more than
#: about ten enemies within five units.
_ARMORY3 = (('Zombie', 'ZombieB', 'ZombieC'), ('ZombieB', 'ZombieC', 'Zombie'), ('ZombieC', 'Zombie', 'ZombieB'),
            ('ZombieB', 'QuietZombie', 'Zombie'))
#: No Berserk (the same day): the Sawn-off hits everything sixty degrees either side of where it is aimed, and
#: in every wave something the player would shotgun - a crowd, the Hulk pair, the Dodge - came in within that
#: of a resting Berserk while it was there, and woke it.  They stay in Collateral, which has no shotgun.
#: Spaced (the same day): each group comes within five units about five seconds after the one before, and
#: the Runners, the Dodge, the Chainsaw and the Clown each come on their own, so nothing fast arrives while the
#: rest of the arena is on top of the player.  The spawn times are worked back from where each should be.
PLISTS['port_armory_1'] = _wave(
    _pack(_ARMORY3[0], 20, 11.0, 0.0)
    + [('Hulk', 110, 10.0, 4.3)]
    + _pack(_R3, 290, 11.0, 15.0, spread=5.0)
    + _pack(_ARMORY3[1], 200, 10.0, 14.5)
    + _pack(_ARMORY3[2], 150, 10.0, 19.5)
    + [('Chainsaw', 330, 10.0, 24.5)]
    + _pack(_ARMORY3[3], 70, 11.0, 29.5), no_blast=True)
PLISTS['port_armory_2'] = _wave(
    _pack(_R3, 90, 11.0, 4.0, spread=5.0) + _pack(_R3, 270, 11.0, 6.3, spread=5.0)
    + _pack(_ARMORY3[0], 0, 10.0, 5.5)
    + _pack(('Hulk', 'HulkB'), 180, 10.0, 10.3)
    + _pack(_ARMORY3[3], 225, 10.0, 16.5)
    + [('Dodge', 20, 11.0, 22.0), ('Clown', 315, 10.0, 20.0), ('Chainsaw', 135, 10.0, 25.5)]
    + _pack(_ARMORY3[1], 160, 10.0, 30.5), no_blast=True)
PLISTS['port_armory_3'] = _wave(
    _pack(_R3, 55, 11.0, 5.0, spread=5.0)
    + _pack(_ARMORY3[0], 10, 11.0, 0.0)
    + _pack(_ARMORY3[2], 190, 11.0, 5.5)
    + _pack(('Hulk', 'HulkB'), 100, 11.0, 12.3)
    + _pack(_ARMORY3[1], 235, 10.0, 17.5)
    + [('Dodge', 200, 11.0, 23.0)]
    + _escort(_ARMORY3[3], 'Shield', 325, 10.0, 26.5)
    + [('Chainsaw', 80, 10.0, 32.5), ('Clown', 260, 10.0, 26.0)]
    + _pack(_R3, 170, 11.0, 44.0, spread=5.0), no_blast=True)
PLISTS['port_armory'] = {
    'challenge_id': 'port_armory',
    'title': 'The Armory',
    'objective': 'Everything you bought for this chapter, and everything you bought it for.',
    'tip': 'Each of them is right for something out here and wrong for the rest. There is no time to find '
           'out which by trying.',
    'icon': 'Challenge_icon_02', 'icon_title': 'AR',
    'weapons': [{'name': 'grenade', 'ammo': '25'}, {'name': 'sawnoff', 'ammo': '70'}, {'name': 'claymore'}],
    'bricks': ['port_armory_1', 'port_armory_2', 'port_armory_3'],
    'ambient': {'ambientPlaylist': 'ambient_roman', 'gain': 0.5},
    'time_limit_star': {'reward': 500, 'objective': 280},
    'accuracy_star': {'reward': 500, 'objective': 70},
}


# ================================================================================== the second round
#: Arenas added on 2026-09-30 to bring each chapter to seven to ten (user request), and to put every
#: weapon, enemy and power-up the game has to use somewhere; where each is played is `CHAPTERS`' business.

# ---------------------------------------------------------------------------------------------- Busker
#: The Banjo, which at 1500 coins is the first thing most players will buy, and an arena that asks for
#: nothing else.  It does 30 a swing and locks everything for only 0.3 seconds (`MeleeWeapon`), thirty-five
#: degrees either side and three units out; a swing inside its ten-degree `criticalSpread` is precise (x1.3,
#: 39), which is a Zombie or a Whisperer in one, and a swing outside it needs a second.  A Reject is always
#: one.  So everything here comes right up to the player: one at a time in the first wave, then twos and
#: threes, seven units out on bearings all round, each group within reach about five seconds after the one
#: before it and never more than six within five units in any eight seconds.
#:
#: Whisperers walk inside some of the crowds, which is where they belong: their walk is 25 dB under a
#: Zombie's and cannot be followed, but `Enemy.update` turns them aggressive at three units and they scream
#: (-17 dB, louder than a Zombie's walk), and then take 3.6 seconds to arrive at 0.75.  Three units is
#: exactly the banjo's reach, so the scream is the cue to swing, and the only thing this arena asks a player
#: to hear that is not loud.  The first wave has one on its own, sixty degrees round from the zombie before
#: it, so the scream is heard once for what it is.
#:
#: The two Runners come last in the last wave, on their own: each reaches arm's length two to three seconds
#: after the crowd before it has been dealt with and three or more before the next.  A Runner has 40 life,
#: one more than a precise swing, so it is two swings in the 2.1 seconds it is inside reach - or five of the
#: twelve revolver rounds from further out, which is what the rounds are for.
PLISTS['port_busker_1'] = _wave(
    [('WeakZombie', 0, 7.0, 0.0), ('Zombie', 143, 7.0, 5.0), ('WeakZombieB', 71, 7.0, 10.0),
     ('ZombieB', 230, 7.0, 15.0), ('QuietZombie', 290, 7.0, 20.0), ('Zombie', 196, 7.0, 25.0)],
    no_blast=True)
PLISTS['port_busker_2'] = _wave(
    _pack(('Zombie', 'WeakZombie'), 30, 7.0, 0.0)
    + _pack(('ZombieB', 'QuietZombie', 'WeakZombieB'), 170, 7.0, 5.0)
    + _pack(('Zombie', 'ZombieC'), 300, 7.0, 10.0)
    + _pack(('WeakZombieC', 'QuietZombie', 'Zombie'), 80, 7.0, 15.0)
    + _pack(('ZombieB', 'WeakZombie'), 220, 7.0, 20.0), no_blast=True)
PLISTS['port_busker_3'] = _wave(
    _pack(('Zombie', 'WeakZombieB', 'ZombieB'), 10, 7.0, 0.0)
    + _pack(('ZombieC', 'QuietZombie', 'WeakZombie'), 140, 7.0, 4.5)
    + _pack(('ZombieB', 'Zombie', 'WeakZombieC'), 240, 7.0, 9.0)
    + [('Runner', 180, 11.0, 16.2)]
    + _pack(('Zombie', 'QuietZombie', 'ZombieB'), 50, 7.0, 19.0)
    + _pack(('WeakZombieB', 'ZombieC', 'Zombie'), 310, 7.0, 23.5)
    + [('RunnerB', 110, 11.0, 32.0)], no_blast=True)
PLISTS['port_busker'] = {
    'challenge_id': 'port_busker',
    'title': 'Busker',
    'objective': 'A crowd always gathers round anyone who plays, and this one wants to stand very close.',
    'tip': 'Face them squarely and one note is enough. Some of them will not make a sound until they are '
           'close enough to touch.',
    'icon': 'Challenge_icon_02', 'icon_title': 'BU',
    'weapons': [{'name': 'pistol', 'ammo': '12'}, {'name': 'banjo'}],
    'bricks': ['port_busker_1', 'port_busker_2', 'port_busker_3'],
    'ambient': {'ambientPlaylist': 'ambient_ghosttown', 'gain': 0.5},
    'time_limit_star': {'reward': 200, 'objective': 150},
    'accuracy_star': {'reward': 200, 'objective': 70},
}

# ------------------------------------------------------------------------------------------------ Fore
#: The golf club, 4000 coins: 45 a swing, forty degrees either side and three units out, which is anything
#: light in one at level one - a Reject, a Zombie, a Runner (40).  What it costs is its lock, half a second in
#: which nothing else can be used, and `MeleeWeapon` takes it whether the swing found anything or not: a swing
#: at a Runner three and a half units out hits nothing and is still coming back when the Runner, 2.1 seconds
#: from arm's length to contact, gets there.
#:
#: The heavier ones are the arena.  A Chainsaw has 70 life, two swings at level one (precise 58.5 and critical
#: 67.5 both fall short), and closes its last three units at 1.45 in 1.9 seconds, after circling in at 0.725 so
#: that it is never quite where it was; three revolver rounds first (27.5 at ten units, 29.4 at five) leave it
#: on 41 to 42.5, which is one swing.  The Hulk has 100: three swings in the 3.6 seconds it is in reach, or six
#: rounds and one.  Eighteen rounds is three for each of the five Chainsaws and a start on the Hulk, and not
#: enough to shoot the Runners too (five each).
#:
#: Everything comes within reach on its own: four to five seconds apart in the first two waves and three and
#: a half in the last, every Runner and Chainsaw with nothing else arriving within three seconds of it.  The
#: Hulk's arrival roar is 3.67 or 5.71 seconds, so it reaches three units anywhere from 11.7 to 13.7 seconds
#: into the last wave; the Zombie before it is in reach at 9.5 and nothing after it before 17.7, so neither
#: roar puts it on top of anything.  WeakZombieD, used before only in Hydra, walks in the first and last waves.
PLISTS['port_fore_1'] = _wave(
    [('Zombie', 30, 7.0, 0.0), ('Runner', 150, 11.0, 6.2), ('WeakZombieD', 250, 7.0, 9.0),
     ('Runner', 60, 11.0, 16.2), ('Zombie', 200, 7.0, 19.4), ('RunnerB', 320, 11.0, 26.2)], no_blast=True)
PLISTS['port_fore_2'] = _wave(
    [('Zombie', 100, 7.0, 0.0), ('Chainsaw', 220, 10.0, 0.0), ('Runner', 20, 11.0, 11.7),
     ('WeakZombie', 300, 7.0, 13.4), ('Chainsaw', 130, 10.0, 14.65), ('ZombieB', 350, 7.0, 23.9),
     ('RunnerB', 250, 11.0, 30.2)], no_blast=True)
PLISTS['port_fore_3'] = _wave(
    [('Zombie', 45, 7.0, 0.0), ('Hulk', 160, 9.0, 0.0), ('WeakZombieD', 90, 7.0, 8.0),
     ('Chainsaw', 30, 10.0, 10.65), ('Runner', 290, 11.0, 13.7), ('Chainsaw', 250, 10.0, 17.65),
     ('Zombie', 220, 7.0, 18.9), ('WeakZombieD', 150, 7.0, 25.5), ('RunnerB', 100, 11.0, 31.2),
     ('Chainsaw', 180, 10.0, 31.65), ('ZombieC', 330, 7.0, 32.6), ('RunnerC', 20, 11.0, 42.2)],
    no_blast=True)
PLISTS['port_fore'] = {
    'challenge_id': 'port_fore',
    'title': 'Fore',
    'objective': 'Most of what is coming is in a hurry, and the club reaches no further than your arms.',
    'tip': 'A swing at empty air still has to come back before the next one. Some of them will need '
           'softening before they get that close.',
    'icon': 'Challenge_icon_02', 'icon_title': 'FO',
    'weapons': [{'name': 'pistol', 'ammo': '18'}, {'name': 'golf'}],
    'bricks': ['port_fore_1', 'port_fore_2', 'port_fore_3'],
    'ambient': {'ambientPlaylist': 'ambient_roman', 'gain': 0.5},
    'time_limit_star': {'reward': 250, 'objective': 170},
    'accuracy_star': {'reward': 250, 'objective': 70},
}

# ---------------------------------------------------------------------------------------- Bad Company
#: The Micro SMG with its rounds counted, and crowds that walk in round a Farty.
#:
#: A Farty has 50 life and its own `explosion` out of `enemies.plist`, {radius 3, damages 50, dispersal 75}:
#: `Enemy.die` sets it off, and `hit_by_explosion` puts 37.5 flat into everything within three units of it,
#: which is a Zombie (35), a Whisperer (35) or a Reject (20) dead.  FartyB's is {3, 30, 50}, 15 flat, which
#: leaves a Reject standing on 5 - one more round each, and a crowd that goes on walking after the bang.  At
#: level one a Farty is ten rounds of the Micro SMG (eight precise), and 160 rounds against the 288 it would
#: take to kill everything here one at a time means the crowds have to go with their Farties.  The wok is
#: there for what walks in alone.
#:
#: The crowd walks with its Farty (`_gassy`): the Farty in the middle and half a unit ahead, so a round aimed
#: at the middle of the crowd's sound finds it - `calculate_hit_enemies` takes the nearest in angle, and on a
#: tie the nearer - and the rest fifteen degrees either side and behind, every one inside its three units
#: from ten units out.  A fourth walks a little further back and joins them only from eight units, so the
#: bigger crowds are worth a moment's wait; and a Farty killed inside five units rings the ears for up to
#: thirteen seconds, so the wait has an end.  Groups come within five units about five seconds apart.
#:
#: Two Farties side by side, in the last wave, do not simply chain: a blast of 37.5 does not kill a Farty of
#: 50.  It leaves the second on 12.5, three rounds, and the second's blast takes the half of the crowd the
#: first did not reach.
#:
#: `NoBlast` refuses these waves only the blast the Chain Reaction card lends; a Farty's own is its own
#: (`Brick.__init__`).


def _gassy(kinds, farty: str, bearing: float, distance: float, at: float, spread: float = 15.0) -> list:
    """A crowd walking in round a Farty: it in the middle and half a unit ahead, the rest either side of it
    and behind - the first three inside the three units its blast reaches from ten units out, a fourth and
    fifth from about eight."""
    places = ((-spread, 0.5), (spread, 0.5), (0.0, 1.2), (-spread, 1.5), (spread, 1.5))
    return [(farty, bearing, distance, at)] + [
        (k, bearing + places[i][0], distance + places[i][1], at + 0.3 * (i + 1)) for i, k in enumerate(kinds)]


_REJ = ('WeakZombie', 'WeakZombieB', 'WeakZombieC')
PLISTS['port_company_1'] = _wave(
    _gassy(_REJ, 'Farty', 20, 10.0, 0.0)
    + [('Zombie', 140, 10.0, 6.0)]
    + _gassy(('WeakZombieC', 'WeakZombie', 'WeakZombieB'), 'Farty', 240, 10.0, 12.0)
    + [('WeakZombieB', 320, 10.0, 18.0)], no_blast=True)
PLISTS['port_company_2'] = _wave(
    _gassy(('Zombie', 'ZombieB', 'WeakZombie', 'Zombie'), 'Farty', 60, 10.0, 0.0)
    + _gassy(_REJ, 'FartyB', 190, 10.0, 5.0)
    + [('Zombie', 300, 10.0, 10.0)]
    + _gassy(('ZombieC', 'WeakZombieB', 'Zombie'), 'Farty', 120, 10.0, 15.0)
    + [('WeakZombieD', 340, 10.0, 20.0)], no_blast=True)
PLISTS['port_company_3'] = _wave(
    [('Farty', 325, 10.0, 0.0), ('Farty', 340, 10.4, 0.3),
     ('Zombie', 325, 11.1, 0.6), ('ZombieB', 333, 10.9, 0.9), ('WeakZombieC', 340, 11.5, 1.2),
     ('Zombie', 353, 10.9, 1.5)]
    + _gassy(('WeakZombie', 'WeakZombieC', 'WeakZombieB'), 'FartyB', 90, 10.0, 7.0)
    + _gassy(('Zombie', 'QuietZombie', 'ZombieB', 'WeakZombie'), 'Farty', 200, 10.0, 12.0)
    + [('Zombie', 30, 10.0, 17.0)]
    + _gassy(('ZombieB', 'WeakZombieC', 'ZombieC'), 'Farty', 245, 10.0, 22.0), no_blast=True)
PLISTS['port_company'] = {
    'challenge_id': 'port_company',
    'title': 'Bad Company',
    'objective': 'Nowhere near enough rounds for all of them, and some of them are not safe to stand next to.',
    'tip': 'The rest of the crowd does not seem to mind who it walks beside. Choose your moment, and do not '
           'let it be too close.',
    'icon': 'Challenge_icon_02', 'icon_title': 'BC',
    'weapons': [{'name': 'microsmg', 'ammo': '160'}, {'name': 'wok'}],
    'bricks': ['port_company_1', 'port_company_2', 'port_company_3'],
    'ambient': {'ambientPlaylist': 'ambient_roman', 'gain': 0.5},
    'time_limit_star': {'reward': 300, 'objective': 160},
    'accuracy_star': {'reward': 300, 'objective': 60},
}

# ------------------------------------------------------------------------------------------- Cattle Call
#: The Cattle Prod: 60 a swing (65 at level four), which is anything up to a Runner in one, in the widest
#: cone any melee weapon has - fifty degrees either side - and then a second and a half (1.2 at level
#: four) in which nothing can be swung or fired, the revolver included.
#:
#: The QuietZombie is what it is for.  It arrives in silence and walks 25 dB under a Zombie, and the first
#: a player really hears of it is the scream when it turns aggressive three units out; from there it closes
#: at 0.75 and arrives 3.6 s later.  A hundred degrees of cone finds what the ear can only roughly place:
#: turn to the scream and swing.
#:
#: The cows are the catch.  A swing takes whatever in the cone is nearest the aim *in angle*
#: (`calculate_hit_enemies`), and a cow is a target with one life.  A cow given no orientation walks straight
#: through the player at 0.5, so it is within reach for twelve seconds - six on the side it came from and six
#: on the other.  Each one here is timed to be in reach, about forty degrees from a Whisperer, when that
#: Whisperer screams (the first, in wave 1, beside an ordinary Zombie, to learn it on): a swing aimed at the
#: scream takes the Whisperer, one aimed somewhere between the two takes the cow and costs the lock.  None is
#: ever closer than 35 degrees to one, because at ten a swing would be a coin toss rather than a skill; and
#: every cow can be heard coming for fifteen seconds, so the eighteen revolver rounds can also clear one out
#: of the way, bring a Runner down at range, or take half a Hulk (five rounds and one swing instead of two).
#:
#: Everything is placed by the moment it comes within reach (`_reaching`, worked back through its arrival
#: recording and its walk): never two due inside one lock unless they are a pair from opposite sides a second
#: apart, which two swings and a half turn answer inside 3.6 s; Runners on their own; each Hulk (two swings)
#: with nothing due in its window whichever of its two roars (3.7 or 5.7 s) it plays.
#:
#: How long each kind's arrival recording is, in seconds (a Hulk's shorter roar); chapter 6's `_slots`
#: places its groups by it too.
_ARRIVE = {'QuietZombie': 0.58, 'Zombie': 1.51, 'ZombieB': 1.25, 'ZombieC': 1.90, 'WeakZombie': 2.60,
           'WeakZombieB': 1.42, 'WeakZombieC': 1.39, 'Runner': 1.44, 'RunnerB': 1.44, 'RunnerC': 1.44,
           'Hulk': 3.67, 'HulkB': 3.67}
_WALK = {'QuietZombie': 0.5, 'Zombie': 0.5, 'ZombieB': 0.5, 'ZombieC': 0.5, 'Runner': 1.3, 'Hulk': 0.75,
         'HulkB': 0.75}
_COW_ARRIVE = (1.56, 1.41, 2.11)          # Cow, Cow2, Cow3


def _reaching(spec):
    """(kind, bearing, the second of the wave it comes within three units) -> a `_wave` entry."""
    out = []
    for kind, bearing, t in spec:
        d = 11.0 if kind.startswith('Runner') else 10.0
        out.append((kind, bearing, d, round(t - _ARRIVE[kind] - (d - 3.0) / _WALK[kind], 2)))
    return out


def _cows_in(*places):
    """Cows from eleven units, each given by its bearing and the second it comes within reach."""
    return {'Cow%s' % (i + 1 if i else ''): {'spawn_angle': float(a), 'spawn_distance': 11.0,
                                             'spawn_time': round(t - _COW_ARRIVE[i] - 16.0, 2)}
            for i, (a, t) in enumerate(places)}


_W = 'QuietZombie'
PLISTS['port_cattlecall_1'] = _wave(_reaching(
    [('Zombie', 30, 15.6), (_W, 150, 19.6), ('Zombie', 240, 24.6), (_W, 60, 28.6), ('ZombieB', 200, 33.1),
     (_W, 320, 37.6), ('Zombie', 110, 42.1)]), no_blast=True, passers=_cows_in((195, 24.1)))
PLISTS['port_cattlecall_2'] = _wave(_reaching(
    [(_W, 0, 14.6), ('Zombie', 120, 18.1), (_W, 220, 21.6), (_W, 40, 22.6), ('Hulk', 300, 28.1),
     (_W, 130, 33.6), ('Runner', 90, 37.2), (_W, 250, 40.6), (_W, 100, 44.1), ('ZombieB', 190, 47.6)]),
    no_blast=True, passers=_cows_in((80, 22.6), (210, 39.9)))
PLISTS['port_cattlecall_3'] = _wave(_reaching(
    [(_W, 45, 14.6), (_W, 225, 15.6), ('Zombie', 160, 18.6), (_W, 300, 20.6), (_W, 110, 21.4),
     ('Hulk', 210, 24.5), (_W, 20, 28.0), (_W, 250, 30.0), ('Runner', 150, 32.0), (_W, 330, 34.5),
     (_W, 150, 35.3), ('ZombieC', 70, 38.0), (_W, 230, 41.0), ('Runner', 300, 42.0), (_W, 100, 44.5),
     (_W, 200, 45.3), ('HulkB', 320, 48.0), (_W, 160, 54.5)]),
    no_blast=True, passers=_cows_in((60, 27.5), (190, 34.5), (120, 54.0)))
PLISTS['port_cattlecall'] = {
    'challenge_id': 'port_cattlecall',
    'title': 'Cattle Call',
    'objective': 'The quiet ones make no sound until they are close enough to touch, and the cows have '
                 'wandered in again.',
    'tip': 'The prod reaches wide, and it does not care what it finds. Be sure of what is nearest to where '
           'you are pointing.',
    'icon': 'Challenge_icon_02', 'icon_title': 'CC',
    'weapons': [{'name': 'pistol', 'ammo': '18'}, {'name': 'prod'}],
    'bricks': ['port_cattlecall_1', 'port_cattlecall_2', 'port_cattlecall_3'],
    'ambient': {'ambientPlaylist': 'ambient_ghosttown', 'gain': 0.5},
    'time_limit_star': {'reward': 350, 'objective': 190},
    'accuracy_star': {'reward': 350, 'objective': 70},
}

# -------------------------------------------------------------------------------------------- Front Line
#: The Tactical Rifle, and a line that does not stop coming.  At level one it puts 10 a round into what it
#: is pointed at (a 75 % floor: 7.9 at ten units, 9.5 at five), 0.25 s apart while the trigger is held,
#: in a cone narrowed to twenty degrees - and it holds 25 rounds and takes **four seconds** to fill again.
#: A Zombie is four or five rounds, so a magazine is five of them, and the line here brings one every two
#: seconds or so: the reload has to be put somewhere, and where is the arena.
#:
#: The Riot Gear Zombie is what decides where.  A round into one while it walks does its full damage, and
#: it keeps walking for as long as its `_shielddown_` recording lasts (2.2 or 2.8 s); then it stops and
#: nothing a gun does touches it for five seconds and its `_shieldup_` (1.7 or 1.9 s) - rounds held into it
#: then are rounds thrown away, and each one says so with a `shieldimpact`.  So one burst into a Shield
#: is half its life and seven seconds of it standing still while the line walks past it: it comes in
#: last, on its own, and the magazine and the reload can go to the rest in the meantime.  At level one it
#: is sixteen rounds, about two windows; at level four (15 a round, 40 in the magazine) nearly one.
#: (Hits during its 4.25 s arrival or inside three units never raise the shield; a quick player can find
#: that out.)
#:
#: A Hulk in waves 2 and 3 is the other thing worth a magazine: 100 life at 0.75 u/s, twelve rounds at
#: level one.  Its arrival roar is 3.7 or 5.7 s; either way it walks in while the line around it is still
#: at range, and nothing else fast is due then.  One Runner closes wave 3, alone, after the line.
#:
#: Each wave comes from one side - the right, the left, behind - and never from straight ahead, bearing
#: 270, which is where the player starts facing and where the hit test's degrees wrap round
#: (`_deg360`): a target across that seam loses the nearest-in-angle contest it should win.  Whisperers
#: walk in the line and die with it; nothing has to be found by them.
def _line(kinds, bearings, distance: float, every: float, first: float = 0.0):
    """Walkers one at a time, `every` seconds apart, going back and forth across the bearings of one side."""
    return [(kinds[i % len(kinds)], bearings[i], distance, round(first + i * every, 2))
            for i in range(len(bearings))]


PLISTS['port_frontline_1'] = _wave(
    _line(('Zombie', 'WeakZombie', 'ZombieB', 'Zombie', 'WeakZombieB', 'ZombieC', 'Zombie', 'ZombieB'),
          (10, 40, 345, 25, 0, 35, 355, 20), 10.0, 2.5)
    + [('Shield', 15, 11.0, 6.0)], no_blast=True)
PLISTS['port_frontline_2'] = _wave(
    _line(('ZombieB', 'Zombie', 'WeakZombie', 'ZombieC', 'QuietZombie', 'Zombie', 'WeakZombieB', 'ZombieB',
           'Zombie', 'ZombieC', 'Zombie'),
          (150, 190, 130, 175, 205, 140, 160, 195, 125, 180, 145), 10.0, 2.2)
    + [('Shield', 140, 11.0, 3.0), ('Hulk', 170, 11.0, 9.0), ('Shield', 185, 11.0, 15.0)], no_blast=True)
PLISTS['port_frontline_3'] = _wave(
    _line(('Zombie', 'ZombieB', 'WeakZombie', 'ZombieC', 'Zombie', 'QuietZombie', 'ZombieB', 'WeakZombieB',
           'Zombie', 'ZombieC', 'ZombieB', 'WeakZombie', 'Zombie', 'ZombieB'),
          (60, 100, 30, 120, 80, 45, 135, 70, 20, 110, 90, 40, 125, 55), 10.0, 2.0)
    + [('Shield', 80, 11.0, 2.0), ('Hulk', 60, 11.0, 8.0), ('Shield', 40, 11.0, 14.0),
       ('HulkB', 110, 11.0, 20.0), ('Runner', 90, 11.0, 40.0)], no_blast=True)
PLISTS['port_frontline'] = {
    'challenge_id': 'port_frontline',
    'title': 'Front Line',
    'objective': 'They come from one side at a time, in a line that does not stop, and some of them '
                 'brought shields.',
    'tip': 'A shield takes a moment to go up and a long time to come down. Know what the rest of the '
           'magazine is for before you start it.',
    'icon': 'Challenge_icon_02', 'icon_title': 'FL',
    'weapons': [{'name': 'tactical', 'ammo': '999'}, {'name': 'wok'}],
    'bricks': ['port_frontline_1', 'port_frontline_2', 'port_frontline_3'],
    'ambient': {'ambientPlaylist': 'ambient_ruins', 'gain': 0.5},
    'time_limit_star': {'reward': 350, 'objective': 180},
    'accuracy_star': {'reward': 350, 'objective': 60},
}

# -------------------------------------------------------------------------------------------- Short Game
#: Two tools that wait for each other.  The Grenade Launcher puts 45 into whatever it lands on and 22.5 into
#: everything else within five units (30 flat at level four), which is a crowd of Rejects in one; five to a
#: clip at level one, one a second, two seconds to reload.  The golf club is 45 a swing (50 at four) in a
#: forty-degree cone at arm's length, which is anything light in one, and locks everything for half a
#: second (a quarter at four).  But a swing locks the launcher too and **throws away a reload in progress**
#: (`shoot_with_melee`), and a grenade fired keeps the club from swinging for a second after it
#: (`is_weapon_ready_to_shoot`, the gun's own cooldown).  Club first and then the launcher costs half a
#: second; the launcher first and then the club costs a whole one, and a Runner in reach has two.
#:
#: The crowds are Rejects, most with a Zombie walking half a unit ahead in the middle (`_escort`): the
#: grenade goes to the nearest thing in front of the player (`target_enemi_for_explosive_weapon`), which is
#: that Zombie, so on target it takes the lot, and a little off it leaves the Zombie on 12.5 to walk in to
#: the club.  What gets through comes on its own, into the club's reach while a crowd is still out at range
#: on another side: Runners, a Whisperer, a Chainsaw (70, two swings - it circles, so a grenade's lead is
#: wrong for it) and a Hulk (two grenades on target and a swing, or three swings; both of its roars, 3.7 and
#: 5.7 s, leave it room).  The Dodges go the other way: a club sends one sidestepping out of reach every time
#: it lands, and a blast never does.  In wave 3 a Runner comes down the very bearing a crowd is on, ahead of
#: it: a grenade meant for the crowd goes to the Runner and bursts at the player's feet, so it has to be
#: clubbed first.
#:
#: Thirty grenades is two for every crowd and heavy with some to spare, not one for every Zombie.
#: Everything within five units is spaced about five seconds a group, and no eight seconds bring more than
#: about ten.
_W3 = ('WeakZombieC', 'WeakZombie', 'WeakZombieB')

PLISTS['port_shortgame_1'] = _wave(
    _pack(_W4, 30, 11.0, 0.0)
    + [('Zombie', 200, 9.0, 2.0)]
    + _pack(('WeakZombieB', 'WeakZombie', 'WeakZombieC', 'WeakZombieB'), 150, 11.0, 7.0)
    + [('ZombieB', 330, 9.0, 10.0)]
    + _pack(('WeakZombieC', 'WeakZombieB', 'WeakZombie', 'WeakZombieC'), 240, 11.0, 14.0)
    + [('Zombie', 90, 9.0, 17.0), ('Runner', 20, 11.0, 26.0)], no_blast=True)
PLISTS['port_shortgame_2'] = _wave(
    _escort(_W3, 'Zombie', 60, 11.0, 0.0)
    + [('Runner', 190, 11.0, 6.0)]
    + _escort(('WeakZombieB', 'WeakZombieC', 'WeakZombie'), 'ZombieB', 300, 11.0, 5.0)
    + [('QuietZombie', 120, 9.0, 9.0)]
    + _escort(('WeakZombie', 'WeakZombieB', 'WeakZombieC'), 'ZombieC', 170, 11.0, 11.0)
    + [('Runner', 40, 11.0, 17.0)]
    + _pack(_W4, 40, 11.0, 18.5)
    + [('Zombie', 250, 9.0, 20.0), ('Dodge', 20, 11.0, 23.0)]
    + _escort(_W3, 'Zombie', 110, 11.0, 24.0), no_blast=True)
PLISTS['port_shortgame_3'] = _wave(
    _escort(_W4, 'Zombie', 0, 11.0, 0.0)
    + [('Runner', 300, 11.0, 12.0), ('Hulk', 200, 11.0, 10.3)]
    + _escort(('WeakZombieB', 'WeakZombieC', 'WeakZombie'), 'ZombieB', 120, 11.0, 13.5)
    + [('DodgeB', 20, 11.0, 21.5), ('Chainsaw', 60, 10.0, 23.5)]
    + _escort(('WeakZombie', 'WeakZombieB', 'WeakZombieC', 'WeakZombieB'), 'ZombieC', 240, 11.0, 27.5)
    + _pack(_W4, 330, 11.0, 33.5) + [('Runner', 330, 11.0, 39.0)]
    + [('QuietZombie', 160, 9.0, 41.4)]
    + _escort(_W3, 'Zombie', 90, 11.0, 41.5)
    + [('Runner', 210, 11.0, 53.0)]
    + _escort(('WeakZombieC', 'WeakZombie', 'WeakZombieB', 'WeakZombie'), 'ZombieB', 180, 11.0, 51.5),
    no_blast=True)
PLISTS['port_shortgame'] = {
    'challenge_id': 'port_shortgame',
    'title': 'Short Game',
    'objective': 'A launcher for the crowds and a club for whatever walks through them.',
    'tip': 'Each of them waits for the other, and one of them waits longer. Decide which comes first before '
           'it matters.',
    'icon': 'Challenge_icon_02', 'icon_title': 'SG',
    'weapons': [{'name': 'grenade', 'ammo': '30'}, {'name': 'golf'}],
    'bricks': ['port_shortgame_1', 'port_shortgame_2', 'port_shortgame_3'],
    'ambient': {'ambientPlaylist': 'ambient_roman', 'gain': 0.5},
    'time_limit_star': {'reward': 450, 'objective': 220},
    'accuracy_star': {'reward': 450, 'objective': 70},
}

# ----------------------------------------------------------------------------------------- Bonfire Night
#: The power-ups no arena has used, as part of the plan rather than a present.  `PowerUp` with
#: `force_spawn_time` puts a crate five units out on a bearing of its own two seconds later; it arrives over
#: 4.7 s, beeps for fifteen, and has one life - and the Sawn-off hits everything sixty degrees either side
#: of where it points, crates included, so a shell fired towards a pack on the crate's side opens it
#: whether that was meant or not.  It beeps where it is, and the player chooses when.
#:
#: **Fireworks** (waves 1 and 3): from the moment it opens, everything within ten units of the player takes
#: a blast every half second for eight seconds - about 21 in all at level one (16.5-27), 49 at level four,
#: and nothing at all beyond ten.  For the Sawn-off at level one that is the difference between two shells
#: and one: its damage is nearly all distance (`dispersal` 1: 28 at three units, 21 at six, 14 at eight), a
#: Zombie has 35 and no plain shell kills one, and a Zombie with 14 left dies to a shell at eight units.  So
#: it is worth most opened when every crowd is inside ten units, and little before.  In wave 1 that is the
#: moment the crate can first be shot - three crowds walk in from nine, ten and a half and twelve units and
#: reach five units three seconds apart - so the first one teaches it; in wave 3 the crate is ready five
#: seconds before the crowd is inside ten units, and two Zombies come in first on a bearing of their own, to
#: be shot with the crate somewhere beeping - on their side of the player or not.
#:
#: **Tornado** (wave 2): four gusts over ten seconds, each pushing everything outward a quarter of a unit at
#: level one (1.25 at level four): at level one about two seconds of a Zombie's walk, which is a Sawn-off
#: reload (2.3 s), and ten seconds at level four.  It comes in the middle of two pairs of crowds from
#: opposite sides; opened when the shells are gone and a pack is at arm's length it buys the reload, and
#: opened by a stray shell with a pack at three units it only pushes it out of the shotgun's best range.
#:
#: One crate a wave, and each after the one before is long over: a crate appearing stops whatever power-up
#: is still running, and none here is meant to.  The paired crowds of wave 2 come four seconds apart, time for
#: two shells, a reload and a half turn.  Runners come as one pair at the end of waves 2 and 3, after the
#: last crowd is due to be dead: at level one a Runner needs two shells unless one is a critical, so they must
#: find both barrels loaded, and nothing else must be asking for them.
_Z3 = ('Zombie', 'ZombieB', 'ZombieC')
_Z3B = ('ZombieB', 'ZombieC', 'Zombie')
_Z3C = ('ZombieC', 'Zombie', 'ZombieB')

PLISTS['port_bonfire_1'] = _wave(
    _pack(_Z3, 30, 9.0, 0.0) + _pack(('ZombieB', 'Zombie', 'WeakZombie'), 150, 10.5, 0.5)
    + _pack(('ZombieC', 'WeakZombieB', 'Zombie'), 250, 12.0, 1.0)
    + [('Zombie', 100, 10.0, 18.0), ('WeakZombieB', 320, 10.0, 22.0), ('ZombieB', 200, 10.0, 26.0)],
    no_blast=True)
PLISTS['port_bonfire_1']['PowerUp'] = {'force_spawn_time': 0.1, 'type': 'fireworks'}
PLISTS['port_bonfire_2'] = _wave(
    _pack(_Z3, 60, 10.0, 0.0) + _pack(_Z3B, 240, 10.0, 4.0)
    + _pack(('Zombie', 'ZombieC', 'ZombieB', 'WeakZombie'), 150, 10.0, 10.0) + _pack(_Z3C, 330, 10.0, 14.0)
    + [('Zombie', 200, 10.0, 20.0)] + _pack(('Runner', 'RunnerB'), 100, 11.0, 33.0, spread=5.0),
    no_blast=True)
PLISTS['port_bonfire_2']['PowerUp'] = {'force_spawn_time': 6.0, 'type': 'tornado'}
PLISTS['port_bonfire_3'] = _wave(
    _pack(('Zombie', 'ZombieB'), 300, 9.0, 5.0)
    + _pack(_Z3, 20, 12.0, 9.0) + _pack(_Z3B, 140, 12.0, 10.0) + _pack(_Z3C, 250, 12.0, 11.0)
    + _pack(_Z3, 200, 10.0, 29.0) + _pack(_Z3B, 20, 10.0, 32.0)
    + _pack(('ZombieC', 'Zombie', 'ZombieB', 'WeakZombieB'), 110, 10.0, 37.0)
    + _pack(('Runner', 'RunnerB'), 250, 11.0, 52.0, spread=5.0), no_blast=True)
PLISTS['port_bonfire_3']['PowerUp'] = {'force_spawn_time': 3.0, 'type': 'fireworks'}
PLISTS['port_bonfire'] = {
    'challenge_id': 'port_bonfire',
    'title': 'Bonfire Night',
    'objective': 'Forty shells, a crowd for every few of them, and a crate every wave. What is in it helps '
                 'only if it is opened at the right moment.',
    'tip': 'A shotgun opens anything in front of it. Know where the crate is, and what will be near you when '
           'it opens.',
    'icon': 'Challenge_icon_02', 'icon_title': 'BN',
    'weapons': [{'name': 'sawnoff', 'ammo': '40'}, {'name': 'wok'}],
    'bricks': ['port_bonfire_1', 'port_bonfire_2', 'port_bonfire_3'],
    'ambient': {'ambientPlaylist': 'ambient_foundry', 'gain': 0.5},
    'time_limit_star': {'reward': 450, 'objective': 210},
    'accuracy_star': {'reward': 450, 'objective': 70},
}

def _shoulder(kinds, bearing: float, width: float, distance: float, at: float):
    """A line standing shoulder to shoulder across `width` degrees, all at one distance, arriving from one
    end to the other a quarter of a second apart, so the line is heard drawing itself."""
    n = len(kinds)
    step = width / (n - 1) if n > 1 else 0.0
    return [(k, bearing - width / 2.0 + i * step, distance, round(at + 0.25 * i, 2)) for i, k in enumerate(kinds)]


#: The Police Shotgun: twenty a shell at level one and thirty at four, into everything within fifty degrees
#: either side of the aim, and - its `dispersal` is 50 where the Sawn-off's is 1 - half of it however far away
#: the target stands (`hit_by_weapon` 0x100060b30): 13 at nine units and 10 at the edge of its eleven at level
#: one, 20 and 15 at four.  So it is the gun for a crowd that has not arrived yet, and the arena is lines of
#: Rejects and Zombies standing shoulder to shoulder at nine and ten units, drawn in a quarter of a second
#: apart from one end to the other so a line is heard as a line.  A Zombie is three shells at nine units at
#: level one and two at four; a Reject two and one.
#:
#: What it is bad at is being in a hurry.  One shell a second, seven of them at level one (ten at four), then
#: three and a half seconds of reload: a line is two or three shells, so a clip is two or three lines, and the
#: reload taken in the gap between lines is the one that does not kill you.  Wave 1 is four lines each
#: narrower than the cone, eight seconds apart.  Wave 2 has lines wider than it (130 and 120 degrees: the
#: ends need a second aim, or an aim off-centre) and two short ones from opposite sides a second and a half
#: apart.  Wave 3 has two lines side by side (140 degrees between their far ends), a Hulk pair walking in a
#: line (seven shells each at level one, four at four, and the line's shells go into them too), a line of
#: seven across 140 degrees, and two lines ninety degrees apart.  The Runner packs (three shells at level
#: one, two at four) each come on their own, six seconds or more from the groups either side of them.
PLISTS['port_riot_1'] = _wave(
    _shoulder(('WeakZombie', 'Zombie', 'WeakZombieC', 'ZombieB', 'WeakZombie'), 20, 70, 9.0, 0.0)
    + _shoulder(('Zombie', 'WeakZombieC', 'ZombieC', 'WeakZombie', 'Zombie'), 150, 70, 9.0, 8.0)
    + _shoulder(('WeakZombieC', 'ZombieB', 'WeakZombie', 'Zombie', 'WeakZombieC'), 240, 80, 10.0, 16.0)
    + _shoulder(('Zombie', 'WeakZombie', 'ZombieC', 'WeakZombieC', 'ZombieB'), 90, 80, 9.0, 24.0), no_blast=True)
PLISTS['port_riot_2'] = _wave(
    _shoulder(('Zombie', 'WeakZombie', 'ZombieB', 'ZombieC', 'WeakZombieC', 'Zombie'), 0, 130, 9.0, 0.0)
    + _shoulder(('WeakZombieC', 'Zombie', 'ZombieC', 'WeakZombie', 'ZombieB'), 120, 90, 10.0, 7.0)
    + _pack(_R3, 230, 11.0, 19.0, spread=5.0)
    + _shoulder(('Zombie', 'ZombieB', 'WeakZombie', 'ZombieC', 'WeakZombieC', 'Zombie'), 330, 120, 9.0, 23.0)
    + _shoulder(('ZombieB', 'Zombie', 'WeakZombie', 'ZombieC'), 70, 60, 9.0, 30.0)
    + _shoulder(('Zombie', 'WeakZombieC', 'ZombieB', 'Zombie'), 250, 60, 9.0, 31.5), no_blast=True)
PLISTS['port_riot_3'] = _wave(
    _shoulder(('Zombie', 'ZombieB', 'WeakZombie', 'ZombieC'), 330, 60, 9.0, 0.0)
    + _shoulder(('ZombieC', 'WeakZombieC', 'Zombie', 'ZombieB'), 50, 60, 9.0, 0.5)
    + _shoulder(('Zombie', 'WeakZombie', 'ZombieB', 'ZombieC', 'WeakZombieC', 'Zombie'), 170, 100, 9.0, 8.0)
    + [('Hulk', 164, 9.5, 6.0), ('HulkB', 176, 9.5, 6.3)]
    + _pack(_R3, 270, 11.0, 18.0, spread=5.0)
    + _shoulder(('ZombieB', 'Zombie', 'WeakZombieC', 'ZombieC', 'WeakZombie', 'Zombie', 'ZombieB'), 30, 140, 10.0, 22.0)
    + _shoulder(('Zombie', 'ZombieC', 'WeakZombie', 'ZombieB', 'WeakZombieC'), 210, 80, 9.0, 32.0)
    + _shoulder(('ZombieC', 'Zombie', 'WeakZombieC', 'ZombieB'), 120, 60, 9.0, 33.0)
    + _pack(_R3, 300, 11.0, 44.0, spread=5.0), no_blast=True)
PLISTS['port_riot'] = {
    'challenge_id': 'port_riot',
    'title': 'Crowd Control',
    'objective': 'They come in long lines, shoulder to shoulder, and this shotgun is nearly as wide as a line.',
    'tip': 'It still bites a long way out, and it bites everything in front of you. The slow reload is the '
           'danger: choose when to take it.',
    'icon': 'Challenge_icon_02', 'icon_title': 'CO',
    'weapons': [{'name': 'policeshotgun', 'ammo': '999'}, {'name': 'wok'}],
    'bricks': ['port_riot_1', 'port_riot_2', 'port_riot_3'],
    'ambient': {'ambientPlaylist': 'ambient_ruins', 'gain': 0.5},
    'time_limit_star': {'reward': 500, 'objective': 170},
    'accuracy_star': {'reward': 500, 'objective': 85},
}

#: Where each of a huddle stands, in units across and back from its middle: none of them more than 2.5 from
#: any other, inside the three that every one of them carries.
_HUDDLE = ((0.0, 0.0), (-1.2, 0.3), (1.2, 0.3), (-0.6, 1.2), (0.6, 1.2), (0.0, -1.0), (-1.4, -0.7))


def _huddle(kinds, bearing: float, distance: float, at: float):
    """A few standing close together, arriving a quarter of a second apart."""
    out = []
    for i, k in enumerate(kinds):
        across, back = _HUDDLE[i]
        out.append((k, round(bearing + math.degrees(across / distance), 1), distance + back, round(at + 0.25 * i, 2)))
    return out


def _file(kinds, bearing: float, first: float, at: float, gap: float = 2.2):
    """In single file on one bearing, `gap` apart, the front one at `first`: all arrive at once, so they walk
    as they stand.  Kinds whose arrival roars are within 0.4 s of each other, so no gap opens past three."""
    return [(k, bearing, first + i * gap, at) for i, k in enumerate(kinds)]


def _spaced(kinds, bearing: float, step: float, distance: float, at: float):
    """A line `step` degrees apart, all at one distance, arriving from one end to the other.  At ten units
    `step` 25 puts them 4.3 apart, out of each other's reach; they close ranks as they come, to three units
    at 6.9 out."""
    n = len(kinds)
    return [(k, bearing + (i - (n - 1) / 2.0) * step, distance, round(at + 0.25 * i, 2)) for i, k in enumerate(kinds)]


#: The Police Shotgun under Chain Reaction (`everythingExplodes`): every zombie that dies goes off with
#: 37.5 flat into everything within three units of it (`CHAIN_REACTION_BLAST`, {3, 50, 75}, and
#: `hit_by_explosion`'s cancelling falloff), which is a Reject, a Zombie or a Whisperer, and one blast
#: short of a Runner (40), a Farty (50) or a Hulk.  The card is read when each one dies (`Enemy.blast`), so
#: it holds from the first wave.  Three shapes, all of them walking in from nine and ten units:
#:
#: * a **huddle** (`_huddle`): six or so standing within two and a half units of each other.  One death
#:   takes the lot, and a Hulk in the middle of one takes a blast from each neighbour.
#: * a **file** (`_file`): one behind another on one bearing, 2.2 units apart, the back of it beyond the
#:   shotgun's eleven.  The front one's blast takes the next, and so on down the line.  Kinds whose arrival
#:   roars differ by 0.4 s or less, so the gaps stay under three units whichever roar is played.  A FartyB in
#:   the third file is a firebreak: it has 50 of life, survives the blast, and its own is 15.
#: * a **line** (`_spaced`): twenty-two or twenty-five degrees apart at ten units, 3.8 to 4.3 apart - out of
#:   each other's reach - and wider than the cone.  They close ranks as they come: three units apart at 7.9
#:   and 6.9 out.  Started there, one death runs the length of the line; started early, each end has to be
#:   turned to.  Farties in the last line hold a chain up until a second blast reaches them.
#:
#: And all of it is loud: a blast centred within five units rings the ears, three to thirteen seconds a
#: blast, adding up to twenty, and a chain is many blasts.  Killed out beyond five, nothing rings.  So the
#: window for a line is between seven and five units, and a wok kill at arm's length - which goes off at arm's
#: length - is the last thing to want.  Runner packs and Hulk pairs, which a chain does not finish, come on
#: their own.
PLISTS['port_chain_1'] = _wave(
    _huddle(('WeakZombie', 'Zombie', 'WeakZombieC', 'ZombieB', 'WeakZombie'), 20, 10.0, 0.0)
    + _file(('Zombie', 'ZombieC', 'Zombie', 'WeakZombieC'), 140, 9.0, 5.0)
    + _huddle(('Zombie', 'WeakZombieC', 'ZombieB', 'WeakZombie', 'ZombieC', 'WeakZombieC'), 250, 10.0, 10.0)
    + _file(('ZombieC', 'Zombie', 'WeakZombieC', 'Zombie', 'ZombieC'), 80, 9.0, 15.0)
    + _spaced(('Zombie', 'WeakZombie', 'ZombieB', 'ZombieC', 'WeakZombieC'), 320, 25.0, 10.0, 20.0))
PLISTS['port_chain_2'] = _wave(
    _spaced(('Zombie', 'ZombieB', 'Farty', 'ZombieC', 'Zombie', 'ZombieB'), 0, 25.0, 10.0, 0.0)
    + _huddle(('Zombie', 'WeakZombieC', 'Farty', 'ZombieB', 'WeakZombie', 'ZombieC'), 130, 10.0, 5.0)
    + _pack(_R3, 230, 11.0, 17.5, spread=5.0)
    + _spaced(('ZombieB', 'ZombieC', 'Zombie', 'Farty', 'ZombieC'), 300, 25.0, 10.0, 17.0)
    + _file(('Zombie', 'ZombieC', 'WeakZombieC', 'Zombie', 'ZombieC'), 60, 9.0, 23.5)
    + _pack(('Hulk', 'HulkB'), 170, 10.0, 26.5)
    + _spaced(('Zombie', 'ZombieB', 'ZombieC', 'Zombie', 'ZombieB'), 250, 22.0, 10.0, 30.5)
    + _pack(_R3, 20, 11.0, 41.2, spread=5.0))
PLISTS['port_chain_3'] = _wave(
    [('Hulk', 30, 10.0, 0.0)] + _huddle(('Zombie', 'ZombieB', 'WeakZombieC', 'ZombieC', 'WeakZombie'),
                                         30, 10.5, 2.0)
    + _file(('Zombie', 'ZombieC', 'FartyB', 'Zombie', 'WeakZombieC', 'ZombieC'), 150, 9.0, 7.4)
    + _spaced(('Zombie', 'ZombieC', 'ZombieB', 'Farty', 'ZombieC', 'Zombie', 'ZombieB'), 270, 25.0, 10.0, 10.0)
    + _pack(_R3, 90, 11.0, 22.3, spread=5.0)
    + _huddle(('ZombieC', 'WeakZombie', 'Zombie', 'WeakZombieC', 'ZombieB', 'Zombie'), 200, 10.0, 22.5)
    + [('Hulk', 330, 10.0, 27.5), ('HulkB', 336, 10.5, 27.8)]
    + _huddle(('WeakZombie', 'WeakZombieC', 'WeakZombie'), 333, 11.5, 29.0)
    + _pack(('Hulk', 'HulkB'), 60, 10.0, 33.5)
    + _pack(_R3, 160, 11.0, 45.0, spread=5.0)
    + _spaced(('Zombie', 'Farty', 'ZombieB', 'WeakZombieC', 'Farty', 'Zombie'), 250, 25.0, 10.0, 45.5)
    + _pack(_R3, 20, 11.0, 57.0, spread=5.0))
PLISTS['port_chain'] = {
    'challenge_id': 'port_chain',
    'title': 'Shell Shock',
    'objective': 'Every one of them carries something that goes off when it dies, and some of them walk '
                 'close enough together to share it.',
    'tip': 'One going off sets off whoever stands near it, and you hear all of it. Let a crowd close ranks '
           'before you start it, but not on top of you.',
    'icon': 'Challenge_icon_02', 'icon_title': 'SH',
    'weapons': [{'name': 'policeshotgun', 'ammo': '999'}, {'name': 'wok'}],
    'bricks': ['port_chain_1', 'port_chain_2', 'port_chain_3'],
    'ambient': {'ambientPlaylist': 'ambient_foundry', 'gain': 0.5},
    'Modifiers': ['everythingExplodes'],
    'time_limit_star': {'reward': 600, 'objective': 190},
    'accuracy_star': {'reward': 600, 'objective': 65},
}

#: The Police Shotgun and the cheapest club in the armory.  The shotgun hits everything fifty degrees either
#: side and keeps half its damage at any range (`dispersal` 50 in `hit_by_weapon` 0x100060b30: 20 at nine
#: units at level four, 13 at level one), so a crowd spread across the front at nine or ten units - a
#: crescent, `_crescent`, eighty degrees wide - is one aim and two or three shells, long before it is near.
#: What it is bad at is one fast thing from somewhere else: a shell a second, and 3.6 seconds to load.  So
#: every crescent has a Runner behind it, from another side, timed to reach arm's length around when the
#: shells for its crescent are spent - the encore - and that is the banjo's: 40 a swing at level four, a
#: Runner in one, a quarter of a second between swings.
#:
#: The trick is the one the melee weapons have always had (`WeaponManager.shoot_with_melee`): **a swing
#: cancels a reload in progress**, and a swing cannot start until a second after a Police shell
#: (`is_weapon_ready_to_shoot`).  Reload the moment the crescent is dead and the Runner arrives inside the
#: 3.6 seconds, and the swing that saves you throws the reload away - with the next crescent on its way.
#: Load early, with shells still in hand, or shoot the crescent further out.  It is all hearable: a Runner's
#: arrival roar is the loudest in the game (-14.7 dBFS) and it takes eight seconds to arrive.
#:
#: Two crescents carry a Hulk (four shells at level four, or three swings), and two a Riot Gear Zombie
#: walking in the line at its pace.  A shell raises its shield, it stops, and the crowd walks on and dies
#: without it; it comes in on its own afterwards, and inside three units it never shields, so it is the
#: banjo's too.  No Whisperer: an earlier draft had one in a crescent, and a Whisperer that outlives its line
#: is a cue nobody can hear.  No Berserk: a shotgun is in hand.  The Runners come one at a time, each about
#: five seconds after the last.
#:
#: The Banjo rather than the Golf club: both are cheap and quick, the Golf already has two arenas, and the
#: Banjo only one.
#:
#: Measured with the referee (C1's player, which fires the Police Shotgun as soon as its shells kill; 10 runs
#: a rung, 2026-09-30): level 4 wins 90 100 90 100 90 50 % at R = 0.6 .. 1.6 s, difficulty 1.60.

_C5 = (('Zombie', 'WeakZombie', 'ZombieB', 'WeakZombieC', 'ZombieC'),
       ('ZombieB', 'Zombie', 'WeakZombie', 'ZombieC', 'WeakZombieB'),
       ('WeakZombieC', 'ZombieC', 'WeakZombieB', 'Zombie', 'ZombieB'),
       ('Zombie', 'ZombieB', 'Shield', 'ZombieC', 'WeakZombie'))


def _crescent(kinds, centre, at, distance=10.0, width=80.0):
    """A crowd spread along an arc `width` degrees wide, arriving together: one shell's cone (fifty degrees
    either side) holds all of it, and nothing else."""
    n = len(kinds)
    return [(k, centre - width / 2.0 + i * width / (n - 1), distance + (i % 2) * 0.5, at + 0.2 * i)
            for i, k in enumerate(kinds)]


PLISTS['port_encore_1'] = _wave(
    _crescent(_C5[0], 20, 0.0)
    + [('Runner', 200, 11.0, 6.0)]
    + _crescent(_C5[1], 150, 12.0)
    + [('RunnerB', 330, 11.0, 16.0)]
    + _crescent(_C5[2], 240, 24.0)
    + [('Runner', 80, 11.0, 27.0)], no_blast=True)
_H5S = (('Zombie', 'ZombieB', 'Hulk', 'ZombieC', 'Zombie'), ('ZombieB', 'Zombie', 'HulkB', 'ZombieC', 'WeakZombie'))
PLISTS['port_encore_2'] = _wave(
    _crescent(_C5[0], 330, 0.0, 9.0)
    + [('Runner', 170, 11.0, 1.5)]
    + _crescent(_C5[3], 110, 5.0, 9.0)
    + [('RunnerB', 250, 11.0, 6.5)]
    + _crescent(_H5S[0], 200, 10.0, 9.0)
    + [('Runner', 30, 11.0, 11.5)]
    + _crescent(_C5[2], 60, 15.0, 9.0)
    + [('RunnerC', 230, 11.0, 16.5)]
    + _crescent(_C5[1], 300, 20.0, 9.0), no_blast=True)
PLISTS['port_encore_3'] = _wave(
    _crescent(_C5[1], 10, 0.0, 9.0)
    + [('Runner', 190, 11.0, 1.5)]
    + _crescent(_H5S[0], 130, 5.0, 9.0)
    + [('RunnerB', 300, 11.0, 6.5)]
    + _crescent(_C5[3], 240, 10.0, 9.0)
    + [('Runner', 60, 11.0, 11.5)]
    + _crescent(_C5[2], 340, 15.0, 9.0)
    + [('RunnerC', 160, 11.0, 16.5)]
    + _crescent(_H5S[1], 100, 20.0, 9.0)
    + [('Runner', 220, 11.0, 21.5)]
    + _crescent(_C5[0], 200, 25.0, 9.0)
    + [('RunnerB', 20, 11.0, 26.5)]
    + _crescent(_C5[3], 320, 30.0, 9.0), no_blast=True)
PLISTS['port_encore'] = {
    'challenge_id': 'port_encore',
    'title': 'Encore',
    'objective': 'They come in a line across the front, and something always comes back for more.',
    'tip': 'The shotgun takes a long time to load, and the banjo will not wait for it to finish.',
    'icon': 'Challenge_icon_02', 'icon_title': 'EN',
    'weapons': [{'name': 'policeshotgun', 'ammo': '999'}, {'name': 'banjo'}],
    'bricks': ['port_encore_1', 'port_encore_2', 'port_encore_3'],
    'ambient': {'ambientPlaylist': 'ambient_ghosttown', 'gain': 0.5},
    'time_limit_star': {'reward': 550, 'objective': 140},
    'accuracy_star': {'reward': 550, 'objective': 75},
}

_P4 = (('Zombie', 'ZombieB', 'ZombieC', 'Zombie'), ('WeakZombie', 'Zombie', 'WeakZombieC', 'ZombieB'),
       ('ZombieC', 'Zombie', 'ZombieB', 'WeakZombie'), ('ZombieB', 'WeakZombieC', 'Zombie', 'ZombieC'))

#: The Bazooka: 45 flat into everything within five units of where the rocket lands (60 at level four) and 60
#: at the centre (80), which is any pack in one rocket and a Hulk in two - and fifteen units of range, four
#: more than any other gun.  So everything here stands up at twelve to fourteen units, where nothing else in
#: the shop reaches, and walks in from there.
#:
#: What makes it an arena is that the rocket is slow.  It flies at four units a second along the way the
#: player faces and goes off where the target will be (`create_projectile_for_current_weapon`): 2.7 seconds
#: to a pack at twelve units, time in which a Runner covers three and a half.  A rocket at anything inside
#: five units rings the ears for up to thirteen seconds (`start_tinitus_with_intensity`, intensity 1 - d^2/25),
#: and it goes to the nearest thing within thirty degrees (`target_enemi_for_explosive_weapon`), so a pack
#: let in close is both loud and in the way of the one behind it.  Fired early, every rocket lands out beyond
#: seven units and the arena is quiet; fired late, it is not.  Five rockets and a two-and-a-half-second
#: reload set the pace.
#:
#: Packs of four walk six degrees apart (four units across at thirteen out, inside one blast).  Heavies: Hulks
#: alone and in pairs (a pair is three rockets at level one, two at four), a Riot Gear Zombie escorted by
#: Rejects (a blast goes through its shield; the first rocket takes the escort, two more the Shield), Zombie
#: Dogs alone or together (a blast does not make them sidestep), a Chainsaw whose circling puts the rocket a
#: unit or two off.  Runner packs start at fourteen units, each on its own.  Nothing that must be rocketed
#: stands within twenty-five degrees of bearing 270, where `target_enemi_for_explosive_weapon` cannot see
#: across the seam (handbook 1.1).
PLISTS['port_artillery_1'] = _wave(
    _pack(_P4[0], 30, 13.0, 0.0, spread=5.0)
    + [('Hulk', 150, 13.0, 6.0)]
    + _pack(_P4[1], 215, 14.0, 12.0, spread=5.0)
    + _pack(_R3, 330, 14.0, 21.0, spread=4.0)
    + _pack(_P4[2], 90, 13.0, 27.0, spread=5.0)
    + _pack(('Hulk', 'HulkB'), 190, 13.0, 32.0), no_blast=True)
PLISTS['port_artillery_2'] = _wave(
    _pack(_P4[3], 45, 13.0, 0.0, spread=5.0) + _pack(_P4[0], 135, 13.0, 0.5, spread=5.0)
    + [('Dodge', 225, 14.0, 8.7)]
    + _pack(('Hulk', 'HulkB'), 320, 13.0, 11.6)
    + _escort(('WeakZombie', 'WeakZombieB', 'WeakZombieC', 'WeakZombie'), 'Shield', 70, 13.0, 11.7)
    + _pack(_R3, 100, 14.0, 27.4, spread=4.0)
    + [('Chainsaw', 200, 12.0, 26.7)]
    + _pack(('Zombie', 'WeakZombie', 'ZombieB', 'ZombieC', 'WeakZombieC'), 20, 13.0, 26.4, spread=7.0)
    + _pack(_P4[1], 160, 13.0, 30.4, spread=5.0)
    + [('Hulk', 235, 13.0, 36.6)], no_blast=True)
PLISTS['port_artillery_3'] = _wave(
    _pack(_P4[2], 60, 12.0, 0.0, spread=5.0) + _pack(('Hulk', 'HulkB'), 60, 14.0, 0.0)
    + _pack(_P4[0], 200, 13.0, 2.4, spread=5.0)
    + _pack(_R3, 150, 14.0, 17.4, spread=4.0)
    + _escort(('WeakZombie', 'WeakZombieB', 'WeakZombieC', 'WeakZombie'), 'Shield', 310, 13.0, 13.0)
    + [('Dodge', 225, 14.0, 22.7), ('DodgeB', 235, 14.0, 23.0)]
    + _pack(_P4[3], 20, 13.0, 21.4, spread=5.0) + _pack(_P4[1], 110, 12.0, 29.9, spread=5.0) + _pack(('Hulk', 'HulkB'), 110, 14.0, 29.9)
    + _pack(('Hulk', 'HulkB'), 180, 13.0, 27.0)
    + _pack(_R3, 80, 14.0, 44.5, spread=4.0)
    + _escort(('WeakZombieC', 'WeakZombie', 'WeakZombieB', 'WeakZombieC'), 'Shield', 330, 13.0, 40.5), no_blast=True)
PLISTS['port_artillery'] = {
    'challenge_id': 'port_artillery',
    'title': 'Artillery',
    'objective': 'They stand up at the edge of hearing, out of reach of every gun you own but this one.',
    'tip': 'A rocket takes its time getting there, and it is loud when it does. The further off it lands, '
           'the less of it you hear.',
    'icon': 'Challenge_icon_02', 'icon_title': 'AT',
    'weapons': [{'name': 'bazooka', 'ammo': '75'}, {'name': 'wok'}],
    'bricks': ['port_artillery_1', 'port_artillery_2', 'port_artillery_3'],
    'ambient': {'ambientPlaylist': 'ambient_ruins', 'gain': 0.5},
    'time_limit_star': {'reward': 500, 'objective': 230},
    'accuracy_star': {'reward': 500, 'objective': 85},
}

#: The Bazooka's one cost, as an arena.  A rocket kills anything light in one and leads a walker exactly
#: (`create_projectile_for_current_weapon`: it lands where the target will be), but a blast centred inside five
#: units of the player rings the ears for `10 * (1 - d^2/25) + 3` seconds, adding up to twenty
#: (`solve_explosion_with_dictionary`, `start_tinitus_with_intensity`) - and in a game played by ear, twenty
#: seconds of ringing is twenty seconds half deaf.  Everything here arrives six and a half to eight units out,
#: which leaves a Zombie about four seconds before a rocket at it lands inside five.
#:
#: Each wave has a crunch: more than a clip's worth arriving in six or seven seconds from all round - pairs of
#: Zombies (a rocket each), Hulk pairs (two), Riot Gear Zombies (three; a blast goes through the shield and
#: makes it stand still for seven seconds), fifteen to seventeen rockets against five a clip and a 2.5-second
#: reload.  Fired as they come, most of them land close.  The answer is in the crate each wave brings
#: (`PowerUp` `force_spawn_time`, a **Tornado**, never used before): four gusts over ten seconds, each pushing
#: everything outward a quarter of `blowDistance` (`TornadoPowerUp.play_random_wind`, `blow_enemies_away`) -
#: five units in all at level four, which holds a Zombie still for ten seconds, and one at level one.  So the
#: crate is a matter of when: it beeps five units out from seven to ten seconds into each wave - as wave 1's
#: crunch begins, a few seconds before the others'.  Opened at once, the wind blows itself out while the crunch is
#: still coming; opened as the first pair arrives, it keeps the whole crunch out past five units while the
#: launcher is reloaded.  It has one life and the revolver has six rounds, so opening it costs a bullet and two
#: weapon switches, not a rocket landing five units away.  A crate stops any power-up still running when it
#: appears, and there is one a wave, long after the last one's wind is gone.
#:
#: The melee weapon is the Claymore, on purpose and not to be used in a crowd: at level four the wok is
#: 25 a quarter-second and would make "too close" harmless, and then the arena would have no idea left.  The
#: Claymore is for one thing that got in.  The Runner pairs, the Dodges and the late crowds come on their own,
#: after each crunch is over.
#:
#: Measured with the referee (C1's player; 10 runs a rung, 2026-09-30): level 4 wins 100 90 90 100 70 80 % at
#: R = 0.6 .. 1.6 s, difficulty 1.72, with the ears ringing for the whole twenty-second cap in most runs.
#: Without the crates: 80 and 70 % at R = 1.0 and 1.4 against 90 and 70 %.  The referee opens a crate the
#: moment it can and models ringing ears only as slower reactions, so it undervalues the wind.

_TRIOS = (('Zombie', 'ZombieB', 'ZombieC'), ('ZombieB', 'ZombieC', 'Zombie'), ('ZombieC', 'Zombie', 'ZombieB'),
       ('ZombieB', 'WeakZombie', 'Zombie'))
_P2 = (('Zombie', 'ZombieB'), ('ZombieC', 'Zombie'), ('ZombieB', 'ZombieC'), ('Zombie', 'WeakZombie'))
_HH = ('Hulk', 'HulkB')
_R2 = ('Runner', 'RunnerB')


def _near(kinds, bearing, at, distance=8.0):
    """A crowd that arrives close: from eight units, about five seconds before a rocket landing on it rings
    the ears; from seven and a half, about four."""
    return _pack(kinds, bearing, distance, at, spread=8.0)


def _crate(wave, at):
    wave['PowerUp'] = {'force_spawn_time': at, 'type': 'tornado'}
    return wave


PLISTS['port_blowback_1'] = _crate(_wave(
    _near(_TRIOS[0], 40, 0.0)
    + _near(_TRIOS[1], 160, 4.0)
    + _near(_P2[2], 300, 10.0, 7.0)
    + _near(_P2[3], 100, 11.3, 7.0)
    + _near(_P2[0], 220, 12.6, 7.0)
    + _near(_P2[1], 20, 13.9, 7.0)
    + _pack(_HH, 180, 9.0, 16.0)
    + _near(_TRIOS[2], 320, 26.0), no_blast=True), 3.0)
PLISTS['port_blowback_2'] = _crate(_wave(
    _near(_TRIOS[0], 0, 0.0)
    + _near(_TRIOS[1], 130, 3.0)
    + _pack(_HH, 240, 9.0, 5.0)
    + _near(_P2[2], 60, 13.0, 6.5)
    + _escort(('Zombie', 'ZombieB'), 'Shield', 200, 6.5, 14.0)
    + _pack(_HH, 320, 7.0, 15.0)
    + [('Shield', 110, 6.5, 16.0)]
    + _near(_P2[0], 230, 17.0, 6.5)
    + _pack(_HH, 20, 7.0, 18.0)
    + _escort(('ZombieC', 'Zombie'), 'Shield', 160, 6.5, 19.0)
    + _pack(_R2, 290, 11.0, 30.0, spread=5.0)
    + _near(_TRIOS[3], 90, 33.0), no_blast=True), 2.5)
PLISTS['port_blowback_3'] = _crate(_wave(
    _near(_TRIOS[0], 20, 0.0)
    + [('Dodge', 150, 9.0, 2.0)]
    + _near(_TRIOS[1], 250, 8.0)
    + _escort(('ZombieB', 'Zombie'), 'Shield', 290, 6.5, 15.0)
    + _pack(_HH, 60, 7.0, 16.0)
    + _near(_P2[2], 180, 17.0, 6.5)
    + [('Shield', 330, 6.5, 18.0)]
    + _pack(_HH, 110, 7.0, 19.0)
    + _escort(('ZombieC', 'Zombie'), 'Shield', 0, 6.5, 20.0)
    + _near(_P2[1], 220, 21.0, 6.5)
    + _pack(_HH, 140, 7.0, 22.0)
    + _pack(_R2, 210, 11.0, 31.0, spread=5.0)
    + _near(_TRIOS[3], 90, 34.0)
    + _near(_TRIOS[0], 300, 37.0)
    + [('Dodge', 30, 11.0, 40.0)], no_blast=True), 0.5)
PLISTS['port_blowback'] = {
    'challenge_id': 'port_blowback',
    'title': 'Blowback',
    'objective': 'They arrive close, and a rocket that lands close is heard for a long time afterwards. Six '
                 'rounds for whatever needs less than a rocket.',
    'tip': 'Five rockets are not always enough, and the wind does not care whom it pushes. Let it in just '
           'before you need the room.',
    'icon': 'Challenge_icon_02', 'icon_title': 'BW',
    'weapons': [{'name': 'bazooka', 'ammo': '999'}, {'name': 'pistol', 'ammo': '6'}, {'name': 'claymore'}],
    'bricks': ['port_blowback_1', 'port_blowback_2', 'port_blowback_3'],
    'ambient': {'ambientPlaylist': 'ambient_foundry', 'gain': 0.5},
    'time_limit_star': {'reward': 500, 'objective': 140},
    'accuracy_star': {'reward': 500, 'objective': 70},
}

#: The Bazooka against the one thing it was made for: five hundred life at a quarter of a unit a second.  A
#: rocket does 45 flat to everything within five units at level one and 60 near the centre, 60 and 80 at
#: level four (`hit_by_explosion` 0x100061284, whose falloff cancels the radius), so a Colossus walking
#: straight in takes nine rockets on target at level one and seven at level four - two clips and a reload,
#: ten seconds of nothing else, twice a wave.  Nothing but the Bazooka reaches it where it starts (range
#: 15, every other gun 11), and it walks in from eleven and a half units in 45 seconds, so the clock is its
#: own and slow; what makes the arena is everything that does not wait for it.
#:
#: The trick is the blast's five units.  `target_enemi_for_explosive_weapon` 0x1000c57b8 sends a rocket to
#: the nearest thing within thirty degrees, and crowds walk in on a Colossus's own bearing a little behind
#: it (`_beside`): at 0.5 against 0.25 they catch it up and walk past it, inside five units of it the whole
#: way in.  A rocket at the Colossus lands among them, and one at them lands on it - so time spent on a
#: Colossus is never time taken from its crowd, and a crowd on its own bearing costs nothing.  What costs is
#: the rest: crowds, Hulk pairs, a Chainsaw, a Dodge and pairs of Runners from the other bearings, which pull
#: the player off a Colossus that is still walking.  A rocket does not make a Dodge step aside, and it goes
#: through a raised shield, so the Riot Gear Zombie in wave 3 walks in one of the Colossus's crowds.
#:
#: Spaced (the chapter 4 rules): the Runner pairs, the Dodges and the Chainsaws each come within five units
#: about five seconds after the fast one before, never two at once, and never while a crowd is on top of
#: the player; the second Colossus of waves 2 and 3 comes three and four seconds after the first, so they do
#: not arrive together.  The Police Shotgun is for whatever gets inside five units, where a rocket rings the
#: ears.  No Berserk: a shotgun is in hand.
#:
#: Measured with the referee (C1's player, which fires the Police Shotgun and the Bazooka as they are meant
#: to be fired; 10 runs a rung, 2026-09-30): level 4 wins 100 90 80 80 90 60 % at R = 0.6 .. 1.6 s,
#: difficulty 1.64.  Nearly every loss is a Colossus left too long - loud, slow and fair.  Level 1: see the
#: report.


def _beside(kinds, bearing, at):
    """A crowd walking in with a Colossus: on its bearing, a little further out, and faster (0.5 against
    0.25), so it catches the Colossus up and walks past it, inside five units of it the whole way in."""
    return _pack(kinds, bearing, 13.5, at, spread=8.0)


PLISTS['port_titans_1'] = _wave(
    [('Colossus', 330, 12.0, 0.0)]
    + _beside(_TRIOS[0], 330, 4.0)
    + _pack(_TRIOS[1], 150, 10.0, 8.0)
    + _beside(_TRIOS[2], 330, 13.0)
    + _pack(_TRIOS[3], 60, 10.0, 17.0)
    + _pack(_R2, 210, 11.0, 24.0, spread=5.0)
    + _beside(_TRIOS[0], 330, 25.0), no_blast=True)
PLISTS['port_titans_2'] = _wave(
    [('Colossus', 30, 11.0, 0.0), ('Colossus', 200, 11.0, 3.0)]
    + _beside(_TRIOS[0], 30, 3.5)
    + _pack(_TRIOS[1], 110, 10.0, 6.0)
    + _beside(_TRIOS[2], 200, 7.5)
    + [('Chainsaw', 290, 10.0, 9.5)]
    + _pack(_HH, 120, 12.0, 13.0)
    + _beside(_TRIOS[3], 30, 14.5)
    + _pack(_R2, 250, 11.0, 19.5, spread=5.0)
    + _beside(_TRIOS[0], 200, 19.5)
    + [('Dodge', 340, 11.0, 21.5)]
    + _pack(_HH, 330, 12.0, 17.0)
    + _pack(_TRIOS[1], 160, 10.0, 24.5)
    + _pack(_R2, 80, 11.0, 31.0, spread=5.0), no_blast=True)
PLISTS['port_titans_3'] = _wave(
    [('Colossus', 20, 11.5, 0.0), ('Colossus', 150, 11.5, 4.0)]
    + _beside(_TRIOS[0], 20, 3.5)
    + _beside(('ZombieB', 'Shield', 'Zombie'), 150, 7.0)
    + _pack(_R2, 250, 11.0, 8.0, spread=5.0)
    + _pack(_TRIOS[2], 85, 10.0, 10.0)
    + [('Dodge', 300, 11.0, 10.0)]
    + _beside(_TRIOS[3], 20, 13.5)
    + [('Chainsaw', 110, 10.0, 13.5)]
    + _pack(_HH, 210, 12.0, 14.5)
    + _beside(_TRIOS[0], 150, 18.5)
    + _pack(_HH, 60, 12.0, 20.0)
    + _pack(_R2, 330, 11.0, 24.0, spread=5.0)
    + _beside(_TRIOS[1], 20, 24.0)
    + [('Dodge', 190, 11.0, 25.5)]
    + _pack(_TRIOS[2], 240, 10.0, 27.0)
    + [('Chainsaw', 250, 10.0, 29.0)]
    + _escort(('Zombie', 'ZombieB'), 'Shield', 120, 12.0, 33.0)
    + _pack(_R2, 70, 11.0, 39.5, spread=5.0), no_blast=True)
PLISTS['port_titans'] = {
    'challenge_id': 'port_titans',
    'title': 'Titans',
    'objective': 'Two of the biggest things out there, and a launcher to answer them. Nothing else will wait '
                 'while you do.',
    'tip': 'They are slow, and they do not walk alone. What walks beside them is standing where the rockets '
           'land.',
    'icon': 'Challenge_icon_02', 'icon_title': 'TI',
    'weapons': [{'name': 'bazooka', 'ammo': '999'}, {'name': 'policeshotgun', 'ammo': '999'}, {'name': 'wok'}],
    'bricks': ['port_titans_1', 'port_titans_2', 'port_titans_3'],
    'ambient': {'ambientPlaylist': 'ambient_ruins', 'gain': 0.5},
    'time_limit_star': {'reward': 500, 'objective': 160},
    'accuracy_star': {'reward': 500, 'objective': 70},
}

#: Where each of a crowd walks relative to the dummy's bearing: parted round it, seven degrees or more
#: either side, so a revolver aimed at the dummy finds nothing nearer its aim.
_PARTED = {2: (-8.0, 8.0), 3: (-10.0, 7.0, 12.0), 4: (-13.0, -7.0, 7.0, 13.0)}


def _field(dummy: str, bearing: float, near: float, at: float) -> list:
    """A dummy standing `near` units out on `bearing`, from `at`: it never moves and never has to."""
    return [(dummy, bearing, near, at)]


def _parted(kinds, bearing: float, distance: float, at: float) -> list:
    """A crowd walking in either side of `bearing`, parted round whatever stands on it, a third of a second
    apart.  One rocket landing on any of them still takes the far side: thirteen degrees either side of the
    line is 4.5 units across at thirteen out, inside the blast's five."""
    return [(k, bearing + _PARTED[len(kinds)][i], distance + (i % 2) * 0.5, round(at + 0.3 * i, 2))
            for i, k in enumerate(kinds)]


def _shielded(bearing: float, distance: float, at: float) -> list:
    """Rejects walking round a Riot Gear Zombie, parted round the bearing like the rest; the Shield half a
    unit ahead of them, so it is the one a rocket finds."""
    return [('WeakZombie', bearing - 13.0, distance, at), ('WeakZombieB', bearing - 7.0, distance + 0.5, at + 0.3),
            ('Shield', bearing + 7.0, distance - 0.5, at), ('WeakZombieC', bearing + 13.0, distance, at + 0.6),
            ('WeakZombie', bearing + 19.0, distance + 0.5, at + 0.9)]


#: Artillery's rocket, and the thing about it that Artillery only hints at: it goes to the **nearest** thing
#: within thirty degrees of the aim (`target_enemi_for_explosive_weapon`), and flies along the aim, not
#: towards what it meant.  So here Bob, Jim and Ted - the tutorial's dummies, one life, ten and ten, standing
#: still for ever - stand four and a half to six units out in front of the crowds.  A rocket aimed at the
#: crowd lands on the dummy: one rocket gone, the crowd untouched, and a blast at four and a half units rings
#: the ears for five seconds (intensity 1 - d^2/25).  The revolver is for them: Bob dies to anything, Jim and
#: Ted to one shot at level four and to a centred one at level one (9.9 off-centre leaves them a tenth of a
#: life).  Every switch costs a second (`Weapon.deploy`), so the arena is the order of things: find the
#: dummies, clear them, switch, fire.  They stand where they are loud enough to find - four to six units, a
#: Ted louder than a Zombie across the arena, a Jim six decibels under one - and the wave waits for them
#: (`Brick` ends only when every `Enemies` entry is dead), including a Bob in wave 3 that stands in front of
#: nothing at all.
#:
#: Each crowd is parted round its dummy (`_parted`): seven degrees or more either side, so a revolver aimed
#: at the dummy has nothing nearer its aim to hit instead, and a crowd thirteen degrees either side is still
#: one rocket (4.5 units across at thirteen out).  Aiming thirty degrees off to miss the dummy puts the rocket
#: seventeen or more off the crowd, which it then misses.  Rockets are counted (32), and so are the rounds
#: (36): enough for every dummy twice over and a few more, and nowhere near enough for the crowds, which the
#: rocket has to take.  The melee weapon is the Claymore, which a player has from chapter 4: it is for the one
#: that gets through, and it locks everything else for a second and a half at level four.  Nothing stands
#: within thirty degrees of bearing 270, where a rocket cannot see across the seam.
PLISTS['port_scarecrows_1'] = _wave(
    _field('Bob', 40, 4.5, 0.0) + _parted(_P4[0], 40, 13.0, 2.0)
    + _field('Jim', 160, 4.5, 9.0) + _parted(_P4[1], 160, 13.0, 11.0)
    + _parted(_P4[2], 220, 13.0, 18.0)
    + _field('Ted', 330, 4.5, 24.0) + _parted(('Hulk', 'HulkB'), 330, 13.0, 26.0), no_blast=True)
#: The one paying Diamond of the arena (key exactly 'Diamond', so `Enemy.die` pays it; `_wave` would number it):
#: 5.5 units out at bearing 100, sixty degrees from every crowd of the wave so no rocket meant for one can
#: find it, arriving in the lull after the second crowd.  Its glow is quiet (-26 dB), so it is a reward and
#: a wave lock that waits for a quiet moment, never the thing in the way.
PLISTS['port_scarecrows_1']['Enemies']['Diamond'] = {'spawn_angle': 100.0, 'spawn_distance': 5.5, 'spawn_time': 16.0}
PLISTS['port_scarecrows_2'] = _wave(
    _field('Bob', 80, 4.5, 0.0) + _field('Ted', 350, 5.0, 0.5)
    + _parted(_P4[3], 80, 13.0, 3.0) + _parted(_P4[0], 350, 13.0, 6.0)
    + _field('Jim', 200, 4.5, 10.0) + _parted(_R3, 200, 14.0, 13.0)
    + _field('Bob', 120, 5.0, 15.0)
    + _parted(_P4[1], 100, 13.0, 17.0) + _parted(_P4[2], 140, 13.0, 21.0)
    + [('Hulk', 20, 13.0, 25.0)], no_blast=True)
PLISTS['port_scarecrows_3'] = _wave(
    _parted(_P4[0], 30, 13.0, 0.0) + _field('Ted', 30, 4.5, 3.0)
    + _field('Jim', 150, 4.5, 4.0) + _parted(('Hulk', 'HulkB'), 150, 14.0, 6.0)
    + _field('Bob', 225, 4.5, 11.0) + _parted(_R3, 225, 14.0, 14.0)
    + _field('Ted', 100, 4.5, 16.0) + _parted(('Hulk', 'HulkB'), 100, 13.0, 18.0)
    + _parted(_P4[1], 320, 13.0, 20.0)
    + _field('Jim', 190, 5.0, 25.0) + _shielded(190, 13.0, 27.0)
    + _field('Bob', 60, 6.0, 29.0)
    + _field('Jim', 310, 4.5, 33.0) + _parted(_R3, 310, 14.0, 36.0), no_blast=True)
PLISTS['port_scarecrows'] = {
    'challenge_id': 'port_scarecrows',
    'title': 'Scarecrows',
    'objective': 'Something stands close in front of every crowd out here. It will not move, and it will not '
                 'get out of the way.',
    'tip': 'A rocket is not particular: it takes the first thing in its way. Some things out here were put '
           'in the way.',
    'icon': 'Challenge_icon_02', 'icon_title': 'SC',
    'weapons': [{'name': 'bazooka', 'ammo': '32'}, {'name': 'pistol', 'ammo': '36'}, {'name': 'claymore'}],
    'bricks': ['port_scarecrows_1', 'port_scarecrows_2', 'port_scarecrows_3'],
    'ambient': {'ambientPlaylist': 'ambient_ghosttown', 'gain': 0.5},
    'time_limit_star': {'reward': 550, 'objective': 190},
    'accuracy_star': {'reward': 550, 'objective': 80},
}

#: Everything the chapter sent, and the three weapons it was fought with, all at once and each for its own
#: distance.  Crescents of Zombies at nine or ten units are the Police Shotgun's (every one of them inside its
#: fifty degrees, half damage kept at range).  Hulk pairs and Riot Gear escorts at twelve or thirteen units
#: are the Bazooka's, since nothing else reaches past eleven.  A rocket goes through a raised shield and
#: never sends a Dodge sideways, so the Dodges are the Bazooka's too.  The Runners that reach arm's length
#: are the golf club's: 50 a swing at level four, anything light in one, a quarter of a second between.
#: Switching between the two guns takes a second (`Weapon.deploy`), the club needs no switch but waits a
#: second after either gun's shot, so the arena is choosing by distance before choosing by target - and
#: hearing the distance, which every one of these is loud enough to give away.
#:
#: What each earlier arena taught is in here once: a Colossus in waves 2 and 3, twelve units out, walking in
#: while everything else does (Titans); Riot Gear Zombies walking in crescents, stopping behind their shields
#: while the line dies and coming on alone afterwards (Encore); a Tornado crate in wave 3 (Blowback), which a
#: shell fired on its side opens whether that was meant or not.  A Farty walks in the middle of a narrower
#: crescent: killed there, its 37.5 within three units takes the Zombies either side of it.  Killed at arm's
#: length, it rings the ears.  Waves 2 and 3 are Zombies throughout, two shells a crescent at level four
#: where a Reject needs one.
#:
#: Spaced by the rules the chapter 4 test made: the Runners and the Dodges come one at a time, each within
#: five units about five seconds after the fast one before, never in a pair from opposite sides.  The Dodges
#: come alone, the Riot Gear Zombies inside their crowds, and there is no Berserk, because a shotgun is in hand.
#:
#: Measured with the referee (C1's player; 10 runs a rung, 2026-09-30): level 4 wins 100 100 80 60 50 50 % at
#: R = 0.6 .. 1.6 s, difficulty 1.60, the lowest middle rungs of the chapter's second half.  Its losses are
#: spread over Hulks, Riot Gear Zombies, Runners and crowds, never one moment.

_RC5 = (('Zombie', 'WeakZombie', 'ZombieB', 'WeakZombieC', 'ZombieC'),
       ('ZombieB', 'Zombie', 'WeakZombie', 'ZombieC', 'WeakZombieB'),
       ('WeakZombieC', 'ZombieC', 'QuietZombie', 'Zombie', 'ZombieB'),
       ('Zombie', 'ZombieB', 'Hulk', 'ZombieC', 'Zombie'))
_FARTY = ('ZombieB', 'Zombie', 'Farty', 'ZombieC', 'Zombie')


def _far(kinds, bearing, at, distance=12.0):
    """Heavies twelve units out: beyond every gun but the Bazooka."""
    return _pack(kinds, bearing, distance, at, spread=6.0)


_H5 = ('ZombieB', 'Zombie', 'HulkB', 'ZombieC', 'Zombie')
_Z5 = (('Zombie', 'ZombieB', 'ZombieC', 'Zombie', 'ZombieB'),
       ('ZombieC', 'Zombie', 'ZombieB', 'ZombieC', 'Zombie'))
_S5 = ('Zombie', 'ZombieB', 'Shield', 'ZombieC', 'Zombie')
PLISTS['port_riotact_1'] = _wave(
    _crescent(_RC5[0], 30, 0.0)
    + _far(_HH, 200, 2.0, 13.0)
    + [('Runner', 120, 11.0, 5.0)]
    + _crescent(_RC5[1], 300, 6.5)
    + _escort(('Zombie', 'ZombieB'), 'Shield', 160, 12.0, 9.0)
    + [('RunnerB', 60, 11.0, 12.5)]
    + _crescent(_RC5[2], 220, 15.0)
    + [('Dodge', 330, 11.0, 18.5)], no_blast=True)
PLISTS['port_riotact_2'] = _wave(
    [('Colossus', 20, 12.0, 0.0)]
    + _crescent(_Z5[0], 180, 1.5, 9.5)
    + [('Dodge', 290, 11.0, 4.5)]
    + _crescent(_FARTY, 100, 6.5, 9.5, 60.0)
    + _far(_HH, 330, 10.0)
    + [('Runner', 220, 11.0, 13.0)]
    + _crescent(_H5, 240, 13.0, 9.5)
    + _crescent(_S5, 140, 18.0, 9.5)
    + [('RunnerC', 60, 11.0, 18.5)]
    + _far(_HH, 200, 21.0)
    + _crescent(_RC5[3], 90, 24.0, 9.5)
    + [('Runner', 300, 11.0, 24.0)], no_blast=True)
PLISTS['port_riotact_3'] = _wave(
    [('Colossus', 320, 12.0, 0.0)]
    + _crescent(_Z5[0], 0, 0.0, 9.5)
    + _far(_HH, 90, 1.5)
    + _crescent(_Z5[1], 180, 4.0, 9.5)
    + [('Runner', 250, 11.0, 5.0)]
    + [('Dodge', 130, 11.0, 6.0)]
    + _escort(('ZombieC', 'Zombie'), 'Shield', 300, 12.0, 6.5)
    + _crescent(_RC5[3], 50, 9.5, 9.5)
    + _crescent(_FARTY, 230, 13.0, 9.5, 60.0)
    + _far(_HH, 340, 14.0)
    + [('Runner', 200, 11.0, 14.5)]
    + _crescent(_S5, 110, 17.5, 9.5)
    + [('RunnerB', 20, 11.0, 19.0)]
    + [('Dodge', 60, 11.0, 20.0)]
    + _crescent(_Z5[0], 200, 22.0, 9.5)
    + _escort(('ZombieB', 'Zombie'), 'Shield', 40, 12.0, 23.0)
    + _crescent(_H5, 150, 26.5, 9.5)
    + [('RunnerC', 300, 11.0, 29.0)], no_blast=True)
PLISTS['port_riotact_3']['PowerUp'] = {'force_spawn_time': 8.0, 'type': 'tornado'}
PLISTS['port_riotact'] = {
    'challenge_id': 'port_riotact',
    'title': 'Riot Act',
    'objective': 'Everything this chapter sent, from every side and every distance, and three ways to answer '
                 'it.',
    'tip': 'Each of them is loud about where it is. Choose the weapon by the distance before you choose the '
           'target.',
    'icon': 'Challenge_icon_02', 'icon_title': 'RA',
    'weapons': [{'name': 'policeshotgun', 'ammo': '999'}, {'name': 'bazooka', 'ammo': '999'}, {'name': 'golf'}],
    'bricks': ['port_riotact_1', 'port_riotact_2', 'port_riotact_3'],
    'ambient': {'ambientPlaylist': 'ambient_roman', 'gain': 0.5},
    'time_limit_star': {'reward': 600, 'objective': 170},
    'accuracy_star': {'reward': 600, 'objective': 70},
}

#: How fast the kinds that do not walk at 0.5 close in, in units a second.
_SPEED = {'Hulk': 0.75, 'HulkB': 0.75, 'Runner': 1.3, 'RunnerB': 1.3, 'RunnerC': 1.3}


def _slots(slots, first: float, every: float) -> list:
    """Groups that come within five units `every` seconds apart, the first at `first`.  Each slot is
    `(group, bearing)`, `(group, bearing, distance)` for one walking in from further off, or None for a quiet
    one; a group is a pack (a tuple of kinds) walking in from ten units, one kind on its own from eleven, or
    'Shield', a Riot Gear Zombie walking in the middle of three Zombies (`_escort`).  The spawn times are
    worked back from the moment the first of the group would reach five units on its shortest arrival
    sound (`_ARRIVE`)."""
    out = []
    for i, slot in enumerate(slots):
        if slot is None:
            continue
        group, bearing = slot[:2]
        if group == 'Shield':
            at = round(max(0.0, first + i * every - (1.25 + 10.0)), 2)
            out += _escort(('Zombie', 'ZombieB', 'ZombieC'), 'Shield', bearing, 10.0, at)
            continue
        kinds = group if isinstance(group, tuple) else (group,)
        dist = slot[2] if len(slot) > 2 else (10.0 if isinstance(group, tuple) else 11.0)
        lead = min(_ARRIVE[k] + (dist - 5.0) / _SPEED.get(k, 0.5) for k in kinds)
        at = round(max(0.0, first + i * every - lead), 2)
        out += _pack(group, bearing, dist, at) if isinstance(group, tuple) else [(group, bearing, dist, at)]
    return out

#: The shortest arrival sound and the walking speed of each kind used (handbook 4.1), for `_slots`.


_BELT4 = (('Zombie', 'ZombieB', 'WeakZombie', 'ZombieC'), ('ZombieB', 'WeakZombieB', 'Zombie', 'Zombie'),
       ('ZombieC', 'Zombie', 'QuietZombie', 'ZombieB'))
_BELT5 = (('Zombie', 'ZombieB', 'WeakZombieC', 'ZombieC', 'Zombie'),
       ('ZombieB', 'Zombie', 'QuietZombie', 'ZombieC', 'ZombieB'),
       ('ZombieC', 'WeakZombie', 'Zombie', 'ZombieB', 'Zombie'))
_BELT_H3 = ('Hulk', 'HulkB', 'Hulk')

# ------------------------------------------------------------------------------------------------ Belt Fed
#: The Machine Gun, which no arena had handed out.  Held down it fires every 0.2 s at twenty degrees either
#: side rather than thirty (`Weapon.spread` answers `continuous_spread` in state 3): 16 a round at level four
#: and a hundred rounds to a belt, 10 and fifty at level one.  Then `reloadTime` 6, the longest in the game,
#: with nothing else in hand but a wok - and a swing throws a reload away (`shoot_with_melee`).
#:
#: So the arena is bursts and the quiet between them.  Groups come within five units four and a half to five
#: seconds apart (`_slots` works each spawn time back from that moment, on the shorter arrival sound): packs
#: of four and five, and Hulks in twos and threes, and at level four a burst is about a belt.  Between bursts
#: nothing comes but one Runner on its own, ten seconds clear of everything else, and that is where a belt
#: goes in.  A belt changed in the middle of a burst is six seconds of a pack and a Hulk trio walking in
#: untouched.  The gun says when it is nearly out: under held fire `_warningloop` sounds once the clip is
#: down to its last fifth (`running_low`), which is the moment to finish what is in front and change it.
#:
#: No Chainsaws, Dodges or Berserks.  The fast ones come alone, and nothing here minds being hit.
PLISTS['port_beltfed_1'] = _wave(_slots((
    (_BELT4[0], 20), (_BELT4[1], 140), ('Hulk', 260), (_BELT4[2], 80), (_HH, 200), (_BELT4[0], 320),
    None, ('Runner', 110), None,
    (_BELT5[0], 230), (_HH, 350), (_BELT4[1], 100), (_BELT5[1], 220)), 12.0, 5.0),
    no_blast=True)
PLISTS['port_beltfed_2'] = _wave(_slots((
    (_BELT5[0], 10), (_BELT_H3, 130), (_BELT5[1], 250), (_HH, 60), (_BELT5[2], 180), (_BELT_H3, 300),
    (_BELT5[0], 70), (_BELT_H3, 190),
    None, ('Runner', 310), None,
    (_BELT5[1], 90), (_BELT_H3, 210), (_BELT5[2], 330), (_HH, 150), (_BELT5[0], 270 + 15), (_BELT_H3, 40)),
    12.0, 4.5), no_blast=True)
PLISTS['port_beltfed_3'] = _wave(_slots((
    (_BELT5[0], 0), (_BELT_H3, 120), (_BELT5[1], 240), (_BELT_H3, 60), (_BELT5[2], 180), (_BELT_H3, 300),
    (_BELT5[0], 90), (_BELT_H3, 210),
    (_BELT5[1], 330), None, ('Runner', 100), None,
    (_BELT_H3, 220), (_BELT5[1], 340), (_BELT_H3, 160), (_BELT5[2], 40), (_BELT_H3, 270 + 15),
    (_BELT5[0], 150), (_BELT_H3, 30),
    (_BELT5[1], 250)), 12.0, 4.0),
    no_blast=True)
PLISTS['port_beltfed'] = {
    'challenge_id': 'port_beltfed',
    'title': 'Belt Fed',
    'objective': 'A gun that fires for as long as you hold it, and takes its time when it stops.',
    'tip': 'The belt tells you when it is nearly out. The quiet moments are the ones to spend on it.',
    'icon': 'Challenge_icon_02', 'icon_title': 'BF',
    'weapons': [{'name': 'machinegun', 'ammo': '999'}, {'name': 'wok'}],
    'bricks': ['port_beltfed_1', 'port_beltfed_2', 'port_beltfed_3'],
    'ambient': {'ambientPlaylist': 'ambient_ruins', 'gain': 0.5},
    'time_limit_star': {'reward': 600, 'objective': 300},
    'accuracy_star': {'reward': 600, 'objective': 55},
}

_Z4Q = ('ZombieB', 'QuietZombie', 'Zombie', 'ZombieC')
#: The Machine Gun and the Claymore: a gun that never stops and a blade that stops everything.  The gun is
#: the crowd's answer - held, it fires every 0.2 s into a cone narrowed to twenty degrees, 50 rounds to the
#: belt at level one and 100 at four - and it has two faults, both the original's.  The belt takes **six
#: seconds** to change (`reloadTime` 6, the longest in the game), and every surviving hit on a Dodge sends it
#: three and a half units sideways (`hit_by_weapon` 0x100060b30), which at anything under ten units is
#: outside a twenty degree cone: a belt spent on a Dodge is a belt spent making it dance.  The Claymore does
#: 85 at level four and a Dodge has 80, so one swing at arm's length ends it (70 at level one, 91 inside
#: its five degree precise cone); a Chainsaw has 70 and is one swing at any level.  But a swing locks the gun
#: for as long as it lasts (1.5 s at level four, 2.5 at one) and **throws away a belt change in progress**
#: (`shoot_with_melee`, kept from the original), so the two cannot be used at once, and the order is the
#: arena: blade first and then the belt, or the belt early while nothing is coming.
#:
#: Built to the chapter 4 rules: crowds in fours, a group coming within five units about every four seconds
#: and never more than ten in any eight; every Dodge and Chainsaw on its own between two crowds; Runners in
#: one small pack from one bearing, never two packs within 2.3 s of each other.  No Berserk (a belt held on
#: a crowd walking past one would find it) and no Riot Gear Zombie (inside three units it never raises its
#: shield, but it is three swings).  Hulks come in pairs from eleven units, and either roar (3.7 or 5.7 s)
#: puts them in reach between two other groups.
PLISTS['port_coldsteel_1'] = _wave(
    _pack(_Z4, 20, 10.0, 0.5)
    + _pack(_Z4, 150, 10.0, 5.5)
    + [('Dodge', 270, 11.0, 11.0)]
    + _pack(_Z4Q, 80, 10.0, 13.5)
    + [('Chainsaw', 200, 10.0, 17.5)]
    + _pack(_Z4, 320, 10.0, 21.5)
    + [('DodgeB', 110, 11.0, 27.0)]
    + _pack(_Z4, 240, 10.0, 29.5)
    + _pack(_R2, 30, 11.0, 39.0, spread=5.0), no_blast=True)
PLISTS['port_coldsteel_2'] = _wave(
    _pack(_Z4, 0, 10.0, 0.5)
    + _pack(_HH, 120, 11.0, 4.3)
    + [('Dodge', 240, 11.0, 13.0)]
    + _pack(_Z4, 190, 10.0, 15.5)
    + [('Chainsaw', 60, 10.0, 23.5)]
    + _pack(_R3, 300, 11.0, 24.9, spread=5.0)
    + _pack(_Z4Q, 100, 10.0, 27.5)
    + [('DodgeB', 210, 11.0, 33.0)]
    + _pack(_HH, 330, 11.0, 35.3)
    + _pack(_Z4, 150, 10.0, 42.5), no_blast=True)
PLISTS['port_coldsteel_3'] = _wave(
    _pack(_Z4, 30, 10.0, 0.5)
    + _pack(_HH, 200, 11.0, 4.3)
    + [('Dodge', 110, 11.0, 13.0)]
    + _pack(_Z4Q, 290, 10.0, 15.5)
    + [('Chainsaw', 240, 10.0, 23.5)]
    + _pack(_R3, 60, 11.0, 24.9, spread=5.0)
    + _pack(_HH, 160, 11.0, 27.3)
    + [('DodgeB', 330, 11.0, 36.0)]
    + _pack(_Z4, 250, 10.0, 38.5)
    + [('Chainsaw', 10, 10.0, 42.5)]
    + _pack(_R3, 190, 11.0, 51.9, spread=5.0)
    + _pack(_Z4Q, 300, 10.0, 50.5), no_blast=True)
PLISTS['port_coldsteel'] = {
    'challenge_id': 'port_coldsteel',
    'title': 'Cold Steel',
    'objective': 'A gun that does not stop, until it has to, and a blade for everything it cannot hold.',
    'tip': 'Some of them will not stand still for a belt, and the belt takes a long time to change. The '
           'blade takes one swing, and it does not wait for the belt.',
    'icon': 'Challenge_icon_02', 'icon_title': 'CS',
    'weapons': [{'name': 'machinegun', 'ammo': '999'}, {'name': 'claymore'}],
    'bricks': ['port_coldsteel_1', 'port_coldsteel_2', 'port_coldsteel_3'],
    'ambient': {'ambientPlaylist': 'ambient_ruins', 'gain': 0.5},
    'time_limit_star': {'reward': 600, 'objective': 200},
    'accuracy_star': {'reward': 600, 'objective': 55},
}

_JUG4 = (('Zombie', 'ZombieB', 'WeakZombie', 'ZombieC'), ('ZombieB', 'Zombie', 'QuietZombie', 'Zombie'),
       ('ZombieC', 'WeakZombieB', 'Zombie', 'ZombieB'))
_JUG5 = (('Zombie', 'ZombieB', 'WeakZombie', 'ZombieC', 'Zombie'),
       ('ZombieC', 'Zombie', 'QuietZombie', 'ZombieB', 'Zombie'))
_JUG_H3 = ('Hulk', 'HulkB', 'Hulk')

# ---------------------------------------------------------------------------------------------- Juggernaut
#: The Long Walk again, a chapter of guns later.  A Colossus is 500 life at a quarter of a unit a second, and
#: the Machine Gun at level four puts one down in about 35 rounds - seven seconds of holding the trigger, a
#: third of a belt (at level one it is more than a whole one).  So the half minute of revolver fire is gone
#: and what is left is the order of things: one, two and then three of them walk in from in front, ten units
#: out and some forty seconds from reaching the player, while the crowds come up from the half behind, a
#: group every four and a half to five seconds (`_slots`), Zombie packs and Hulks in twos and threes, and a
#: Runner alone in a gap.  The Colossi will wait; the crowd will not, and a Colossus started on a belt with
#: ten rounds left in it takes the six-second reload with it, with its back to the crowd.
PLISTS['port_juggernaut_1'] = _wave(
    [('Colossus', 0, 10.0, 0.0)]
    + _slots(((_JUG4[0], 180), (_JUG4[1], 225), (_HH, 140), (_JUG4[2], 200), None, ('Runner', 160), None,
              (_JUG5[0], 215), (_HH, 185), (_JUG4[0], 150)), 12.0, 5.0), no_blast=True)
PLISTS['port_juggernaut_2'] = _wave(
    [('Colossus', 330, 10.0, 0.0), ('Colossus', 40, 10.0, 8.0)]
    + _slots(((_JUG5[0], 190), (_JUG_H3, 150), (_JUG5[1], 230), (_HH, 170), None, ('Runner', 120), None,
              (_JUG5[1], 210), (_JUG_H3, 140), (_JUG5[0], 250), (_HH, 180),
              (_JUG5[1], 130)), 12.0, 4.5), no_blast=True)
PLISTS['port_juggernaut_3'] = _wave(
    [('Colossus', 0, 10.0, 0.0), ('Colossus', 65, 10.0, 6.0), ('Colossus', 295, 11.0, 16.0)]
    + _slots(((_JUG5[0], 180), (_JUG_H3, 225), (_JUG5[1], 135), (_JUG_H3, 200), None, ('Runner', 240), None,
              (_JUG5[0], 160), (_JUG_H3, 210), (_JUG5[1], 120), (_JUG_H3, 185), None, ('RunnerB', 150), None,
              (_JUG5[0], 230), (_JUG_H3, 170), (_JUG5[1], 205)), 12.0, 4.5), no_blast=True)
PLISTS['port_juggernaut'] = {
    'challenge_id': 'port_juggernaut',
    'title': 'Juggernaut',
    'objective': 'They are slow, they are enormous, and they did not come alone.',
    'tip': 'They are slow enough to wait until your belt is full. What comes up behind you is not.',
    'icon': 'Challenge_icon_02', 'icon_title': 'JG',
    'weapons': [{'name': 'machinegun', 'ammo': '999'}, {'name': 'wok'}],
    'bricks': ['port_juggernaut_1', 'port_juggernaut_2', 'port_juggernaut_3'],
    'ambient': {'ambientPlaylist': 'ambient_ruins', 'gain': 0.5},
    'time_limit_star': {'reward': 650, 'objective': 240},
    'accuracy_star': {'reward': 650, 'objective': 55},
}

def _noise(wave, **where):
    """Passers-by that stay for the rest of the challenge: kind -> (bearing, distance, spawn time)."""
    wave['PasserBy'] = {k: {'spawn_angle': float(a), 'spawn_distance': float(d), 'spawn_time': float(t)}
                        for k, (a, d, t) in where.items()}
    return wave


_RACKET4 = (('Zombie', 'ZombieB', 'WeakZombie', 'ZombieC'), ('ZombieB', 'WeakZombieB', 'Zombie', 'ZombieC'))
_RACKET5 = (('Zombie', 'ZombieB', 'WeakZombie', 'ZombieC', 'Zombie'),
       ('ZombieC', 'Zombie', 'WeakZombieB', 'ZombieB', 'Zombie'))
#: what walks in behind the noise: only the loud ones (no Rejects, no Whisperers)
_L4 = ('Zombie', 'ZombieC', 'ZombieB', 'Zombie')
_L5 = ('ZombieC', 'Zombie', 'ZombieB', 'ZombieC', 'Zombie')
_RACKET_H3 = ('Hulk', 'HulkB', 'Hulk')

# -------------------------------------------------------------------------------------------------- Racket
#: Finding things through noise.  `ambient_foundry` is the original's own factory floor, and on top of it a
#: Jukebox from the first wave (music at gain 6: from nine units, louder than a Zombie at three), the Machine
#: from the second (a loud loop, -16 dB at gain 3.5) and a second Jukebox from the third - passers-by stay
#: for the rest of the challenge, so they add up.  Some groups walk in on the noise's own bearing, from eleven
#: or twelve units, and cannot be told from it until they are five or six units out; so only loud ones walk
#: there (Zombies - no Rejects, no Whisperers, no Hulks and no Runners), and what comes from a clear bearing
#: is everything else.  Groups come within five units four and a half to five seconds apart (`_slots`).
#:
#: All of it can be quietened.  A round into a jukebox stops it for ten seconds (`JukeBox.hit_by_weapon`,
#: `pauseTime` 10); the Machine blown up - 130 life, nine rounds at level four, and seven units out, so its
#: blast (15 within three units) leaves the ears alone - stays gone for 35 to 54 seconds before it comes back
#: (`Machine.update`, state 502).  The Machine Gun, because it is the chapter's.
#: noise: a jukebox at 60 degrees (wave 1), the Machine at 200 (wave 2), a second jukebox at 300 (wave 3)
PLISTS['port_racket_1'] = _noise(_wave(_slots((
    (_RACKET4[0], 180), (_RACKET4[1], 300), (_L4, 60, 11.0), (_RACKET4[0], 240), ('Hulk', 120),
    (_L4, 60, 11.0),
    None, ('Runner', 200), None,
    (_RACKET5[0], 0), (_HH, 150), (_L5, 60, 11.0), (_RACKET5[1], 270 + 15)), 12.0, 5.0), no_blast=True),
    Jukebox=(60, 8.0, 1.0))
PLISTS['port_racket_2'] = _noise(_wave(_slots((
    (_RACKET5[0], 100), (_L4, 200, 12.0), (_RACKET_H3, 320), (_L5, 60, 11.0), (_HH, 160),
    None, ('Runner', 20), None,
    (_RACKET_H3, 250), (_L5, 200, 12.0), (_RACKET5[0], 290), (_L5, 60, 11.0), (_RACKET_H3, 130),
    None, ('RunnerB', 330), None,
    (_RACKET5[1], 0), (_L5, 200, 12.0), (_RACKET_H3, 100)), 12.0, 4.5), no_blast=True),
    Machine=(200, 7.0, 2.0))
PLISTS['port_racket_3'] = _noise(_wave(_slots((
    (_RACKET5[0], 0), (_L5, 300, 11.0), (_RACKET_H3, 150), (_L5, 200, 12.0), (_HH, 100), (_L5, 60, 11.0),
    (_RACKET_H3, 240),
    None, ('Runner', 130), None,
    (_RACKET5[1], 20), (_L5, 300, 11.0), (_RACKET_H3, 130), (_L5, 60, 11.0), (_HH, 250),
    None, ('RunnerC', 350), None,
    (_RACKET_H3, 110), (_L5, 200, 12.0), (_RACKET5[1], 150), (_L5, 300, 11.0),
    (_RACKET_H3, 20)), 12.0, 4.5), no_blast=True),
    Jukebox=(300, 9.0, 1.0))
PLISTS['port_racket'] = {
    'challenge_id': 'port_racket',
    'title': 'Racket',
    'objective': 'Music, machinery, and somewhere underneath it all, footsteps.',
    'tip': 'Everything out here can be made to be quiet for a while, even the music. Some of it stays quiet '
           'for longer than the rest.',
    'icon': 'Challenge_icon_02', 'icon_title': 'RK',
    'weapons': [{'name': 'machinegun', 'ammo': '999'}, {'name': 'wok'}],
    'bricks': ['port_racket_1', 'port_racket_2', 'port_racket_3'],
    'ambient': {'ambientPlaylist': 'ambient_foundry', 'gain': 0.5},
    'time_limit_star': {'reward': 700, 'objective': 330},
    'accuracy_star': {'reward': 650, 'objective': 50},
}

#: Collateral's lesson with the heaviest things in the game, and two guns that each get half of it wrong.
#: `hit_by_weapon` 0x100060b30 is what wakes a Berserk, sends a Dodge sideways and raises a Riot Gear
#: Zombie's shield; `hit_by_explosion` 0x100061284 does none of the three and goes straight through a shield
#: that is already up.  So the Tactical Rifle - forty rounds at level four, held fire every quarter second
#: into a twenty degree cone, a four second reload - is for the Hulks and the crowds that walk in the open,
#: and the Bazooka is for everything touchy: 80 where it lands and 60 to all within five units at level four
#: (60 and 45 at one), which is a Dodge in one rocket on target, a crowd of Zombies in one anywhere near, and
#: a Hulk pair in two.  It reaches fifteen units where the rifle reaches eleven, so the Hulks, which come from
#: thirteen, can be met early - at four units a second, a rocket there is three seconds in the air.
#:
#: Twenty-five rockets is not enough to use them on everything (every group by rocket is about 35), which is
#: the arena: the rifle for what can take a bullet, rockets for what cannot.  And a rocket goes to the
#: nearest thing within thirty degrees (`target_enemi_for_explosive_weapon`), which near a resting Berserk is
#: the Berserk - harmless: it lands on it without waking it, and the crowd walking past three units behind
#: takes the flat 60.  The rifle aimed at that crowd finds the Berserk instead.
#:
#: Where each special is, and why (the chapter 4 rules): a Berserk rests seven units out on a crowd's way in
#: (`_resting`) and leaves by itself; a Riot Gear Zombie walks inside its crowd at its pace (`_escort`); a
#: Dodge comes alone (it outruns everything at 0.5).  No shotgun and no Minigun crate, so nothing wide can
#: find a Berserk by accident.  Groups come within five units about five seconds apart and never more than
#: ten in any eight.
PLISTS['port_heavyweights_1'] = _wave(
    _resting(_Z4, 40, 10.0, 1.0)
    + _pack(_HH, 170, 13.0, 3.0)
    + [('Dodge', 280, 12.0, 13.5)]
    + _escort(_Z3, 'Shield', 100, 10.0, 17.0)
    + _resting(_Z4, 45, 10.0, 23.0)
    + [('Hulk', 330, 13.0, 28.0)], no_blast=True)
PLISTS['port_heavyweights_2'] = _wave(
    _pack(_HH, 0, 13.0, 0.0)
    + _resting(_Z4, 120, 10.0, 10.0)
    + [('Dodge', 240, 12.0, 14.5)]
    + _escort(_Z3, 'Shield', 300, 10.0, 18.5)
    + _pack(_HH, 60, 13.0, 20.5)
    + [('DodgeB', 170, 12.0, 31.0)]
    + _escort(_Z3, 'Shield', 200, 10.0, 34.0), no_blast=True)
PLISTS['port_heavyweights_3'] = _wave(
    _resting(_Z4, 20, 10.0, 1.0)
    + _pack(_HH, 140, 13.0, 2.0)
    + _escort(_Z3, 'Shield', 260, 10.0, 12.0)
    + [('Dodge', 80, 12.0, 17.5)]
    + _pack(_HH, 320, 13.0, 19.5)
    + _resting(_Z4, 190, 10.0, 28.5)
    + [('DodgeB', 40, 12.0, 34.5)]
    + _escort(_Z3, 'Shield', 110, 10.0, 37.0)
    + _pack(_HH, 230, 13.0, 41.0)
    + [('Dodge', 350, 12.0, 51.0)], no_blast=True)
PLISTS['port_heavyweights'] = {
    'challenge_id': 'port_heavyweights',
    'title': 'Heavyweights',
    'objective': 'Everything out here is big, and some of it is touchy.',
    'tip': 'A bullet is taken personally. A blast, it seems, is not. Count your rockets.',
    'icon': 'Challenge_icon_02', 'icon_title': 'HW',
    'weapons': [{'name': 'tactical', 'ammo': '999'}, {'name': 'bazooka', 'ammo': '25'}, {'name': 'wok'}],
    'bricks': ['port_heavyweights_1', 'port_heavyweights_2', 'port_heavyweights_3'],
    'ambient': {'ambientPlaylist': 'ambient_ruins', 'gain': 0.5},
    'time_limit_star': {'reward': 650, 'objective': 200},
    'accuracy_star': {'reward': 650, 'objective': 60},
}

def _tesla(wave, at, cow=None):
    """One Tesla crate, `at` seconds into the wave (a wave can force one), and perhaps a cow: `cow` is the
    bearing it walks in from, eleven units out, timed to be six units away and still coming when the crate
    starts to beep (1.56 s of arrival and 0.5 a second), so that it is the nearest thing for the whole
    fifteen seconds unless it is shot."""
    wave['PowerUp'] = {'force_spawn_time': at, 'type': 'tesla'}
    if cow is not None:
        wave['PasserBy'] = {'Cow': {'spawn_angle': float(cow), 'spawn_distance': 11.0,
                                    'spawn_time': round(max(0.1, at + 6.75 - 1.56 - 10.0), 2)}}
    return wave


_ROD3 = (('Zombie', 'ZombieB', 'ZombieC'), ('ZombieB', 'Zombie', 'WeakZombie'),
         ('ZombieC', 'WeakZombieB', 'Zombie'))
_ROD4 = (('Zombie', 'ZombieB', 'ZombieC', 'Zombie'), ('ZombieC', 'Zombie', 'WeakZombieB', 'ZombieB'))
# ------------------------------------------------------------------------------------------- Lightning Rod
#: The Tesla (`TeslaPowerUp`): 2.86 s after its crate is opened, and every two seconds after that for as many
#: kills as its level (one to four), `BrickManager.closest_enemy` - the nearest shootable thing to the
#: player, whatever it is - has its life set to nought.  That is a Colossus in one stroke, or a Riot Gear
#: Zombie behind its shield, or a cow.  The rifle is the Tactical, which no arena had handed out (held, a
#: round every 0.25 s at twenty degrees; 15 a round at level four, forty to a magazine, four seconds to
#: reload): a Colossus is some forty rounds of it and twelve seconds, and there are one, then two, then two
#: of them, with a group coming within five units every four to five seconds around them.  A crate is one
#: zap at level one (four at level four), so in waves 2 and 3 one Colossus is the rifle's whatever happens,
#: and the second one too if the zap goes astray.
#:
#: One crate a wave (`PowerUp`'s force_spawn_time; a wave forces one), five units out on a random bearing and
#: beeping from 6.75 s after its time for fifteen seconds.  Each starts beeping while something smaller is
#: still nearer than the Colossus, so the zap goes where the player lets it.  In waves 2 and 3 a cow walks in
#: too - a `PasserBy` with no orientation walks straight through the player - timed to be six units out and
#: coming as the crate starts, so that for all fifteen seconds it is the nearest thing there is: one round,
#: or a Colossus left standing.  It can be heard; it moos.
#:
#: Shields walk inside their crowd (`_escort`), Runners come alone.  No Berserk: a zap would take it, but a
#: rifle round that found it would wake it, and it would be one more thing nearer than the Colossus.
PLISTS['port_lightningrod_1'] = _tesla(_wave(
    [('Colossus', 30, 11.0, 4.0)]
    + _slots(((_ROD3[0], 150), (_ROD3[1], 250), (_ROD3[2], 110), (_ROD3[0], 200), (_ROD3[1], 330)),
             12.0, 5.0),
    no_blast=True), 8.0)
PLISTS['port_lightningrod_2'] = _tesla(_wave(
    [('Colossus', 300, 11.0, 0.0), ('Colossus', 120, 11.0, 10.0)]
    + _slots(((_ROD4[0], 150), ('Shield', 200), (_HH, 60), (_ROD4[1], 240), (_HH, 330), None, ('Runner', 20),
              None, (_ROD4[0], 100), (_HH, 220), (_ROD4[1], 340),
              ('Shield', 170)), 12.0, 4.0), no_blast=True),
    6.0, cow=80)
PLISTS['port_lightningrod_3'] = _tesla(_wave(
    [('Colossus', 0, 11.0, 0.0), ('Colossus', 180, 11.0, 12.0)]
    + _slots(((_ROD4[0], 180), ('Shield', 60), (_HH, 300), (_ROD4[1], 40), (_HH, 200), None, ('Runner', 150),
              None, ('Shield', 330), (_HH, 90), (_ROD4[0], 210), (_HH, 270 + 15), (_ROD4[1], 20), None,
              ('RunnerB', 160), None, (_ROD4[0], 250), (_HH, 100)), 12.0, 4.0), no_blast=True),
    10.0, cow=270 + 20)
PLISTS['port_lightningrod'] = {
    'challenge_id': 'port_lightningrod',
    'title': 'Lightning Rod',
    'objective': 'Some of what is coming is too big for this rifle. What is dropped in to help is not '
                 'particular.',
    'tip': 'What is in the crate strikes whatever is closest to you. Be sure that is the one you want gone.',
    'icon': 'Challenge_icon_02', 'icon_title': 'LR',
    'weapons': [{'name': 'tactical', 'ammo': '999'}, {'name': 'wok'}],
    'bricks': ['port_lightningrod_1', 'port_lightningrod_2', 'port_lightningrod_3'],
    'ambient': {'ambientPlaylist': 'ambient_ghosttown', 'gain': 0.5},
    'time_limit_star': {'reward': 650, 'objective': 220},
    'accuracy_star': {'reward': 650, 'objective': 55},
}

#: The Sonic Cannon: one round to a clip, so every shot is followed by the 1.8 second reload, and a shot
#: every 1.83 seconds is all it will ever do (`Weapon.reload` does not wait for the shot's cooldown).  What it
#: buys is that one is enough: 65 at level four with a 75 per cent floor is 49 even at eleven units, which is
#: anything of 35 to 47 life at any range the gun reaches - a Zombie, a Runner, a Reject (at level one, 50
#: falls to 37.5 at eleven units, and a Runner there needs a hit inside the ten degree precise cone).  So the
#: arena keeps time: single arrivals on a beat from bearings all round (`SCATTER`), one shot each, and the
#: turn to the next made during the reload.
#:
#: Two things break the beat.  A Hulk or a Dodge takes two shots, and has to be made room for by getting
#: ahead.  And the bands: four Rejects round a Farty walking a unit ahead of them.  Shot one at a time they
#: are five beats; the Farty's death is 37.5 to everything within three units (`Enemy.die` calls
#: `explode`; `explosion` {3, 50, 75} in enemies.plist), and a Reject has 20 - so they are one beat, if the
#: one shot goes to the Farty.
#: The gun hits whatever is nearest the aim in angle, and the Rejects walk ten degrees either side, so a shot
#: within five degrees of the band's middle is the Farty's.  It is also the one to listen for: its walk is
#: 3.6 dB under a Zombie's and a Reject's 7 to 11, so it is the loudest thing in its band and it is in the
#: middle.  Killed beyond five units, its blast does not ring the ears.
#:
#: The Runners come one at a time, never in packs, each a beat after the last (1.9 to 2.2 seconds, which
#: the 1.83 second shot can keep up with, and each has seven seconds or more inside the gun's reach).  No
#: more than ten come within five units in any eight seconds.
_REJECTS = ('WeakZombie', 'WeakZombieC', 'WeakZombieB', 'WeakZombie')


def _band(bearing: float, distance: float, at: float, kinds=_REJECTS):
    """Four Rejects round a Farty that walks a unit ahead of them: ten degrees either side, two of them a
    unit further back, so every one of them is inside the three units its blast reaches."""
    offsets = ((-10.0, 0.0), (10.0, 0.0), (-10.0, 1.0), (10.0, 1.0))
    return [('Farty', bearing, distance - 1.0, at)] + [
        (k, bearing + a, distance + d, round(at + 0.3 * (i + 1), 2))
        for i, (k, (a, d)) in enumerate(zip(kinds, offsets))]


def _beat(kinds, count: int, every: float, first: float = 0.0, bearings=SCATTER):
    """Single arrivals on a beat, from bearings all round; Runners from eleven units, the rest from ten."""
    out = []
    for i in range(count):
        k = kinds[i % len(kinds)]
        out.append((k, bearings[i % len(bearings)], 11.0 if k.startswith('Runner') else 10.0,
                    round(first + i * every, 2)))
    return out


PLISTS['port_tempo_1'] = _wave(
    _beat(('Zombie', 'ZombieB', 'ZombieC', 'Zombie'), 8, 2.5)
    + _band(300, 10.0, 20.0) + [('Runner', 170, 11.0, 24.0)]
    + _band(60, 10.0, 28.0) + [('RunnerB', 230, 11.0, 32.0)], no_blast=True)
PLISTS['port_tempo_2'] = _wave(
    _beat(('Runner', 'Zombie', 'RunnerB', 'ZombieB'), 12, 2.2, bearings=_turned(4))
    + [('Hulk', 250, 12.0, 6.0)]
    + _band(140, 10.0, 12.0) + _band(20, 10.0, 26.0) + _band(200, 10.0, 34.0), no_blast=True)
PLISTS['port_tempo_3'] = _wave(
    _beat(('Runner', 'RunnerB', 'RunnerC'), 7, 1.9, bearings=_turned(8))
    + _band(100, 10.0, 11.0) + [('Dodge', 250, 12.0, 14.0)] + _band(330, 10.0, 20.0)
    + _beat(('RunnerB', 'Runner', 'RunnerC'), 7, 1.9, first=25.0, bearings=_turned(14))
    + [('Hulk', 180, 12.0, 36.0)] + _band(60, 10.0, 40.0), no_blast=True)
PLISTS['port_tempo'] = {
    'challenge_id': 'port_tempo',
    'title': 'Tempo',
    'objective': 'One shot, then a reload, every time. They keep time too, and some of them come in bands.',
    'tip': 'Stay ahead of the beat and there is room for the ones that take two. A band is only as strong '
           'as the loud one in the middle.',
    'icon': 'Challenge_icon_02', 'icon_title': 'TP',
    'weapons': [{'name': 'sonic', 'ammo': '999'}, {'name': 'wok'}],
    'bricks': ['port_tempo_1', 'port_tempo_2', 'port_tempo_3'],
    'ambient': {'ambientPlaylist': 'ambient_roman', 'gain': 0.5},
    'time_limit_star': {'reward': 650, 'objective': 180},
    'accuracy_star': {'reward': 650, 'objective': 65},
}

_CLOSE3 = ('ZombieB', 'Zombie', 'ZombieC')
_CLOSE_W3 = ('WeakZombie', 'WeakZombieC', 'WeakZombieB')

#: The last arena, for now: one of everything the chapters taught, each with the answer it was taught with,
#: and four weapons from across the shop to give those answers.  The Hunting Rifle, the first gun anyone
#: bought (Big Game), is in hand: 25 a shot at level four, a Hulk in four, the Colossus in twenty.  The
#: Grenade Launcher (chapter 4) is for what only a blast should touch.  The Golf club is for arm's length:
#: 50 a swing and a quarter-second lock at level four, one swing for anything light.  And the Machine Gun is
#: here as **one belt** - a hundred rounds, which at level four is exactly one belt and never needs its six
#: second change (two belts of fifty at level one): the answer to the moment that goes wrong.  The Colossus
#: is a third of it at level four and half of it at level one.
#:
#: What comes, and what it was answered with before:
#:
#: * a band - four Rejects round a Farty a unit ahead of them (Powder Keg): one grenade, or a shot
#:   into the Farty, whose 37.5 within three units is more than a Reject's 20;
#: * a crowd of Rejects walking past a resting Berserk (Do Not Wake It, Collateral): a grenade lands on the
#:   Berserk, the nearest thing in front, does not wake it, and its flat 30 (22.5 at level one) takes every
#:   Reject within five units.  A bullet aimed at the crowd finds the Berserk;
#: * a Riot Gear Zombie inside a crowd of Rejects (Collateral): the grenade goes through the shield;
#: * a Dodge, alone (Sidestep): a grenade does not send it sideways;
#: * Runners, three from one bearing (Stampede): the rifle, or the belt;
#: * Hulks in pairs from twelve units (The Wall), a Chainsaw alone (Carousel), two Whisperers (heard by
#:   their scream at three units, and one swing of the club each);
#: * and in the last wave a Colossus from ten units (The Long Walk), at the player 42 seconds in, with all of
#:   the above arriving from every other side while it comes.  Twenty rifle hits, or a third of the belt: when
#:   is the wave.
#:
#: Built to every rule the chapter 4 test left: groups come within five units about five seconds apart and
#: never more than ten in any eight; Dodges, Chainsaws and Runner packs come on their own, and never two
#: Runner packs together; Berserks rest on a crowd's way in and leave by themselves; nothing wide in the
#: arena - no shotgun, no Minigun crate - can find a Berserk by accident.  Rejects rather than Zombies round
#: the Berserks, so that one grenade is always a whole crowd.

PLISTS['port_closingtime_1'] = _wave(
    _band(30, 10.0, 0.0)
    + _resting(_REJECTS, 150, 10.0, 5.0)
    + [('Runner', 270, 11.0, 16.0), ('RunnerB', 275, 11.3, 16.3), ('RunnerC', 265, 11.0, 16.6)]
    + _pack(_HH, 90, 12.0, 14.0)
    + _escort(_CLOSE_W3, 'Shield', 210, 10.0, 20.5)
    + [('QuietZombie', 330, 10.0, 28.0), ('QuietZombie', 350, 10.0, 29.5)], no_blast=True)
PLISTS['port_closingtime_2'] = _wave(
    _escort(_CLOSE3, 'Shield', 0, 10.0, 0.0)
    + [('Dodge', 120, 12.0, 4.7)]
    + _resting(_REJECTS, 240, 10.0, 7.6)
    + [('Chainsaw', 60, 10.0, 12.4)]
    + _pack(_HH, 300, 12.0, 18.4)
    + _pack(_R3, 180, 11.0, 21.0, spread=5.0)
    + _band(100, 10.0, 25.6)
    + [('DodgeB', 210, 12.0, 33.0)], no_blast=True)
PLISTS['port_closingtime_3'] = _wave(
    [('Colossus', 0, 10.0, 0.0)]
    + _resting(_REJECTS, 150, 10.0, 0.8)
    + _pack(_HH, 100, 12.0, 9.5)
    + _pack(_R3, 250, 11.0, 12.5, spread=5.0)
    + _escort(_CLOSE_W3, 'Shield', 200, 10.0, 15.0)
    + [('Dodge', 300, 12.0, 20.5)]
    + _band(60, 10.0, 23.0)
    + [('Chainsaw', 170, 10.0, 29.0)]
    + _pack(_HH, 230, 12.0, 31.0)
    + _pack(_R3, 120, 11.0, 45.5, spread=5.0), no_blast=True)
PLISTS['port_closingtime'] = {
    'challenge_id': 'port_closingtime',
    'title': 'Closing Time',
    'objective': 'One of everything, and then all of it at once. This is the last of them, for now.',
    'tip': 'You have met every one of these before, and each of them had an answer. Nothing out here '
           'shares one.',
    'icon': 'Challenge_icon_02', 'icon_title': 'CT',
    'weapons': [{'name': 'hunting', 'ammo': '999'}, {'name': 'grenade', 'ammo': '20'},
                {'name': 'machinegun', 'ammo': '100'}, {'name': 'golf'}],
    'bricks': ['port_closingtime_1', 'port_closingtime_2', 'port_closingtime_3'],
    'ambient': {'ambientPlaylist': 'ambient_ghosttown', 'gain': 0.5},
    'time_limit_star': {'reward': 700, 'objective': 190},
    'accuracy_star': {'reward': 700, 'objective': 60},
}

# ---------------------------------------------------------------------------------------------- Reprise
#: The whole of the Extra mode again, in the order it was played, as one challenge of twelve waves: six acts
#: of two, one for each chapter, and each act fought with that chapter's weapons (user request).  A wave may
#: carry `Weapons` of its own - the challenge's form, handed over as the wave loads - so the first wave of
#: every act takes the last act's weapons away and hands over the next set, reads it out ("New weapons:
#: ..."), and draws its first gun.  The challenge's own `weapons` names every one of them, because that is
#: the list the overview checks; the first wave's set replaces it before anything is heard.
#:
#: It is long - ten to twelve minutes - and one enemy reaching the player ends it, so every act is a little
#: gentler than the chapter it remembers, and a death offers the revive, as in every arena of the mode.
#: It is measured as if there were none.  Nothing here can use a modifier or a second ambience (both are the
#: challenge's, not a wave's), and nothing that stays is left behind: cows walk off, so they are used, and
#: no jukebox or machine is, because a passer-by stays for every wave after the one it came in.
#:
#: Each act's first wave starts quietly - nothing inside eight units for the first six seconds or so - so the
#: new weapons can be heard and a player can cycle to the one they want before anything needs it.

#: Arrival lengths and speeds for the kinds `_ARRIVE` and `_slots` do not know, so a group can be placed by
#: the moment it comes within five units rather than by the moment it is heard (the shortest recording of
#: each lottery; handbook 4.1).  A Chainsaw circles in at 0.725 a second, a Farty walks a unit ahead of its
#: band.
_REMIX_ARRIVE = dict(_ARRIVE, Chainsaw=4.60, Dodge=3.34, DodgeB=3.34, Farty=2.14, FartyB=2.14, Colossus=3.41,
                     Shield=4.25, WeakZombieD=1.70)
_REMIX_SPEED = {'Hulk': 0.75, 'HulkB': 0.75, 'Runner': 1.3, 'RunnerB': 1.3, 'RunnerC': 1.3, 'Chainsaw': 0.725,
                'Dodge': 0.9, 'DodgeB': 0.9, 'Colossus': 0.25}


def _remix_lead(kind: str, distance: float) -> float:
    """Seconds from spawning to five units out, for one walking in straight from `distance`."""
    return _REMIX_ARRIVE[kind] + max(0.0, distance - 5.0) / _REMIX_SPEED.get(kind, 0.5)


def _remix_when(reach: float, kinds, distance: float, step: float = 0.3) -> float:
    """When a group - `kinds` spawning `step` seconds apart from `distance` - must start for its first to
    come within five units at `reach`."""
    return round(max(0.0, reach - min(step * i + _remix_lead(k, distance) for i, k in enumerate(kinds))), 2)


def _remix_slots(slots, first: float, every: float) -> list:
    """`_slots` for this arena: groups coming within five units `every` seconds apart from `first`, `None`
    for a quiet slot.  A group is a pack (a tuple of kinds, ten units out), one kind alone (eleven for a
    Runner, ten for the rest), 'Shield' (a Riot Gear Zombie in the middle of three Rejects) or 'band' (four
    Rejects round a Farty, `_band`); a third member of the slot is the distance."""
    out = []
    for i, slot in enumerate(slots):
        if slot is None:
            continue
        group, bearing = slot[:2]
        reach = first + i * every
        if group == 'Shield':
            dist = slot[2] if len(slot) > 2 else 10.0
            at = reach - _remix_lead('WeakZombieC', dist)
            out += _escort(('WeakZombie', 'WeakZombieC', 'WeakZombieB'), 'Shield', bearing, dist,
                           round(max(0.0, at), 2))
        elif group == 'band':
            dist = slot[2] if len(slot) > 2 else 10.0
            at = reach - _remix_lead('Farty', dist - 1.0)
            out += _band(bearing, dist, round(max(0.0, at), 2))
        elif isinstance(group, tuple):
            dist = slot[2] if len(slot) > 2 else 10.0
            at = min(reach - _remix_lead(k, dist) - 0.3 * j for j, k in enumerate(group))
            out += _pack(group, bearing, dist, round(max(0.0, at), 2))
        else:
            dist = slot[2] if len(slot) > 2 else (11.0 if group.startswith('Runner') else 10.0)
            out.append((group, bearing, dist, round(max(0.0, reach - _remix_lead(group, dist)), 2)))
    return out


def _remix_beat(kinds, bearings, every: float, first: float, distance: float = 10.0) -> list:
    """One at a time on a beat, the kinds and the bearings taken in turn; a Runner a unit further out."""
    return [(kinds[i % len(kinds)], b,
             distance + (1.0 if kinds[i % len(kinds)].startswith('Runner') else 0.0),
             round(first + i * every, 2)) for i, b in enumerate(bearings)]


def _remix_singles(entries) -> list:
    """One at a time, each given by `(kind, bearing, the second it comes within five units[, distance])`."""
    out = []
    for one in entries:
        kind, bearing, reach = one[:3]
        dist = one[3] if len(one) > 3 else (11.0 if kind.startswith('Runner') else 10.0)
        out.append((kind, bearing, dist, round(max(0.0, reach - _remix_lead(kind, dist)), 2)))
    return out


def _remix_asleep(bearing: float, at: float, kinds=('Zombie', 'WeakZombie')) -> list:
    """Do Not Wake It's shape, for single-shot guns: a Berserk resting seven units out and two walkers going
    past it twenty-five degrees either side, so a shot at either has something nearer in angle than it."""
    return [('Berserk', bearing, 7.0, at), (kinds[0], bearing - 25.0, 10.0, at + 1.0),
            (kinds[1], bearing + 25.0, 10.0, at + 5.0)]


def _remix_heads(wave: dict, head: str, heads, after: float = 2.0) -> dict:
    """Hydra: `heads` - (kind, bearing, distance) - start `after` seconds after `head` dies
    (`spawn_after`)."""
    for kind, bearing, dist in heads:
        wave['Enemies']['%s %d' % (kind, 90 + len(wave['Enemies']))] = {
            'spawn_angle': float(bearing), 'spawn_distance': float(dist),
            'spawn_after': {'enemy': head, 'time': after}}
    return wave


#: The six sets.  One or two guns and a melee weapon from each chapter, so that across the six every gun of
#: the Extra mode is handed over once and every melee weapon at least once: the revolver, the Micro SMG and
#: the Banjo; the Hunting Rifle, the Micro SMG again and the Golf Club; the Tactical Rifle, the revolver and
#: the Cattle Prod; the Sawn-off, the Grenade Launcher and the Claymore; the Police Shotgun, the Bazooka and
#: the wok; the Machine Gun, the Sonic Cannon and the Golf Club.  Rounds are unlimited except where counting
#: them was the chapter's point (the launchers).
_REMIX_ARMS = (
    [{'name': 'pistol', 'ammo': '999'}, {'name': 'microsmg', 'ammo': '999'}, {'name': 'banjo'}],
    [{'name': 'hunting', 'ammo': '999'}, {'name': 'microsmg', 'ammo': '999'}, {'name': 'golf'}],
    [{'name': 'tactical', 'ammo': '999'}, {'name': 'pistol', 'ammo': '999'}, {'name': 'prod'}],
    [{'name': 'sawnoff', 'ammo': '999'}, {'name': 'grenade', 'ammo': '30'}, {'name': 'claymore'}],
    [{'name': 'policeshotgun', 'ammo': '999'}, {'name': 'bazooka', 'ammo': '40'}, {'name': 'wok'}],
    [{'name': 'machinegun', 'ammo': '999'}, {'name': 'sonic', 'ammo': '999'}, {'name': 'golf'}],
)

# ---- Act one: chapter 1 - Clockwork, Barnyard and Busker; Three Bullets, Do Not Wake It and The Wall
#: Clockwork's metronome, round four bearings three seconds apart, with Barnyard's cows walking through it
#: between the bearings (a round into a cow is one not in a zombie), and Busker's end: two small crowds
#: standing up at seven units, arm's length for the banjo in a few seconds, a Whisperer in each.
PLISTS['port_remix_1'] = _wave(
    _remix_beat(('WeakZombie', 'Zombie', 'ZombieB', 'QuietZombie', 'Zombie', 'WeakZombieB', 'ZombieC',
                 'Zombie',
                 'QuietZombie', 'ZombieB'), (20, 110, 200, 290) * 2 + (20, 110), 3.0, 2.0)
    + _pack(('Zombie', 'QuietZombie', 'WeakZombie'), 65, 7.0, 36.0)
    + _pack(('ZombieB', 'WeakZombieC', 'QuietZombie'), 245, 7.0, 43.0), no_blast=True,
    passers=_cows((65, 11, 3), (155, 11, 11), (335, 11, 19)))
PLISTS['port_remix_1']['Weapons'] = _REMIX_ARMS[0]
#: What will not come to you, what should not be woken and what does not die to a cylinder: two Bobs and
#: the arena's one Diamond standing still, two Berserks resting with walkers passing wide of them, and two
#: Hulks and a Riot Gear Zombie (two Rejects with it) walking in from twelve.
PLISTS['port_remix_2'] = _wave(
    [('Bob', 200, 9.0, 0.0), ('Hulk', 300, 12.0, 4.0)]
    + _remix_asleep(100, 1.0)
    + _escort(('WeakZombie', 'WeakZombieB'), 'Shield', 20, 12.0, 11.0) + [('Bob', 60, 10.0, 14.0)]
    + _remix_asleep(230, 16.0, ('ZombieB', 'Zombie'))
    + [('QuietZombie', 150, 10.0, 25.0), ('HulkB', 110, 12.0, 28.0), ('Zombie', 340, 10.0, 31.0)],
    no_blast=True)
PLISTS['port_remix_2']['Enemies']['Diamond'] = {'spawn_angle': 175.0, 'spawn_distance': 6.0,
                                                 'spawn_time': 22.0}

# ---- Act two: chapter 2 - The Long Walk, Sidestep and Bad Company; Stampede, Hydra, Fore and Big Game
#: The Long Walk: a Colossus from twelve units in front, and a crowd coming one at a time from behind while
#: it walks; then a Dodge alone, and Bad Company's Farty with three Rejects round it, to be shot while they
#: are round it and not after they are close.
PLISTS['port_remix_3'] = _wave(
    [('Colossus', 0, 12.0, 0.0), ('Zombie', 160, 10.0, 3.0), ('WeakZombie', 200, 10.0, 9.0),
     ('ZombieB', 180, 10.0, 15.0), ('QuietZombie', 170, 10.0, 21.0), ('Dodge', 90, 12.0, 24.0),
     ('Zombie', 215, 10.0, 27.0)]
    + _gassy(('WeakZombie', 'WeakZombieB', 'WeakZombieC'), 'Farty', 240, 10.0, 31.0)
    + [('ZombieC', 130, 10.0, 38.0)], no_blast=True)
PLISTS['port_remix_3']['Weapons'] = _REMIX_ARMS[1]
#: Stampede's Runners one at a time, six seconds or more apart, never two at once; Big Game's Hulks for the
#: rifle; Fore's Chainsaw for the club; and two Hydra heads, each growing two more two seconds after it dies.
PLISTS['port_remix_4'] = _remix_heads(_remix_heads(_wave(
    [('Zombie', 150, 9.0, 2.0), ('Hulk', 60, 12.0, 0.0)]
    + _remix_singles((('Runner', 250, 19.0), ('HulkB', 300, 25.0, 12.0), ('Chainsaw', 200, 30.0),
                      ('RunnerB', 30, 35.0), ('Zombie', 330, 39.0, 9.0), ('Runner', 110, 45.0),
                      ('Hulk', 240, 48.0, 12.0), ('RunnerC', 180, 53.0))), no_blast=True),
    'Zombie 1', (('WeakZombie', 130, 8.0), ('WeakZombieB', 170, 8.0))),
    'Zombie 7', (('ZombieB', 310, 7.5), ('WeakZombieC', 350, 7.5)))

# ---- Act three: chapter 3 - Front Line and Cattle Call; The Drop and Carousel
#: Front Line: one broad side (fifteen to ninety-five degrees, clear of the seam at 270) walking in one at a
#: time, two seconds apart, with two Riot Gear Zombies and two Hulks inside the line.  Then Cattle Call from
#: the other side: Whisperers that nobody hears until they scream at three units, each alone, and a cow
#: walking in among them for the prod to find if it is nearer.
PLISTS['port_remix_5'] = _wave(
    _line(('Zombie', 'WeakZombie', 'ZombieB', 'Zombie', 'WeakZombieB', 'ZombieC', 'Zombie', 'ZombieB',
           'QuietZombie', 'Zombie', 'ZombieC', 'WeakZombie', 'Zombie', 'ZombieB'),
          (40, 70, 25, 55, 85, 35, 65, 20, 50, 90, 30, 75, 45, 60), 10.0, 2.0, first=2.0)
    + [('Shield', 45, 11.0, 4.0), ('Hulk', 60, 11.0, 10.0), ('Shield', 80, 11.0, 16.0),
       ('HulkB', 30, 11.0, 22.0)]
    + _reaching([('QuietZombie', 220, 44.0), ('QuietZombie', 250, 48.0), ('Zombie', 195, 51.0),
                 ('QuietZombie', 235, 54.5), ('QuietZombie', 205, 58.0)]), no_blast=True,
    passers=_cows_in((210, 50.0)))
PLISTS['port_remix_5']['Weapons'] = _REMIX_ARMS[2]
#: Carousel without its speed cards: Chainsaws and Clowns circling in a little over two seconds apart,
#: walkers between them; and The Drop's crate, a Minigun, dropped in while four of them are going round.
PLISTS['port_remix_6'] = _wave(_remix_beat(
    ('Chainsaw', 'Clown', 'Zombie', 'Chainsaw', 'Clown', 'ZombieB', 'Clown', 'Chainsaw', 'Zombie', 'Clown',
     'Hulk', 'Chainsaw', 'Clown', 'ZombieC', 'Chainsaw', 'Clown'),
    (30, 150, 260, 300, 90, 210, 340, 120, 45, 180, 280, 60, 240, 0, 200, 100), 2.2, 0.0), no_blast=True)
PLISTS['port_remix_6']['PowerUp'] = {'force_spawn_time': 14.0, 'type': 'minigun'}

# ---- Act four: chapter 4 - Point Blank, Fuse and Bonfire Night; One Swing, Crossfire and Short Game
#: Packs of four, four and a half seconds apart, from eleven units: grenades for them far out, shells for
#: them close (Point Blank's 46 at three units against 30 at seven), and Runners in packs of their own;
#: Bonfire Night's Fireworks while packs are inside ten units; and Crossfire's two packs from opposite sides
#: half a second apart - Zombies, not Runners, so a shell, a half turn and a shell still leave room.
PLISTS['port_remix_7'] = _wave(
    _remix_slots(((_Z4, 30, 11.0), (('WeakZombie', 'Zombie', 'WeakZombieC', 'ZombieB'), 150, 11.0),
                  (('ZombieC', 'Zombie', 'ZombieB', 'WeakZombie'), 250, 11.0), (_R3, 100, 11.0), None,
                  None, (_Z4, 210, 11.0), (_R2, 300),
                  (('ZombieB', 'WeakZombieB', 'Zombie', 'ZombieC'), 60, 11.0)),
                 15.5, 4.5)
    + _remix_slots(((('Zombie', 'ZombieC', 'ZombieB'), 330), (('ZombieB', 'Zombie', 'QuietZombie'), 150)),
                   36.0, 0.5),
    no_blast=True)
PLISTS['port_remix_7']['PowerUp'] = {'force_spawn_time': 20.0, 'type': 'fireworks'}
PLISTS['port_remix_7']['Weapons'] = _REMIX_ARMS[3]
#: One Swing's singles - a Runner, a Chainsaw - each alone, for the claymore or a shell; Short Game's crowds
#: of Rejects for the launcher; a Crossfire pair; two Hulks, three shells between them if they are let in
#: together; and Crossfire's Runners from both sides, the second pair two and a half seconds behind the first
#: (a shell, a half turn and a shell).
PLISTS['port_remix_8'] = _wave(_remix_slots((
    (_W4, 40, 11.0), ('Runner', 220), (_Z4, 130), ('Chainsaw', 300), (_Z4, 0), None, (_HH, 70, 11.0), None,
    (_R2, 250), None, (('WeakZombieB', 'WeakZombie', 'WeakZombieC', 'WeakZombieB'), 160, 11.0)), 13.0, 4.5)
    + _remix_slots(((('ZombieB', 'Zombie', 'ZombieC'), 180),), 31.5, 1.0)
    + _remix_slots(((_R2, 70),), 51.5, 1.0), no_blast=True)

# ---- Act five: chapter 5 - Crowd Control, Artillery and Riot Act; Titans and Scarecrows
#: Artillery's packs standing up thirteen units out, where only the rocket reaches, and Crowd Control's lines
#: at nine, shoulder to shoulder, one shell's cone wide, about five seconds apart at five units; a pack of
#: Runners on its own, a Riot Gear Zombie in its crowd far out, two Hulks and a Dodge alone.
_REMIX_L5 = (('WeakZombie', 'Zombie', 'WeakZombieC', 'ZombieB', 'WeakZombie'),
             ('ZombieB', 'WeakZombie', 'Zombie', 'WeakZombieC', 'ZombieC'))
_REMIX_L6 = ('Zombie', 'WeakZombieC', 'ZombieC', 'WeakZombie', 'ZombieB')
PLISTS['port_remix_9'] = _wave(
    _pack(_P4[0], 30, 13.0, _remix_when(16.0, _P4[0], 13.0), spread=5.0)
    + _shoulder(_REMIX_L5[0], 150, 70, 9.0, _remix_when(21.0, _REMIX_L5[0], 9.0, 0.25))
    + _pack(_P4[1], 250, 13.0, _remix_when(26.5, _P4[1], 13.0), spread=5.0)
    + _pack(_R3, 90, 11.0, _remix_when(33.0, _R3, 11.0), spread=5.0)
    + _shoulder(_REMIX_L6, 330, 100, 9.0, _remix_when(37.5, _REMIX_L6, 9.0, 0.25))
    + _escort(('WeakZombie', 'WeakZombieB', 'WeakZombieC'), 'Shield', 200, 13.0,
              _remix_when(42.5, ('WeakZombie', 'WeakZombieB', 'WeakZombieC'), 13.0))
    + _pack(_HH, 110, 13.0, _remix_when(47.0, _HH, 13.0))
    + [('Dodge', 20, 14.0, _remix_when(51.5, ('Dodge',), 14.0))]
    + _shoulder(_REMIX_L5[1], 240, 80, 9.0, _remix_when(56.0, _REMIX_L5[1], 9.0, 0.25))
    + _pack(_P4[2], 150, 13.0, _remix_when(61.0, _P4[2], 13.0), spread=5.0), no_blast=True)
PLISTS['port_remix_9']['Weapons'] = _REMIX_ARMS[4]
#: Titans: two Colossi with crowds walking in on their bearings and past them, where a rocket at one lands
#: among them.  Scarecrows: a Bob, a Jim and a Ted standing close in front of the crowds behind them, in the
#: way of a rocket and not of a shell.  Five seconds between groups at five units.
PLISTS['port_remix_10'] = _wave(
    [('Colossus', 330, 12.0, 0.0), ('Colossus', 150, 11.5, 8.0)]
    + _beside(_TRIOS[0], 330, _remix_when(22.5, _TRIOS[0], 13.5))
    + _field('Bob', 60, 4.5, 6.0) + _parted(_P4[1], 60, 13.0, _remix_when(27.5, _P4[1], 13.0))
    + _beside(_TRIOS[1], 150, _remix_when(32.5, _TRIOS[1], 13.5))
    + _pack(_R3, 240, 11.0, _remix_when(37.5, _R3, 11.0), spread=5.0)
    + _field('Jim', 20, 4.5, 24.0) + _parted(_P4[3], 20, 13.0, _remix_when(42.5, _P4[3], 13.0))
    + [('Chainsaw', 110, 10.0, _remix_when(47.5, ('Chainsaw',), 10.0))]
    + _beside(_TRIOS[2], 330, _remix_when(52.5, _TRIOS[2], 13.5))
    + _field('Ted', 200, 4.5, 41.0) + _parted(_HH, 200, 13.0, _remix_when(57.5, _HH, 13.0))
    + _pack(_R2, 90, 11.0, _remix_when(62.5, _R2, 11.0), spread=5.0), no_blast=True)

# ---- Act six: chapter 6 - Juggernaut, Belt Fed and Lightning Rod; Tempo and Closing Time
#: Juggernaut: two Colossi in front, slow enough to wait for a full belt, and crowds and Hulks from behind
#: four seconds apart with two quiet slots for the belt change (Belt Fed).  Lightning Rod's crate comes down
#: while the Colossi are still coming: its lightning takes whatever is nearest.
_REMIX_P5 = (('Zombie', 'ZombieB', 'WeakZombie', 'ZombieC', 'Zombie'),
             ('ZombieC', 'Zombie', 'QuietZombie', 'ZombieB', 'Zombie'))
_REMIX_H3 = ('Hulk', 'HulkB', 'Hulk')
PLISTS['port_remix_11'] = _wave(
    [('Colossus', 0, 11.0, 0.0), ('Colossus', 60, 11.0, 10.0)]
    + _remix_slots(((_REMIX_P5[0], 180), (_REMIX_H3, 140, 12.0), (_Z4B, 215), (_REMIX_H3, 200, 12.0),
                    None, ('Runner', 160), None, (_REMIX_P5[1], 230), (_REMIX_H3, 120, 12.0), (_Z4, 190),
                    (_HH, 250, 12.0), (_Z4, 150), (_REMIX_H3, 205, 12.0)), 14.0, 4.0), no_blast=True)
PLISTS['port_remix_11']['PowerUp'] = {'force_spawn_time': 12.0, 'type': 'tesla'}
PLISTS['port_remix_11']['Weapons'] = _REMIX_ARMS[5]
#: Tempo: one at a time on a beat of two seconds, Runners and Zombies in turn, for a gun that fires once a
#: reload, and bands of Rejects round a Farty.  Closing Time: one of everything after it - a Riot Gear
#: Zombie in its crowd, a Dodge alone, two Hulks, a Berserk resting with walkers going wide of it, a
#: Chainsaw and a last pack of Runners.
PLISTS['port_remix_12'] = _wave(
    _remix_beat(('Runner', 'Zombie', 'RunnerB', 'ZombieB', 'Runner', 'ZombieC', 'RunnerC', 'Zombie',
                 'RunnerB',
                 'ZombieB'), (20, 200, 110, 290, 60, 240, 160, 330, 90, 180), 2.0, 1.0)
    + _remix_slots((('band', 300), ('Shield', 60), ('Dodge', 200, 12.0), (_HH, 250, 12.0), None, None,
                    ('Chainsaw', 300), ('band', 20), None, (_R3, 90, 11.0)), 34.0, 4.5)
    + _remix_asleep(130, 39.5), no_blast=True)

PLISTS['port_remix'] = {
    'challenge_id': 'port_remix',
    'title': 'Reprise',
    'objective': 'Every chapter again, one after another, and a different set of weapons for each of them.',
    'tip': 'Nothing you are handed stays with you for long, so there is nothing to save it for. Every part '
           'of this has been played to you before.',
    'icon': 'Challenge_icon_02', 'icon_title': 'RP',
    'weapons': [{'name': 'pistol', 'ammo': '999'}, {'name': 'microsmg', 'ammo': '999'},
                {'name': 'hunting', 'ammo': '999'}, {'name': 'tactical', 'ammo': '999'},
                {'name': 'sawnoff', 'ammo': '999'}, {'name': 'grenade', 'ammo': '30'},
                {'name': 'policeshotgun', 'ammo': '999'}, {'name': 'bazooka', 'ammo': '40'},
                {'name': 'machinegun', 'ammo': '999'}, {'name': 'sonic', 'ammo': '999'},
                {'name': 'banjo'}, {'name': 'prod'}, {'name': 'claymore'}, {'name': 'wok'}, {'name': 'golf'}],
    'bricks': ['port_remix_%d' % i for i in range(1, 13)],
    'ambient': {'ambientPlaylist': 'ambient_roman', 'gain': 0.5},
    'time_limit_star': {'reward': 800, 'objective': 840},
    'accuracy_star': {'reward': 800, 'objective': 55},
}

# ========================================================================================== the story
#: The Long Way Home, the Extra mode's story (user request, 2026-10-01): one survivor's road from a barn to
#: the coast, where a boat is said to leave at dawn.  It is told in text, between waves - a wave's `Story`
#: is read as the wave begins (`ChallengeGameplayController.tell_story_if_due`), and an arena's `Epilogue`
#: once its last wave is won - so it needs no recordings and can be translated.  Every arena opens with a
#: part of it, each chapter's last arena has a word in its last wave and an end of its own, and Reprise one
#: for each of its acts.
#:
#: The voice on the radio is Dr. Bastard's, as the arenas' own objectives already have it (Big Game, Rust):
#: it is only the voice until the end of chapter 5, and the doctor after.  Nothing here says how an arena
#: is won; that is the tips' business, and they only hint.
STORY = {
    # Chapter 1: the farm
    'port_barnyard_1': "You wake in a barn with a revolver, a wok and a hand radio, and no memory of "
                       "choosing any of them. The radio is talking. A boat leaves the coast at dawn, it "
                       "says, for anyone who can reach it. Outside, the cows are restless, and not "
                       "everything in the yard is a cow.",
    'port_wall_1': "The farmhouse has a wall round its yard and a gate that no longer shuts. The voice on "
                   "the radio suggests you hold the gate. It does not say with what.",
    'port_clockwork_1': "In the farmhouse kitchen a clock is still ticking, and the things outside have "
                        "begun to come in time with it. The voice on the radio finds this very funny.",
    'port_three_bullets_1': "Three rounds in a kitchen drawer, and three figures standing out in the field, "
                            "perfectly still. Scarecrows, you think, until one of them turns its head.",
    'port_scrap_1': "Beyond the farm is a scrapyard, cars stacked three high, some with their alarms still "
                    "wired to dying batteries. The voice says the road to the coast runs straight through "
                    "it. It says it like a dare.",
    'port_nowake_1': "Something enormous is asleep in the yard behind the scrapyard. The voice on the radio "
                     "drops to a whisper, which is somehow worse.",
    'port_busker_1': "At the crossroads a man sits on an upturned bucket, playing a banjo to nobody. He "
                     "sells it to you for everything in your pockets and walks away humming. The crowd he "
                     "was playing for has not left.",
    'port_survivor_1': "A woman calls to you from the roof of the last farm before the road. She has been "
                       "up there since it started, she says, and she has heard the radio too. She does not "
                       "believe in the boat. She asks you to stay until morning anyway.",
    'port_survivor_3': "From the roof, the woman says she can see the road. Then she says she can see what "
                       "is on it.",
    # Chapter 2: the road
    'port_longwalk_1': "The road out of the valley is long and straight, and you are not alone on it. "
                       "Something very large is walking the same way, a little way behind, and it is in no "
                       "hurry at all.",
    'port_stampede_1': "A town, or what is left of one. The voice on the radio says the town is empty. It "
                       "says it twice, which is once too often.",
    'port_sidestep_1': "The high street is narrow, and some of what lives in it has learned to step aside. "
                       "The voice calls them the dancers.",
    'port_fore_1': "The road crosses a golf course. In the clubhouse you find one good club, and a "
                   "scorecard with a single line written across it in red: play it as it lies.",
    'port_company_1': "Past the course the road fills with walkers again, and some of them smell very wrong "
                      "indeed. The voice on the radio has an opinion about the bloated ones, and for once "
                      "it keeps it to itself.",
    'port_keg_ring_1': "A quarry, still stacked with blasting powder. The voice says the quarrymen left in "
                       "a hurry. From the look of it, so did everything they were blasting.",
    'port_hydra_1': "In the ravine below the quarry, everything you put down seems to bring more up behind "
                    "it. The voice calls it a garden.",
    'port_biggame_1': "A hunting lodge at the edge of the forest, a rifle over the fireplace and a note "
                      "pinned under it: you will need this. The handwriting matches the scorecard from the "
                      "golf course.",
    'port_biggame_3': "Something is coming out of the forest, and it is what the rifle was left here for.",
    # Chapter 3: the storm
    'port_ironsights_1': "The forest road climbs into rain. Someone has been at the sights of your revolver "
                         "while you slept. The voice on the radio insists, at some length, that it was not "
                         "responsible.",
    'port_cattlecall_1': "Cattle have broken out of a farm and wandered into the woods, and something "
                         "quieter has wandered in with them. A cattle prod hangs on the fence post, still "
                         "charged.",
    'port_thunder_1': "The storm arrives properly. The voice on the radio is all crackle now, and so is "
                      "everything else.",
    'port_rust_1': "You shelter in a gun shop with its shutters down. The revolver is worse than ever. "
                   "Someone has been at it again, and you are nearly certain it was not the rain.",
    'port_frontline_1': "Beyond the woods is the old front line, where the army held out for a week. Their "
                        "rifles are still in the trenches. So are the soldiers, more or less, shields and "
                        "all.",
    'port_drop_1': "A plane passes over in the dark, low and slow, and something falls from it on a "
                   "parachute. The voice on the radio says nothing at all. It is the first time it has had "
                   "nothing to say.",
    'port_carousel_1': "A fairground on the hill, the carousel still turning with nobody to run it. The "
                       "music is cheerful. Nothing else is.",
    'port_last_1': "The storm breaks over a ruined chapel. The voice on the radio says it has something "
                   "important to tell you about the boat, and that it will tell you after this.",
    'port_last_3': "The radio clears its throat. About the boat, it begins, and the chapel roof comes down "
                   "on the rest of the sentence.",
    # Chapter 4: the depot
    'port_pointblank_1': "An army supply depot, fenced and floodlit, its gates wide open. The radio is "
                         "still silent. The first thing you find is a sawn-off shotgun in the guard hut. "
                         "The second thing is everyone else.",
    'port_bonfire_1': "Somebody has lit a bonfire in the vehicle yard and stacked crates beside it. "
                      "Fireworks, by the labels. You have never been less in the mood for a party.",
    'port_oneswing_1': "In the officers' mess a great sword hangs over the fireplace, polished and sharp. "
                       "Somebody has cleared the room around it, as though for a performance.",
    'port_fuse_1': "The armoury is open: a grenade launcher, crates of grenades, and a sign on the wall "
                   "that says mind the fuse. The radio comes back on, just for a moment, to laugh.",
    'port_shortgame_1': "Behind the depot, of all things, a driving range. You still have the golf club. "
                        "The voice is back for good, and it would like to see your swing.",
    'port_collateral_1': "A parade ground, and in the middle of every crowd on it something you would "
                         "rather not disturb. The voice says the show must go on. It is the first time it "
                         "has called it a show.",
    'port_crossfire_1': "Two gates, either side of the depot, both open, both busy. The voice offers no "
                        "advice. It has started taking bets.",
    'port_armory_1': "The depot's last store holds everything you have carried this far. The voice says it "
                     "is proud of you. It sounds as though it means it, which is the worst thing about it.",
    'port_armory_3': "The voice on the radio begins to count down. It does not say to what.",
    # Chapter 5: the city's edge
    'port_riot_1': "The outskirts of the city, where the riot police made their stand. Their shotguns are "
                   "still in the vans. Their lines are still standing, too.",
    'port_chain_1': "A street of burnt-out shops, where everything that walks is carrying something that "
                    "goes off. The voice hopes you enjoy the fireworks. It has said that before.",
    'port_encore_1': "A bandstand in the park, and on it a banjo, left as though someone expected you. The "
                     "voice asks for an encore. You did not know you had played.",
    'port_artillery_1': "Up on the ridge above the city, an abandoned battery and a single launcher. From "
                        "up here you can see the coast, and on it, the lights of a boat.",
    'port_blowback_1': "The wind comes off the sea in gusts, and the streets below the ridge funnel it. The "
                       "voice says it ordered the wind specially. You are no longer sure it is joking.",
    'port_titans_1': "In the stadium, two of the biggest things you have ever seen are waiting, and they "
                     "are not waiting alone. There is a sound like applause on the radio, and then the "
                     "voice, apologising for it.",
    'port_scarecrows_1': "The fields beyond the stadium are full of figures standing in rows, propped up on "
                         "poles. Somebody put every one of them there, carefully, by hand, and you are "
                         "beginning to suspect who.",
    'port_riotact_1': "The bridge into the harbour district, and everything the city has left between you "
                      "and it. The voice reads you the riot act, word for word. It has clearly been looking "
                      "forward to this.",
    'port_riotact_3': "Halfway across the bridge, the lamps along it come on one by one, as though someone "
                      "had been waiting for the moment.",
    # Chapter 6: the docks
    'port_beltfed_1': "The docks are one long factory, and the factory is still running. On a workbench by "
                      "the gate there is a machine gun, a belt of ammunition, and a label with your name on "
                      "it, spelt correctly.",
    'port_coldsteel_1': "The machine gun is loud and the night is long. On the next bench someone has left "
                        "a blade, in case the gun needs a rest. Dr. Bastard thinks of everything.",
    'port_juggernaut_1': "The loading bay doors open by themselves. What comes through them was built, not "
                         "born, and Dr. Bastard is very proud of it.",
    'port_racket_1': "The foundry floor: a jukebox on every landing and the furnaces roaring. The doctor "
                     "says he likes a bit of atmosphere. Somewhere underneath it all, things are walking.",
    'port_heavyweights_1': "The heavy plant shed, where nothing is small and everything is easily upset. "
                           "The doctor asks you to mind the merchandise.",
    'port_lightningrod_1': "A laboratory at the top of the foundry, a coil humming in the corner and crates "
                           "stacked ready. The doctor says he has always wanted to see what it does to "
                           "something really big.",
    'port_tempo_1': "In the doctor's own workshop, on a stand of its own, is a gun that fires sound. He "
                    "says it is his finest work, and that it only ever needs one of anything, on the beat.",
    'port_closingtime_1': "The last hour before dawn. Everything the doctor has left, he sends at once. "
                          "Through the windows you can see the harbour, and the boat, and its lights coming "
                          "on.",
    'port_closingtime_3': "The first grey light is in the sky. The doctor says this is his favourite part.",
    # The Finale: Reprise
    'port_remix_1': "By popular demand, says the doctor. The harbour lights go out and the night begins "
                    "again from the start: the barn, the farmhouse, the figures standing in the field. "
                    "Everything is exactly where you left it.",
    'port_remix_3': "The long road again, the golf course and the lodge. The doctor is reading out the "
                    "scores now.",
    'port_remix_5': "The front line, the cattle in the woods, a crate falling out of the dark. You know "
                    "this part. So does everything else.",
    'port_remix_7': "The depot, the shotgun, the launcher and the sword. The doctor calls it the interval, "
                    "and does not stop.",
    'port_remix_9': "The city's edge: the launcher on the ridge, the titans in the stadium, the scarecrows "
                    "in their rows.",
    'port_remix_11': "The foundry, the coil, the machine gun and the doctor's finest work. Over the "
                     "harbour, the sky is going grey.",
}

#: The end of each chapter, and of the story, read once the last wave of the arena that ends it is won,
#: before the completed screen - where the original's challenges play their closing lines.
EPILOGUES = {
    'port_survivor': "Morning comes. The woman does not come down from the roof, and you do not climb up to "
                     "see why. The radio says the road is clear, for now, and wishes you luck in a voice "
                     "that has never needed any.",
    'port_biggame': "The lodge burns behind you. On the radio the voice is pleased: the coast is closer "
                    "than it was, it says, and the weather is turning. It says the weather is turning as "
                    "though it had arranged it.",
    'port_last': "The rain stops. The radio does not start again. Whatever the last word was going to be, "
                 "you did not hear it, and the road to the coast goes on without it.",
    'port_armory': "You leave the depot by the back gate. There is music on the radio now, and between the "
                   "songs the voice reads out your name as though it were a score. The city is on the "
                   "horizon. The coast is beyond it.",
    'port_riotact': "You cross the bridge. Behind you the city falls quiet, and ahead the docks are dark. "
                    "The voice says there is one more night to go, and that it has saved the best for last. "
                    "For the first time, it signs off with a name: Dr. Bastard.",
    'port_closingtime': "The doors open onto the harbour. The boat is there, engines running, with nobody "
                        "aboard. On the radio, Dr. Bastard thanks you for a wonderful season and promises a "
                        "repeat performance. The boat does not leave. It is waiting, he says, for the "
                        "encore.",
    'port_remix': "Dawn. The radio stops in the middle of a sentence, and this time it stays stopped. The "
                  "boat's engines are running and the gangway is down. You walk aboard with whatever you "
                  "are still carrying, and the boat leaves the coast behind, exactly as promised.",
}

for _name, _text in STORY.items():
    PLISTS[_name]['Story'] = _text
for _name, _text in EPILOGUES.items():
    PLISTS[_name]['Epilogue'] = _text


#: The port's own arenas, gathered into chapters (user request).
#:
#: A chapter is `(name, the arenas in it)`.  Inside a chapter each arena names the one before it in
#: `challenges_requirement` - the original's own key, read by `hasChallengeRequirementsForChallengeWithName:`
#: 0x10001ffbc - so an arena opens when the one before it is beaten, and a chapter opens on **stars**, which
#: is how the original gates a world; how many is `chapter_stars_required`, worked out from the chapters
#: before it rather than written down.
#:
#: The order is the one `tools/arena_pressure.py` measures, easiest first and across every chapter
#: rather than within each (user request), so the first arena of a chapter carries on from the last of the
#: one before.  Three Bullets is the one exception, a second easier by the tool than Scrapyard, which comes
#: after it: it is fought with the wok, and a melee duel with no health is the frightening thing in this
#: game, while Scrapyard's sixty rounds are two hundred damage short of its zombies and the tool does not
#: count that shortfall in its margin at all.
#:
#: The second round's arenas (2026-09-30) are placed by a scripted player instead, which plays an arena with
#: the game's own code at virtual time with a human's reaction time, and finds the slowest reaction that
#: still wins: the tool cannot price a Farty's blast.  Busker, the Banjo's, comes before The Survivor; Fore
#: after Sidestep; Bad Company before Powder Keg, so the Farty is met where it is the whole idea before it
#: is one of several; Cattle Call, the prod's, second in chapter 3 and Front Line, the Tactical's, after
#: Rust; Bonfire Night, gentler than anything else in chapter 4, straight after the Sawn-off is bought for
#: Point Blank, and Short Game after Fuse, which is where the launcher is bought.  Chapter 5 is in the order
#: its guns are bought, each introduced on its own first (Crowd Control, Artillery), and within that by the
#: scripted player at level 4; Riot Act, which asks for everything the chapter taught, is the last.
#: Chapter 6 opens on Belt Fed, the Machine Gun's own, and goes by the same measure to Tempo, the Sonic
#: Cannon's, the hardest; Closing Time, the finale, is last.  Reprise is measured act by act, each a little
#: easier than its chapter, since it is long and one death ends it.
#:
#: The chapters are the port's own structure and not worlds in `challenges_index`, which they could have
#: been: `apply_to` reaches that file and the world list would have given locks, star counts and a
#: "you need N stars" row for nothing.  It would also have changed Somethin' Else's game.
#: `totalStarsUnlocked` 0x10001ecd4 sums every world in that file, and their City Crossroad opens at 25
#: stars and Maya Ruin at 40 - so twenty-one stars' worth of arenas of ours would have opened their worlds
#: early, for a player who had not touched them.  Counting on this side costs a screen and a few lines and
#: leaves their progression exactly as they shipped it.
#:
#: These are the chapters of one campaign, The Long Way Home (`CAMPAIGNS`), and the stars that open them are
#: counted inside it.
LONG_WAY_HOME = (
    #: The guns a player already owns, and the Banjo, which at 1500 coins is the first most will buy: in the
    #: order the tool measures, 15.7 seconds of slack down to 2.2, with the second round's placed round it.
    ('Chapter 1', ('port_barnyard', 'port_wall', 'port_clockwork', 'port_three_bullets', 'port_scrap',
                   'port_nowake', 'port_busker', 'port_survivor')),
    #: Where the slack runs out: 1.4 seconds short down to 12.3.
    ('Chapter 2', ('port_longwalk', 'port_stampede', 'port_sidestep', 'port_fore', 'port_company',
                   'port_keg', 'port_hydra', 'port_biggame')),
    #: Harder again (user request): 13.6 seconds short down to 25.6.
    ('Chapter 3', ('port_ironsights', 'port_cattlecall', 'port_thunder', 'port_rust', 'port_frontline',
                   'port_drop', 'port_carousel', 'port_last')),
    #: The armory (user request): 27.7 seconds short down to 39.8, by the tool's crowd-weapon reckoning
    #: (`area_pressure`).
    ('Chapter 4', ('port_pointblank', 'port_bonfire', 'port_oneswing', 'port_fuse', 'port_shortgame',
                   'port_collateral', 'port_crossfire', 'port_armory')),
    #: The Police Shotgun and the Bazooka, each bought for an arena of its own before they are mixed, and
    #: measured at level 4: the chapters from here on may ask for guns upgraded with diamonds (user
    #: decision, 2026-09-30), so a player may have to play Endless before going on.
    ('Chapter 5', ('port_riot', 'port_chain', 'port_encore', 'port_artillery', 'port_blowback',
                   'port_titans', 'port_scarecrows', 'port_riotact')),
    #: The Machine Gun, the Tesla and the Sonic Cannon, and a finale asking for what every chapter taught.
    ('Chapter 6', ('port_beltfed', 'port_coldsteel', 'port_juggernaut', 'port_racket', 'port_heavyweights',
                   'port_lightningrod', 'port_tempo', 'port_closingtime')),
    #: Reprise, every chapter again in one long arena with the weapons changing hands between acts (user
    #: request), on its own after the last chapter rather than a ninth in it, so the chapters stay at eight.
    ('Finale', ('port_remix',)),
)

#: The collections of arenas Extra holds, each `(name, its chapters)` and each a list on the Extra screen
#: of its own (user request, 2026-10-01): Extra is to hold more than one in time, so a campaign is the level
#: above a chapter, and the first is named after the story its arenas tell.  A campaign counts its own
#: stars - a chapter's gate is the chapters before it in the same campaign, so a campaign added later
#: starts at nought - and the save is untouched, since stars are kept by arena (`ChallengeData`).
CAMPAIGNS = (
    ('The Long Way Home', LONG_WAY_HOME),
)

#: Every chapter of every campaign, in order.  A chapter is found by its name everywhere - the arena list,
#: Back, Next challenge - so no two campaigns may give one the same name.
CHAPTERS = tuple(chapter for _name, chapters in CAMPAIGNS for chapter in chapters)
assert len({name for name, _a in CHAPTERS}) == len(CHAPTERS), 'two chapters share a name'

#: How many of the stars in the chapters before it a chapter may be opened without (user request): two.
#: Every chapter asks for all the stars the chapters before it hold but these - 22 of chapter 1's 24 for
#: chapter 2, 46 of 48 for chapter 3, 70 of 72 for chapter 4, 94 of 96 for chapter 5, 118 of 120 for
#: chapter 6, 142 of 144 for the Finale - and two is less than the three an arena is worth, so no arena can
#: be left unbeaten on the way: what may be missed is two accuracy or time stars, across everything behind
#: you.  It does not shrink as the chapters go on, because at nought a single star a player cannot win - The
#: Last Word's time star, say - would shut every chapter after it for good.  It was 12, 26 and 40 at first,
#: which let a player into a chapter with a third of the one before unplayed.
SPARE_STARS = 2

#: Every arena of the port's, in the order they are played.  What `go_to_challenge_list_for` and the
#: overview's Back ask, to know an arena of ours from one of theirs.
EXTRA_CHALLENGES = tuple(name for _c, arenas in CHAPTERS for name in arenas)


#: What an arena needs before it can be played, and what finishing it pays, worked out from the order above
#: rather than written into each arena by hand.  They are facts about the order and nothing else, and while
#: they were written by hand they were wrong twice - once pointing an arena at itself two places back, once
#: leaving the rewards climbing inside each chapter but not across the pair.  `challenges_requirement` is the
#: original's own key (`hasChallengeRequirementsForChallengeWithName:` 0x10001ffbc) and this fills it in the
#: same shape their own challenges use.
def _derive_order() -> None:
    reward = 200
    for _chapter, arenas in CHAPTERS:
        for i, name in enumerate(arenas):
            arena = PLISTS[name]
            if i:
                arena['challenges_requirement'] = [arenas[i - 1]]
            else:
                arena.pop('challenges_requirement', None)   # the first of a chapter waits on the stars
            arena['mission_star'] = dict(arena.get('mission_star') or {}, reward=reward)
            reward += 50


_derive_order()


def chapter_of(challenge_id: str):
    """The chapter an arena belongs to, or None for a challenge that is not one of ours."""
    for name, arenas in CHAPTERS:
        if challenge_id in arenas:
            return name
    return None


def chapter_arenas(chapter: str) -> tuple:
    for name, arenas in CHAPTERS:
        if name == chapter:
            return arenas
    return ()


def arena_after(challenge_id: str):
    """The arena after this one in its chapter - what Next challenge opens - or None for the last of a
    chapter, and for a challenge that is not one of ours."""
    arenas = chapter_arenas(chapter_of(challenge_id))
    if challenge_id in arenas and arenas.index(challenge_id) + 1 < len(arenas):
        return arenas[arenas.index(challenge_id) + 1]
    return None


def campaign_of(chapter: str):
    """The campaign a chapter belongs to, or None for a name that is not one of ours."""
    for name, chapters in CAMPAIGNS:
        if any(c == chapter for c, _a in chapters):
            return name
    return None


def campaign_chapters(campaign: str) -> tuple:
    for name, chapters in CAMPAIGNS:
        if name == campaign:
            return chapters
    return ()


def chapter_stars_required(chapter: str) -> int:
    """Every star the chapters before this one in its campaign hold, less `SPARE_STARS`; the first chapter
    of a campaign is open."""
    before = 0
    for name, arenas in campaign_chapters(campaign_of(chapter)):
        if name == chapter:
            return max(0, 3 * before - SPARE_STARS)
        before += len(arenas)
    return 0
