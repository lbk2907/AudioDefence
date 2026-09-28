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
#: Chapter 1, in the order they open, which is the order `tools/arena_pressure.py` puts them in.
#:
#: That tool exists because of how this game kills you.  There is no health: an enemy that reaches the
#: player ends the game there and then, so what makes a wave hard is not how much life is in it but whether
#: every one of them can be killed before its own clock runs out - and the clock of the one behind it is
#: already running.  It works that out wave by wave and prints the slack at the tightest moment, and the
#: seven arenas below are tuned to a deliberate curve of it, from eleven seconds to spare down to nine
#: seconds short.  Short is not impossible: the tool counts only the gun, and a player also has a wok
#: worth 25 a swing inside three units, headshots, and whatever they have spent diamonds on.
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
#: asks to be played with `fasterEnemies` twice over, which is `enemi_speed_modifier` at 1.4: the same
#: crowd, forty per cent less time to deal with it.
PLISTS['port_stampede_1'] = _crowd(('Runner', 'RunnerB'), 4, 12.0, 4.0)
PLISTS['port_stampede_2'] = _crowd(('Runner', 'Chainsaw', 'RunnerB', 'RunnerC'), 6, 12.0, 3.2)
PLISTS['port_stampede_3'] = _crowd(('Runner', 'Clown', 'Chainsaw', 'RunnerB', 'RunnerC'), 9, 12.0, 3.2)
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
    #: A flag written twice is applied twice, and `times()` counts the stack, so this is +40% speed.
    'Modifiers': ['fasterEnemies'],
    'time_limit_star': {'reward': 200, 'objective': 120},
    'accuracy_star': {'reward': 200, 'objective': 35},
}

# ------------------------------------------------------------------------------------ Three Bullets
#: Three rounds, and three things out there that no number of rounds will reach any other way.
#:
#: Ted, Jim and Bob are zombies with the whole sound set - spawn, approach, aggressive, hit, death - and a
#: speed of 0.  They stand where they spawn and never come, so the wok cannot touch them (it reaches 3) and
#: `brickIsCleared` 0x1000a1658 will not pass the wave until they are dead.  Ted and Jim have 10 life, which
#: is exactly one revolver round at level one and less than one at every level above it.  So: one round
#: each, three of them, three rounds, and no modifier propping it up.
#:
#: Everything else in here walks, and has to be met with the wok at arm's length, because there is nothing
#: left to shoot it with.  A WeakZombie is one swing and a Zombie is two; they arrive far enough apart to be
#: taken one at a time and near enough together that there is no time to think between them.  Spend a round
#: on one of them and the wave it belongs to cannot be finished at all.
PLISTS['port_three_bullets_1'] = _wave(
    [('Ted', 200, 9.0), ('WeakZombie', 0, 9.0, 2.0), ('Zombie', 120, 9.0, 8.0)], no_blast=True)
PLISTS['port_three_bullets_2'] = _wave(
    [('Jim', 60, 10.0), ('Zombie', 250, 9.0, 1.0), ('WeakZombie', 140, 9.0, 4.0),
     ('ZombieB', 20, 9.0, 8.0)], no_blast=True)
PLISTS['port_three_bullets_3'] = _wave(
    [('Ted', 310, 10.0), ('Zombie', 45, 9.0, 1.0), ('ZombieB', 190, 9.0, 3.0),
     ('Runner', 105, 9.0, 7.0), ('WeakZombieB', 265, 9.0, 11.0), ('ZombieC', 330, 9.0, 15.0)],
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
#: `set_life` 0x100061a00 sends it into state 7 every time it is hit and survives: 3.5 units sideways, which
#: at ten units out is nineteen degrees and so outside the revolver's spread of thirty.  Eight rounds at
#: level one means being found again eight times, while it closes at 0.9 - and the walkers arriving behind it
#: do not wait for that.
PLISTS['port_sidestep_1'] = _wave(
    [('Dodge', 60, 12.0), ('WeakZombie', 200, 10.0, 4.0), ('Zombie', 300, 10.0, 10.0)], no_blast=True)
PLISTS['port_sidestep_2'] = _wave(
    [('Dodge', 30, 12.0), ('DodgeB', 210, 12.0, 10.0), ('Zombie', 120, 10.0, 3.0),
     ('WeakZombie', 280, 10.0, 11.0), ('ZombieB', 160, 10.0, 18.0)], no_blast=True)
PLISTS['port_sidestep_3'] = _wave(
    [('Dodge', 20, 12.0), ('DodgeB', 150, 12.0, 9.0),
     ('Zombie', 90, 10.0, 2.0), ('Runner', 330, 11.0, 8.0), ('ZombieB', 190, 10.0, 15.0),
     ('QuietZombie', 60, 10.0, 21.0)], no_blast=True)
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
#: that many seconds after the named one **dies**.  So three seeds stand out there, each with two behind it,
#: and nothing else happens until a seed is killed.  Which means the player decides when the next pair comes,
#: and the arena is really a question about pacing: kill them one at a time and the wave takes for ever
#: against the clock, kill them together and six arrive at once.
def _hydra(seeds, broods, after: float = 3.0) -> dict:
    """Seeds standing out there, and behind each of them a brood that waits for it to die.

    `spawn_after` names another enemy by the key it is written under, so the numbering `_wave` gives has to
    be worked out here: the seeds go in first and are keys 1..n, and each brood follows.  An enemy with a
    `spawn_after` and no `spawn_time` is built and then left alone by `Brick.__init__`, and
    `checkSpawnAfterKill:` 0x1000a20ac is what eventually starts its clock.
    """
    spec = list(seeds) + [one for brood in broods for one in brood]
    wave = _wave(spec, no_blast=True)
    keys = list(wave['Enemies'])
    seed_keys = keys[:len(seeds)]
    i = len(seeds)
    for seed_key, brood in zip(seed_keys, broods):
        for _one in brood:
            wave['Enemies'][keys[i]] = dict(wave['Enemies'][keys[i]],
                                            spawn_after={'enemy': seed_key, 'time': after})
            wave['Enemies'][keys[i]].pop('spawn_time', None)
            i += 1
    return wave


PLISTS['port_hydra_1'] = _hydra(
    (('Zombie', 45, 9.0), ('Zombie', 225, 9.0)),
    ([('WeakZombie', 20, 11.0), ('WeakZombieB', 70, 11.0)],
     [('WeakZombieC', 200, 11.0), ('WeakZombieD', 250, 11.0)]))
PLISTS['port_hydra_2'] = _hydra(
    (('Zombie', 30, 9.0), ('Zombie', 150, 9.0), ('Zombie', 270, 9.0)),
    ([('WeakZombie', 10, 11.0), ('WeakZombieB', 50, 11.0)],
     [('WeakZombieC', 130, 11.0), ('WeakZombieD', 170, 11.0)],
     [('Zombie', 250, 11.0), ('ZombieB', 290, 11.0)]))
PLISTS['port_hydra_3'] = _hydra(
    (('Zombie', 20, 8.5), ('Zombie', 110, 8.5), ('Zombie', 200, 8.5), ('Zombie', 290, 8.5)),
    ([('WeakZombie', 0, 11.0), ('ZombieB', 40, 11.0)],
     [('WeakZombieB', 90, 11.0), ('ZombieC', 130, 11.0)],
     [('Runner', 180, 11.0), ('WeakZombieC', 220, 11.0)],
     [('Runner', 270, 11.0), ('WeakZombieD', 310, 11.0)]))
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
     ('Runner', 200, 11.0, 34.0), ('RunnerB', 120, 11.0, 39.0), ('Chainsaw', 240, 11.0, 44.0),
     ('Clown', 60, 11.0, 49.0)], no_blast=True)
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


