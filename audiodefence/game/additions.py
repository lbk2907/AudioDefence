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
#: asks to be played with `fasterEnemies` twice over, which is `enemi_speed_modifier` at 1.4: the same
#: crowd, forty per cent less time to deal with it.
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
#: and it never asks whether a Riot Gear Zombie's shield is up.  A Berserk woken is 225 life charging, a Dodge
#: shot steps aside, a shield raised is a wall - so the grenades are the way through.
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

# ------------------------------------------------------------------------------------ Shooting Gallery
#: Targets that stand still, and walkers that do not.
#:
#: Bob, Jim and Ted are the tutorial's dummies: a whole zombie's sound set and a speed of 0, so they stand
#: where they spawn and groan there for ever, and `brickIsCleared` 0x1000a1658 will not pass a wave until
#: they are dead - nothing about them is dangerous, and nothing ends without them.  Bob has 1 life.  Jim and
#: Ted have 10, which the revolver's `dispersal` 90 makes two rounds at level one anywhere outside its
#: ten-degree `criticalSpread` (9 and a fraction a round) and one inside it (x1.3), so a round well centred is
#: worth two; with 999 rounds that is a lesson and never a lock.  They stand five to ten units out, where the
#: wok cannot reach them, and at least 25 degrees from any walker's bearing, so a round meant for a walker
#: never finds one of them instead.
#:
#: The walkers are ordinary ones from ten units, four to seven seconds apart and never more than three
#: within five units in any eight seconds, so there is always a quiet moment to go looking.  Each wave's
#: standing ones are harder to hear than the last: Ted, as loud as a Zombie, and Bob, 3 dB under, in the
#: first, Ted alone for four seconds, 35 degrees from where the player starts facing; Jim, 6 dB under, in
#: the second; and in the last all three further out, and the diamond, whose glow is 6 dB under a Zombie and
#: ten units away, arriving while four walkers are on their way in.
#:
#: The diamond is the only one in this arena that pays.  `Enemy.die` pays a diamond only to an enemy whose
#: key is exactly `Diamond`, and `_wave` numbers its keys, so it is written into the last wave by hand.
PLISTS['port_gallery_1'] = _wave(
    [('Ted', 235, 7.0), ('WeakZombie', 20, 10.0, 4.0), ('Zombie', 150, 10.0, 10.0),
     ('Bob', 80, 6.0, 14.0), ('ZombieB', 320, 10.0, 18.0)], no_blast=True)
PLISTS['port_gallery_2'] = _wave(
    [('Jim', 45, 8.0), ('Zombie', 200, 10.0, 2.0), ('WeakZombieB', 330, 10.0, 6.0),
     ('Bob', 160, 8.0, 9.0), ('ZombieB', 100, 10.0, 11.0), ('Ted', 290, 9.0, 15.0),
     ('Zombie', 20, 10.0, 16.0), ('WeakZombie', 240, 10.0, 20.0)], no_blast=True)
PLISTS['port_gallery_3'] = _wave(
    [('Jim', 330, 9.0), ('Zombie', 20, 10.0, 2.0), ('ZombieB', 250, 10.0, 5.0),
     ('Bob', 60, 9.0, 8.0), ('WeakZombie', 100, 10.0, 9.0), ('Zombie', 180, 10.0, 12.5),
     ('WeakZombieC', 300, 10.0, 16.0), ('Ted', 210, 10.0, 16.0), ('ZombieC', 0, 10.0, 19.5),
     ('ZombieB', 260, 10.0, 23.0)], no_blast=True)
PLISTS['port_gallery_3']['Enemies']['Diamond'] = {'spawn_angle': 140.0, 'spawn_distance': 10.0,
                                                  'spawn_time': 12.0}
PLISTS['port_gallery'] = {
    'challenge_id': 'port_gallery',
    'title': 'Shooting Gallery',
    'objective': 'Not all of them are coming for you. The ones that are not will still have to be found.',
    'tip': 'If the walking stops and the wave does not end, something is still out there. It is not going '
           'anywhere, and it will wait for you.',
    'icon': 'Challenge_icon_02', 'icon_title': 'SG',
    'weapons': [{'name': 'pistol', 'ammo': '999'}, {'name': 'wok'}],
    'bricks': ['port_gallery_1', 'port_gallery_2', 'port_gallery_3'],
    'ambient': {'ambientPlaylist': 'ambient_roman', 'gain': 0.5},
    'time_limit_star': {'reward': 150, 'objective': 150},
    'accuracy_star': {'reward': 150, 'objective': 60},
}

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
    'ambient': {'ambientPlaylist': 'ambient_arena', 'gain': 0.5},
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
_ARRIVE = {'QuietZombie': 0.58, 'Zombie': 1.51, 'ZombieB': 1.25, 'ZombieC': 1.90, 'Runner': 1.44,
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
    'ambient': {'ambientPlaylist': 'ambient_arena', 'gain': 0.5},
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
#: still wins: the tool cannot price a dummy that holds a wave or a Farty's blast.  Shooting Gallery, the
#: gentlest there is, comes first; Busker, the Banjo's, before The Survivor; Fore after Sidestep; and Bad
#: Company before Powder Keg, so the Farty is met where it is the whole idea before it is one of several;
#: Cattle Call, the prod's, second in chapter 3 and Front Line, the Tactical's, after Rust; Bonfire Night,
#: gentler than anything else in chapter 4, straight after the Sawn-off is bought for Point Blank, and Short
#: Game after Fuse, which is where the launcher is bought.
#:
#: The chapters are the port's own structure and not worlds in `challenges_index`, which they could have
#: been: `apply_to` reaches that file and the world list would have given locks, star counts and a
#: "you need N stars" row for nothing.  It would also have changed Somethin' Else's game.
#: `totalStarsUnlocked` 0x10001ecd4 sums every world in that file, and their City Crossroad opens at 25
#: stars and Maya Ruin at 40 - so twenty-one stars' worth of arenas of ours would have opened their worlds
#: early, for a player who had not touched them.  Counting on this side costs a screen and a few lines and
#: leaves their progression exactly as they shipped it.
CHAPTERS = (
    #: The guns a player already owns, and the Banjo, which at 1500 coins is the first most will buy: in
    #: the order the tool measures, 15.7 seconds of slack down to 2.2, with the second round's placed round it.
    ('Chapter 1', ('port_gallery', 'port_barnyard', 'port_wall', 'port_clockwork', 'port_three_bullets',
                   'port_scrap', 'port_nowake', 'port_busker', 'port_survivor')),
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
)

#: How many of the stars in the chapters before it a chapter may be opened without (user request): two.
#: Every chapter asks for all the stars the chapters before it hold but these - 25 of chapter 1's 27 for
#: chapter 2, 49 of 51 for chapter 3, 73 of 75 for chapter 4 - and two is less than the three an arena is
#: worth, so no arena can be left unbeaten on the way: what may be missed is two accuracy or time stars,
#: across everything behind you.  It does not shrink as the chapters go on, because at nought a single star
#: a player cannot win - The Last Word's time star, say - would shut every chapter after it for good.
#: It was 12, 26 and 40 at first, which let a player into a chapter with a third of the one before unplayed.
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


def chapter_stars_required(chapter: str) -> int:
    """Every star the chapters before this one hold, less `SPARE_STARS`; the first chapter is open."""
    before = 0
    for name, arenas in CHAPTERS:
        if name == chapter:
            return max(0, 3 * before - SPARE_STARS)
        before += len(arenas)
    return 0