#: The port's own arenas, gathered into chapters (user request).
#:
#: A chapter is `(name, stars needed to open it, the arenas in it)`.  Inside a chapter each arena names the
#: one before it in `challenges_requirement` - the original's own key, read by
#: `hasChallengeRequirementsForChallengeWithName:` 0x10001ffbc - so an arena opens when the one before it is
#: beaten, and a chapter opens on **stars**, which is how the original gates a world.
#:
#: The order is the one `tools/arena_pressure.py` measures, easiest first and across both chapters
#: rather than within each (user request), so the first arena of chapter 2 carries on from the last of
#: chapter 1.  Three Bullets is the exception and is placed by judgement: it is fought with the wok, and
#: what the tool cannot price is that a melee duel with no health is the frightening thing in this game.
#:
#: The chapters are the port's own structure and not worlds in `challenges_index`, which they could have
#: been: `apply_to` reaches that file and the world list would have given locks, star counts and a
#: "you need N stars" row for nothing.  It would also have changed Somethin' Else's game.
#: `totalStarsUnlocked` 0x10001ecd4 sums every world in that file, and their City Crossroad opens at 25
#: stars and Maya Ruin at 40 - so twenty-one stars' worth of arenas of ours would have opened their worlds
#: early, for a player who had not touched them.  Counting on this side costs a screen and a few lines and
#: leaves their progression exactly as they shipped it.
CHAPTERS = (
    #: Every arena a player already owns the guns for, in the order the tool measures: 15.7 seconds of
    #: slack down to 2.2.
    ('Chapter 1', 0, ('port_barnyard', 'port_wall', 'port_clockwork', 'port_three_bullets',
                      'port_scrap', 'port_nowake', 'port_survivor')),
    #: Where the slack runs out: 1.4 seconds short down to 11.2.  Twelve of chapter 1's twenty-one stars
    #: opens it, so a player who could not finish one of its arenas is not stopped here, and one who took
    #: every star is well past it.
    ('Chapter 2', 12, ('port_longwalk', 'port_stampede', 'port_sidestep', 'port_keg', 'port_hydra',
                       'port_biggame')),
)

#: Every arena of the port's, in the order they are played.  What `go_to_challenge_list_for` and the
#: overview's Back ask, to know an arena of ours from one of theirs.
EXTRA_CHALLENGES = tuple(name for _c, _s, arenas in CHAPTERS for name in arenas)


#: What an arena needs before it can be played, and what finishing it pays, worked out from the order above
#: rather than written into each arena by hand.  They are facts about the order and nothing else, and while
#: they were written by hand they were wrong twice - once pointing an arena at itself two places back, once
#: leaving the rewards climbing inside each chapter but not across the pair.  `challenges_requirement` is the
#: original's own key (`hasChallengeRequirementsForChallengeWithName:` 0x10001ffbc) and this fills it in the
#: same shape their own challenges use.
def _derive_order() -> None:
    reward = 200
    for _chapter, _stars, arenas in CHAPTERS:
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
    for name, _stars, arenas in CHAPTERS:
        if challenge_id in arenas:
            return name
    return None


def chapter_arenas(chapter: str) -> tuple:
    for name, _stars, arenas in CHAPTERS:
        if name == chapter:
            return arenas
    return ()


def chapter_stars_required(chapter: str) -> int:
    for name, stars, _arenas in CHAPTERS:
        if name == chapter:
            return stars
    return 0
