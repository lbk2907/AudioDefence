"""PORT ADDITION (user request): challenges a player writes, and the Challenge maker that generates them.

`additions.py` is where the *port* invents content; this is where a **player** does.  A file dropped into
the challenges folder beside the executable is read as an arena of its own, in the Extra screen, and is
played by the same code that plays the original's challenges - `data._load` falls back to what is declared
here exactly as it falls back to `additions.PLISTS`, so every one of the twenty-two places that read the
game's data finds a custom challenge without knowing it is one.

The three rules this file keeps
-------------------------------
* **Nothing a player writes can reach the game's own progression.**  `totalStarsUnlocked` 0x10001ecd4 gates
  the original's worlds and `challenge_data.total_stars_unlocked_for_chapters` gates the port's chapters;
  a custom arena is in neither list, so a folder of generated arenas cannot open City Crossroad, Maya Ruin
  or Chapter 6.  It pays its coins (user decision) and remembers its own three stars, and that is all.
* **A bad file is a line in the log and a row on a screen, never a crash.**  Everything here is read
  defensively: a missing key, a string where a number was meant, a wave with nothing in it, an enemy the
  game has never heard of.  The file is skipped, the reason is kept in `PROBLEMS`, and the Challenge maker
  reads them out.
* **What is generated has to be winnable.**  This game has no player health - one enemy reaching you ends
  the run (`attack` 0x100060304) - so a wave is not the life in it but whether each enemy can be killed
  before its own clock runs out.  The generator sizes every wave against that, the way
  `tools/arena_pressure.py` measures the port's own arenas, and widens the gap between arrivals until the
  tightest moment leaves the slack it was asked for.

The file format
---------------
Two kinds of file, both JSON in UTF-8, distinguished by their suffix:

* `<name>.adchallenge` - one challenge.
* `<name>.adpack` - an arena, and the challenges in it.

A challenge object::

    {
      "format": "audiodefence-challenge",   (a pack's challenges leave this out)
      "version": 1,
      "id": "dead_air",                     optional; made from the title otherwise
      "title": "Dead Air",
      "arena": "My Arena",                  .adchallenge only (a pack names its own); the arena this goes
                                            in, defaulting to LOOSE_ARENA, where loose files gather
      "objective": "What the overview says this asks of you.",
      "tip": "What the overview offers as advice.",
      "ambient": "ambient_roman",           a playlist under game/meta; default ambient_roman
      "ambient_gain": 0.5,
      "modifiers": ["fasterEnemies"],       flags of GameModifiers; see modifiers.FLAGS
      "difficulty": "busy",                 quiet, busy or desperate: how much slack a rerolled wave
                                            leaves at its tightest moment (MARGINS)
      "weapons": [{"name": "pistol", "ammo": 60}, {"name": "wok"}],
      "requires": ["another_id"],           the "id" of challenges of this pack to be beaten first
      "coins": 200,                         paid for finishing; DEFAULT_REWARD if left out, REWARD_CAP
                                            at the most
      "accuracy": {"objective": 45, "reward": 150},
      "time": {"objective": 150, "reward": 150},
      "waves": [ ...wave objects... ]
    }

A wave object::

    {
      "rigged": false,        every enemy carries the Farty's blast: one shot takes the wave
      "no_blast": true,       and refuses them the blast Chain Reaction would lend
      "enemies": [{"kind": "Zombie", "angle": 0, "distance": 10, "at": 0.0},
                  {"kind": "Hulk", "angle": 180, "distance": 12,
                   "after": {"enemy": "Zombie 1", "time": 2}}],
      "passers": [{"kind": "Cow", "angle": 70, "distance": 11, "at": 1.0}],
      "powerup": 8,           an air drop eight seconds in; {"at": 8, "kind": "tesla"} names which
      "diamonds": 2,          diamonds in the arena for this wave, up to MAX_DIAMONDS
      "zombie_themes": false, play this wave without the music its zombies bring
      "before": [ ...cutscene lines... ],   played on its own, before the crowd arrives
      "cutscene": [ ...cutscene lines... ], played while the crowd is being fought
      "after": [ ...cutscene lines... ]     played on its own, once the wave is cleared
    }

`powerup` is one air drop in the wave, `at` seconds after it starts.  `kind` is `any` - whatever the game
feels like, which is what Endless gives - or one of `minigun`, `fireworks`, `tornado`, `tesla`.  A
challenge's drop always arrives: the kind that waits for the air-drop cooldown cannot come at all outside
Endless, which is written up at `POWERUP_KINDS`.

A wave has three cutscenes, then, and a challenge of ten waves has eleven seams to put a scene in - the
`after` of the last wave being the end of the challenge.  `before` and `after` each become a wave of
nothing but that cutscene, which is one of the original's own shapes (`tutorial_7_brick_4`), so they are
not a mode of their own: the arena is quiet, the lines play, and the next wave starts when the last of
them has finished.  A wave still needs zombies or a cutscene of its own, though: a `before` and an `after`
are waves of their own by then, so they do nothing to bring the wave they are written on to an end.

A cutscene line - the original's scripted sounds (`ADSound` 0x1000b2d68), which is what its challenges
say their dialogue with.  `"cutscene": "my_line"` and `"cutscene": ["my_line"]` are both the short way of
writing the first form below, and `before` and `after` are written exactly the same way::

    {
      "sound": "my_line",     a file in the challenges folder's `audio` folder, without its extension
      "at": 0,                seconds from the wave starting; default 0
      "after": "other_line",  or start it when `other_line` has finished instead of at a time
      "after": {"sound": "other_line", "time": 1.5, "when": "starts"},   the long form of the same
      "blocker": true,        the wave is not cleared until this has finished; default true
      "skippable": true,      the Skip button ends it; default true
      "stops_other_sounds": false,
      "gain": 0,              louder than it was recorded, 0 for as it is
      "loop": false,
      "angle": 90, "distance": 6,      where it is heard from, if it stands still
      "from": [-8, 4], "to": [8, 4]    or where it walks from and to, while it talks
    }

A pack object::

    {"format": "audiodefence-pack", "version": 1, "arena": "My Arena",
     "challenges": [ ...challenge objects... ]}

**A pack may carry its own recordings.**  A `.adpack` is either the JSON above or a zip holding that JSON
and the sounds its cutscenes name, under `audio/`.  Both are read, and both are called `.adpack`, because
which one a file is is nobody's business but the reader's: what matters is that a pack with dialogue in it
is *one file* to hand to somebody rather than a folder of recordings to send alongside.  `pack_up` writes
one, and the first read of one puts its sounds into the audio folder beside everybody else's - under
another name if that name is taken by a different recording, with the pack's own lines pointed at the name
it ended up with (`_unpack`).

`angle` is degrees clockwise from where the player starts, `distance` is units out, and `at` is seconds
from the wave starting.  `after` starts an enemy's clock when the one it names dies (`checkSpawnAfterKill:`
0x1000a20ac), naming it by its slot - the kind, a space, and its place in the list from one.
"""
from __future__ import annotations

import json
import logging
import math
import os
import random
import re

from .. import paths

log = logging.getLogger('game.custom')

# ============================================================================================ the format
FORMAT_CHALLENGE = 'audiodefence-challenge'
FORMAT_PACK = 'audiodefence-pack'
FORMAT_VERSION = 1
CHALLENGE_SUFFIX = '.adchallenge'
PACK_SUFFIX = '.adpack'

#: Every name a custom file declares is written into the game's data under this, so nothing a player writes
#: can shadow a plist of the original's or of the port's - `data._load` looks in the bundle first, then in
#: `additions.PLISTS`, and only then here.
PREFIX = 'custom_'

#: Where a `.adchallenge` with no `arena` of its own goes.  A pack names its arena; a loose file is one
#: challenge somebody made, and they all gather in one row rather than one row each.
LOOSE_ARENA = 'Custom Challenges'

#: What a file may ask for.  These are not balance: they are what keeps a mistyped number - a wave of forty
#: thousand, an enemy arriving in the year three thousand - from hanging the game before anybody can see it.
MAX_WAVES = 12
MAX_ENEMIES = 40
MAX_PASSERS = 8
MAX_CUTSCENE = 8
#: PORT ADDITION (user request, 2026-10-01): how many diamonds one wave may be given.  Eight, as the
#: passers-by are: enough for a wave built around collecting them and not so many that a mistyped number
#: fills the arena with things that are not zombies.
MAX_DIAMONDS = 8
MAX_CHALLENGES = 24
MAX_FILES = 64
MIN_DISTANCE, MAX_DISTANCE = 4.0, 20.0
MAX_SPAWN_TIME = 600.0

#: PORT DECISION (user request, 2026-09-30): a custom challenge pays the coins its file asks for, capped
#: here, and its stars open nothing.  A thousand is the most the game itself pays for finishing anything:
#: all 45 of the original's challenges were measured and `urban_10` and `maya_10`, the last of each world,
#: are the two that pay it, the other 43 paying 500 or 200.  So a challenge somebody wrote can be worth as
#: much as the hardest challenge the game has, and no more.  Each star has the same ceiling, which is a
#: cap rather than a rate: anybody who can write the file can also write themselves an easy one, so this is
#: here to keep a mistyped number from being absurd, not to stand between a player and their own coins.
#:
#: Raised from 200 on 2026-09-30 (user request).
REWARD_CAP = 1000

#: What a challenge pays when its file does not say, and what the generator writes into one it makes.  Two
#: hundred is what a chapter-1 arena of the port's pays and what every challenge of the original's first two
#: worlds pays, so an arena generated at random is worth playing without being the quickest way to an armory
#: a player has not earned.  Deliberately not `REWARD_CAP`: the ceiling went up for challenges somebody
#: writes on purpose, and a generated one has not earned the top of it.
DEFAULT_REWARD = 200

#: PORT ADDITION (user request, 2026-09-30): the three places a wave can have a cutscene, in the order they
#: are heard.  `during` is `Sounds` on the brick, which is the original's own key - but dialogue that runs
#: while the crowd is being fought is *not* the original's own habit, and this is the unusual one of the
#: three.  Counted over the game's own data: of the 220 zombies in bricks that also carry dialogue, 124
#: wait for a line before they arrive and 94 wait for another zombie that does, two have a clock of their
#: own (`maya_2_brick_3`, a single Hulk) and none at all simply arrives.  45 of those 47 bricks hold every
#: zombie back until a line has played.  So `before` and `after` - a scene with the arena to itself - are
#: what a cutscene usually is, and what the editor adds; they are not new machinery, only a new place to
#: write one.  `_challenge` gives each its own brick holding nothing but the cutscene, which is a shape the
#: original already has: `tutorial_7_brick_4`, the closing line of "Meet The Farty", is exactly
#: `{'Sounds': [...]}` and nothing else, and `brickIsCleared` 0x1000a1658 holds such a wave on its
#: `blocker` until the line has finished.  So a challenge of ten waves has eleven seams to put a scene in,
#: and `after` on the last wave is the end of the challenge.
PLACES = ('before', 'during', 'after')

#: Where each is kept on the wave dictionary.  `during` is the original's key because it *is* the
#: original's; the other two are the port's own, read by nothing in the game - `_challenge` takes them off
#: the wave and makes bricks of them, and `_wave_to_object` writes them back.
PLACE_KEYS = {'before': 'custom_before', 'during': 'Sounds', 'after': 'custom_after'}

#: And what each is called in the file a player writes.
_WRITTEN_AS = {'before': 'before', 'during': 'cutscene', 'after': 'after'}


#: PORT ADDITION (user request, 2026-09-30): the air drops a wave can be given, by the names
#: `forceToPopPowerUpContainerWithType:` 0x1000c7b68 matches (it upper-cases what it is handed).  `any` is a
#: drop with no kind named, which is what that method falls through to and what every Endless wave asks for.
POWERUP_KINDS = ('any', 'minigun', 'fireworks', 'tornado', 'tesla')

#: A wave's drop is always a *forced* one (`force_spawn_time`), never the kind that waits for the air-drop
#: cooldown (`spawn_time`).  The cooldown only runs down in Endless - `ADBrickManager update:` 0x1000c37b0
#: ticks `ADPowerUpManager update:` 0x10004b5a4 under `mode == 1` and nowhere else - so in a challenge it
#: sits at whatever `resetPowerUpCooldown` left it (90 seconds at level 1) for the whole run, and
#: `tryToPopPowerUpContainer` 0x1000c7b4c refuses every time it is asked.  Measured both ways: after 30
#: seconds of Endless the cooldown had gone 90 -> 60, and after 30 seconds of a challenge it was still 90.
#:
#: The game's own data says the same thing twice over: all 29 of its `spawn_time` blocks are Endless bricks
#: (`level3_brick_2` and the rest) and all 8 of its `force_spawn_time` ones are challenges - maya, urban and
#: the tutorials - as are all 13 of the port's own.  So a challenge that asked to wait would be a wave with
#: a drop in its file and no drop in the arena, which is the one thing not worth offering.

#: PORT ADDITION (user request, 2026-09-30): the four things besides zombies that a challenge can ask to
#: have in the arena.  Each is a `GameModifiers` flag of the original's own (`modifiers.FLAGS`) and the arena
#: furniture it switches on is the original's own too - `ADPasserByManager` 0x1000d570c owns all of it - so
#: this is a list of what to offer and not new content.  The order is the order the editor shows them in:
#: the two that keep arriving, then the two that are placed once.
ARENA_EXTRAS = ('cows', 'cars', 'jukebox', 'machine', 'storm')

#: Of those, the flags that turn something *off*.  Their row would read yes when the flag is *not* there, so
#: that every row in that part of the editor means the same thing: yes is what is happening in the arena.
#: None of them does now; the one that did became a setting of each wave's instead (`ZOMBIE_THEMES`).
ARENA_EXTRAS_INVERTED = ()

#: What to call the ones the tarot deck has no card for; `arena_extras` reads the rest off the cards.
_EXTRA_WORDS: dict = {}

#: PORT ADDITION (user request, 2026-10-01): how many diamonds a wave puts in the arena.  `addDiamond`
#: 0x1000c7748 is the original's own - a `DiamondDropper` on `Diamond` out of `enemies.plist`, placed at a
#: bearing of its own choosing nine units out, arriving two seconds later and leaving about nine seconds
#: after that unless it is shot.  Endless drops one every 40 to 70 seconds and nothing else ever does, so a
#: challenge had none at all; a wave can now ask for some.  Written on the brick under a key of the port's
#: own, which `BrickManager.load_brick_with_name` reads.
WAVE_DIAMONDS = 'Diamonds'

#: PORT ADDITION (user request, 2026-10-01): whether a wave plays the music its zombies bring with them.
#: Six of the game's enemies carry an `ambiant` in `enemies.plist` - the Chainsaw, Hulk and HulkB, the
#: Whisperer, Dodge and DodgeB, four themes between them - and `AmbientManager.check_ambiant` 0x100099444
#: starts whichever one is standing in the arena.  A wave at a time and not a challenge at a time: what
#: somebody wants quiet is usually one wave of a storyline rather than all of them, so the row is in the
#: wave editor.  Written on the brick under a key of the port's own, which nothing of the game's reads.
ZOMBIE_THEMES = 'NoZombieThemes'

#: The challenge-wide flag this was before it became a wave's setting.  A file written in that day is still
#: read: `_challenge` turns it into the key above on every wave and drops the flag, so nobody's arenas
#: stopped working when it moved.  `modifiers.PORT_FLAGS` still accepts the name for that reason.
_OLD_THEME_FLAG = 'noZombieThemes'


def arena_extras() -> list:
    """[(flag, title, what it does)] for `ARENA_EXTRAS`, in the game's own words.

    The words are read out of `Tarot.plist` rather than written here, because each of these four is also one
    of the game's own tarot cards and a card already says what its flag does - "Car alarms will go off around
    you. Shoot the cars to blow them up!".  Reading them means the editor cannot drift from the cards, and
    means the rows are already translated: every card's title and description is a phrase the language files
    carry.  A flag whose card is missing falls back to the flag's own name, which is the one thing that
    cannot be absent.
    """
    from . import data
    said = {}
    tarot = data.plist_ro('Tarot') or {}
    for level in tarot.values() if isinstance(tarot, dict) else ():
        for card in level if isinstance(level, list) else ():
            if isinstance(card, dict) and card.get('selector') in ARENA_EXTRAS:
                said[card['selector']] = (str(card.get('title') or ''), str(card.get('description') or ''))
    return [(flag,) + said.get(flag, _EXTRA_WORDS.get(flag, (flag, ''))) for flag in ARENA_EXTRAS]


def arena_extra_is_on(modifiers, flag: str) -> bool:
    """Whether a challenge's `modifiers` put that one in the arena.

    Directly, or as half of one of the port's level-4 flags (`PAIRED_FLAGS`): a file is allowed to name one
    of those, and a row that read "no" while the cows were walking about would be a row that lies.
    """
    from .modifiers import PAIRED_FLAGS
    for named in modifiers or ():
        if named == flag or flag in PAIRED_FLAGS.get(named, ()):
            return True
    return False


def arena_extra_shows_yes(modifiers, flag: str) -> bool:
    """What the row reads: yes when the thing is happening in the arena.

    For most of them that is the flag being there.  For the ones in `ARENA_EXTRAS_INVERTED` the flag is what
    turns the thing *off*, so the row reads yes when it is absent - a zombie's theme plays unless a challenge
    has said not to, and a row that read no for the game's own behaviour would be a row nobody could follow.
    """
    present = arena_extra_is_on(modifiers, flag)
    return (not present) if flag in ARENA_EXTRAS_INVERTED else present


def paired_sources_of(modifiers, flag: str) -> list:
    """The level-4 flags in `modifiers` that bring `flag` with them, if any.

    The editor's toggle takes out the plain flag and leaves these alone - removing `cattleMarket` to stop the
    cows would quietly take away the lucky night it also gives - so it says which ones are still bringing it.
    """
    from .modifiers import PAIRED_FLAGS
    return [named for named in modifiers or () if flag in PAIRED_FLAGS.get(named, ())]


def diamonds_in(wave: dict) -> int:
    """How many diamonds this wave puts in the arena."""
    try:
        return max(0, min(MAX_DIAMONDS, int(wave.get(WAVE_DIAMONDS) or 0)))
    except (TypeError, ValueError):
        return 0


def set_diamonds(wave: dict, count: int) -> None:
    """That many, or none at all, which takes the key off rather than writing a nought."""
    count = max(0, min(MAX_DIAMONDS, int(count)))
    if count:
        wave[WAVE_DIAMONDS] = count
    else:
        wave.pop(WAVE_DIAMONDS, None)


def zombie_themes_in(wave: dict) -> bool:
    """Whether this wave plays the music its zombies bring with them.

    True unless it has been turned off, because playing it is what the game itself does.
    """
    return not (wave.get(ZOMBIE_THEMES) or False)


def set_zombie_themes(wave: dict, on: bool) -> None:
    """Turn them on or off for one wave.  On takes the key off rather than writing a false, so a wave that
    never said anything about it is written the way it was."""
    if on:
        wave.pop(ZOMBIE_THEMES, None)
    else:
        wave[ZOMBIE_THEMES] = True


def cutscene_of(wave: dict, where: str) -> list:
    """The lines of one of a wave's three cutscenes, in the order they are played."""
    return list(wave.get(PLACE_KEYS[where]) or ())


def set_cutscene(wave: dict, where: str, lines) -> None:
    """Those lines, put back.  An empty cutscene takes its key off the wave rather than sitting there as an
    empty list, so a wave that never had one is written the way it was."""
    if lines:
        wave[PLACE_KEYS[where]] = list(lines)
    else:
        wave.pop(PLACE_KEYS[where], None)


#: A `.adchallenge` or `.adpack` bigger than this is not read.  A challenge is a page of JSON; anything
#: past this is a file that is not one, and reading it would only be a slow way to find that out.
MAX_FILE_BYTES = 1 << 20

#: A zipped pack carries its recordings, so it is a different size of thing: 256 MB, which is a long
#: storyline's worth of speech and still a number that says "this is not a challenge" when it is wrong.
#: What is *inside* it is read against `MAX_FILE_BYTES` like any other pack, so a zip cannot smuggle in a
#: document too big to read.
MAX_PACK_BYTES = 256 << 20

#: What the zip calls things: the document at the top, the recordings in a folder beside it.
PACK_DOCUMENT = 'pack.json'
PACK_AUDIO_DIR = 'audio'


# ======================================================================================== what was loaded
#: plist name -> the dictionary `data._load` hands back for it: the challenges and the waves in them.
PLISTS: dict = {}

#: [(arena title, (challenge id, ...))], in the order the Extra screen lists them.
ARENAS: list = []

#: [(file name, why it was skipped)] - what the Challenge maker reads out.
PROBLEMS: list = []

_LOADED = False


class _Bad(Exception):
    """A file that cannot be read.  Its message is what the player is told."""


# ======================================================================= the cutscenes' own recordings
#: Where the sounds a player's cutscenes use are kept: one folder under the challenges folder, so a pack
#: and the recordings it speaks with can be handed to somebody else together.
#:
#: The engine finds the game's own sounds under `game/sounds/`, which is Somethin' Else's folder, and
#: `additions.py` says in as many words that audible content the port adds "needs a folder of the port's
#: own and an engine that looks in both".  This is that folder, and the looking is one line:
#: `S3DSound.agent_with_entry` builds a path with `os.path.join(paths.BUNDLE, entry.path, ...)`, and
#: `os.path.join` drops what came before an absolute path - so a playlist entry pointing here resolves
#: here, and the engine needed a way in rather than a change to how it reads.
AUDIO_DIR_NAME = 'audio'


def audio_dir(make: bool = False) -> str:
    path = os.path.join(paths.CUSTOM_CHALLENGES, AUDIO_DIR_NAME)
    if make:
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as exc:
            log.info('no audio folder, and none could be made: %s', exc)
    return path


def audio_files() -> dict:
    """{the name a cutscene calls it by: the file}, for every recording in the audio folder.

    The name is the file's own without its extension, so `bastard_intro.wav` is `"bastard_intro"`.  Two
    files of the same name in different formats would be one name; the first by extension order wins, and
    which one that is does not matter, since they are the same recording as far as a cutscene is concerned.
    """
    from ..platform.filedialog import AUDIO_EXTENSIONS
    found: dict = {}
    try:
        names = sorted(os.listdir(audio_dir()))
    except OSError:
        return found
    for name in names:
        stem, extension = os.path.splitext(name)
        if extension.lower() in AUDIO_EXTENSIONS and stem not in found:
            found[stem] = os.path.join(audio_dir(), name)
    return found


def audio_path(key):
    return audio_files().get(str(key))


#: What a recording imported as an ambience is renamed to start with (user request).
#:
#: Not decoration: `startWithambient:gain:` 0x100098004 finds a playlist's looping bed with
#: `any_sound_containing('ambient')`, and a sound's key is its file's own name - so a recording the game
#: will accept as an ambience is one whose file name has "ambient" in it.  Importing puts it there rather
#: than asking a player to know that.
AMBIENCE_PREFIX = 'ambient_'


def ambience_keys() -> list:
    """The ambiences a player has imported, by the name a challenge names one with."""
    return sorted(k for k in audio_files() if k.startswith(AMBIENCE_PREFIX))


def import_ambience(path: str) -> str:
    """A recording imported to be played under an arena rather than spoken over it."""
    return import_audio(path, prefix=AMBIENCE_PREFIX)


def import_audio(path: str, prefix: str = '') -> str:
    """Copy a recording a player chose into the audio folder, and answer the name a cutscene calls it by.

    Copied rather than pointed at: a challenge that named a file somewhere on one machine would be a
    challenge that says nothing on anybody else's, and the point of a pack is that it can be handed over.
    A name already taken gets a number, so importing two different files called `intro.wav` keeps both.
    """
    import shutil
    folder = audio_dir(make=True)
    stem, extension = os.path.splitext(os.path.basename(path))
    key = _slug(stem, 'sound')
    if prefix and not key.startswith(prefix):
        key = prefix + key
    taken = audio_files()
    if key in taken:
        n = 2
        while '%s_%i' % (key, n) in taken:
            n += 1
        key = '%s_%i' % (key, n)
    shutil.copyfile(path, os.path.join(folder, key + extension.lower()))
    log.info('imported %s as %s', path, key)
    return key


# ------------------------------------------------------------------------------------- reading a file
def _slug(text, default: str = 'challenge') -> str:
    out = re.sub(r'[^a-z0-9]+', '_', str(text).lower()).strip('_')
    return out[:48] or default


def _text(where: dict, key: str, required: bool = False, default: str = '') -> str:
    value = where.get(key)
    if value is None or value == '':
        if required:
            raise _Bad('it has no %s' % key)
        return default
    if not isinstance(value, str):
        raise _Bad('its %s is not text' % key)
    return ' '.join(value.split())[:400]


def _number(where: dict, key: str, low: float, high: float, default: float) -> float:
    value = where.get(key)
    if value is None:
        return float(default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _Bad('its %s is not a number' % key)
    if not low <= float(value) <= high:
        raise _Bad('its %s is not between %g and %g' % (key, low, high))
    return float(value)


def _entries(where: dict, key: str, limit: int, required: bool = False) -> list:
    value = where.get(key)
    if value is None:
        if required:
            raise _Bad('it has no %s' % key)
        return []
    if not isinstance(value, list):
        raise _Bad('its %s is not a list' % key)
    if len(value) > limit:
        raise _Bad('it has more than %i %s' % (limit, key))
    for one in value:
        if not isinstance(one, dict):
            raise _Bad('something in its %s is not a block of its own' % key)
    return value


def _names(where: dict, key: str, limit: int = 16) -> list:
    value = where.get(key)
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise _Bad('its %s is not a list of names' % key)
    return value[:limit]


# -------------------------------------------------------------------------------- the game's own data
def _enemies() -> dict:
    from . import data
    return data.plist_ro('enemies') or {}


def _weapons() -> dict:
    from . import data
    return {w.get('name'): w for w in ((data.plist_ro('Weapons') or {}).get('Weapons') or [])
            if isinstance(w, dict)}


def is_melee(weapon) -> bool:
    """Whether a weapon swings rather than fires, by the original's own `melee` key in `Weapons.plist`."""
    return bool((_weapons().get(weapon) or {}).get('melee'))


def _has_sounds(kind: str) -> bool:
    """An enemy the engine can voice.  `Enemy` finds its recordings by name under `sounds/enemies/`, so a
    kind with no folder there spawns silent and invisible and the wave never clears."""
    return os.path.isdir(paths.bundle_path('sounds', 'enemies', str(kind)))


def _base_kind(kind: str) -> str:
    """`RunnerB` is a Runner and `HulkB` a Hulk: the variants of an enemy are its name and one capital."""
    return re.sub(r'[B-D]$', '', str(kind)) or str(kind)


def required_kills(kind: str) -> int:
    """How many more kills the Zombiepedia wants before this enemy is unlocked, nought once it is.

    `getKillRequirementForEnemyWithName:` 0x100084ea8 asks one entry of `enemies.plist`, and the entry that
    carries the requirement is not always the one a wave names: a Runner's own entry holds 0 and is the one
    the Zombiepedia shows, while `RunnerB` and `RunnerC` hold none at all; a Zombie Dog's holds 400 and
    `DodgeB` holds none.  Taking the largest requirement of the enemy, the enemy its name is a variant of,
    and everything sharing its display name means a variant is gated exactly as the entry a player reads
    about it in the Zombiepedia is - which is what "unlocked by the Zombiepedia" has to mean for a wave
    that names `DodgeB`.
    """
    from .persistent_stats import PersistentStats
    stats = PersistentStats.shared()
    return max(stats.kill_requirement_for_enemy(name) for name in _pedia_family(kind))


def _pedia_family(kind: str) -> tuple:
    """The entries the Zombiepedia answers for this kind with: itself, what it is a variant of, and
    everything under the same display name."""
    enemies = _enemies()
    family = {str(kind), _base_kind(kind)}
    display = (enemies.get(kind) or {}).get('displayName')
    if display is not None:
        family |= {name for name, e in enemies.items()
                   if isinstance(e, dict) and e.get('displayName') == display and e.get('bestiary')}
    return tuple(family)


def in_zombiepedia(kind: str) -> bool:
    """Whether this enemy is one of the twelve the Zombiepedia lists, under its own name or a variant's.

    The cows, the cars, the jukebox, the slot machine, the diamond and the power-up container have no
    `bestiary` anywhere in their family: they are not zombies a player is told about, and two of them are
    not enemies at all.
    """
    enemies = _enemies()
    return any((enemies.get(name) or {}).get('bestiary') for name in _pedia_family(kind))


def unlocked_kinds() -> list:
    """Every enemy the generator may use: in the Zombiepedia, unlocked by the kills so far, able to walk,
    and with recordings to walk in with.  Sorted, so a roster is the same roster every time."""
    enemies = _enemies()
    out = []
    for kind, entry in enemies.items():
        if not isinstance(entry, dict) or not float(entry.get('speed') or 0):
            continue                                      # it stands where it spawns: Ted, Jim, Bob, a Car
        if not in_zombiepedia(kind) or not _has_sounds(kind):
            continue
        if required_kills(kind) == 0:
            out.append(kind)
    return sorted(out)


def display_name(kind) -> str:
    """The name the Zombiepedia calls this enemy, which is the only name a player has ever heard.

    Not simply its own `displayName`, because the original's data does not line those up: `Runner` is
    shown as "Snufflehog" and carries the bestiary, while `RunnerB` and `RunnerC` are shown as "Runner"
    and carry none - and the Zombiepedia only ever lists an entry that *has* a bestiary
    (`_bestiaryEntries`, `mapDisplayNameToName` 0x100078b94), so it shows Snufflehog and has never once
    said "Runner".  `Dodge` and `DodgeB` are the same trick under "Zombie Dog" and "Dodger".

    So the name is taken from whichever entry of the family carries the bestiary - the one a player has
    actually been shown - and only then from the enemy's own.  Taking its own first would offer a player
    two rows, "Runner" and "Snufflehog", for one zombie they know by one name.
    """
    enemies = _enemies()
    for other in _pedia_family(kind):
        entry = enemies.get(other) or {}
        if entry.get('bestiary') and entry.get('displayName'):
            return str(entry['displayName'])
    own = (enemies.get(str(kind)) or {}).get('displayName')
    if own:
        return str(own)
    base = (enemies.get(_base_kind(kind)) or {}).get('displayName')
    return str(base or kind)


def pedia_roster() -> list:
    """[(the Zombiepedia's name, (the kinds behind it, ...))] for every entry it has unlocked.

    One row per name a player has been shown, not one per internal kind: the Zombiepedia lists twelve
    zombies and the game has sixteen names for them, because `Zombie`, `ZombieB` and `ZombieC` are one
    zombie with three sets of recordings.  Offering those three separately would be three rows a player
    cannot tell apart; offering the name once and spending the variants behind it is what they are for.

    In the Zombiepedia's own order, which is by what it asks before it will show you the entry
    (`sort_zombie_names` 0x100079610) - so the ones a player met first come first.
    """
    enemies = _enemies()
    groups: dict = {}
    for kind in unlocked_kinds():
        groups.setdefault(display_name(kind), []).append(kind)

    def asked(name: str) -> int:
        for kind in groups[name]:
            for other in _pedia_family(kind):
                bestiary = (enemies.get(other) or {}).get('bestiary')
                if bestiary:
                    try:
                        return int(bestiary.get('Unlock requirement') or 0)
                    except (TypeError, ValueError):
                        return 0
        return 0
    return [(name, tuple(sorted(groups[name]))) for name in sorted(groups, key=lambda n: (asked(n), n))]


def variant_of(kinds, used: int) -> str:
    """Which of a zombie's recordings the next one placed should use.

    Taken in turn rather than at random, so three Zombies in a wave are `Zombie`, `ZombieB` and `ZombieC`
    and sound like three zombies instead of one zombie three times.  That is the whole reason the variants
    exist, and it is the generator's own habit (`_crowd` walks its kinds in turn).
    """
    order = tuple(kinds) or ('Zombie',)
    return order[used % len(order)]


def nothing_to_kill_in(challenge_id: str) -> bool:
    """Whether a custom challenge has no zombies in it anywhere, in any wave.

    A challenge like that is one somebody has made and not filled in yet - `starter_challenge` is one empty
    wave - and its row says so rather than offering a run that would be over before it started and would
    pay its coins for nothing.  An empty wave *inside* a challenge that does have zombies is fine: the game
    lets one by (`BrickManager.update`), so it is a pause between crowds.
    """
    load()
    if not is_custom(challenge_id):
        return False
    waves = waves_of(challenge_id)
    if not waves:
        return False                                      # no waves at all is a file `_read` already refused
    return not any(wave.get('Enemies') for wave in waves)


def locked_kinds_in(challenge_id: str) -> list:
    """The enemies of a custom challenge the Zombiepedia has not unlocked yet.

    `canUseBrickWithName:` 0x1000c259c refuses an Endless brick holding one of these, and a custom arena's
    row says so for the same reason: a file written by somebody who has played further than you have would
    otherwise be a wave that arrives and cannot be understood.  Asked as the row is drawn, since what is
    locked changes as the game is played.
    """
    load()
    locked = set()
    for brick in (PLISTS.get(challenge_id) or {}).get('bricks') or ():
        for slot in ((PLISTS.get(brick) or {}).get('Enemies') or {}):
            kind = str(slot).split(' ')[0]
            if required_kills(kind) >= 1:
                locked.add(display_name(kind))            # what a player would look up, not `DodgeB`
    return sorted(locked)


def _flag(where: dict, key: str, default: bool) -> bool:
    """A true or false a file may say, refusing anything that is neither rather than reading it as one."""
    value = where.get(key)
    if value is None:
        return default
    if not isinstance(value, bool):
        raise _Bad('its %s is not true or false' % key)
    return value


def _point(value, key: str) -> str:
    """A CGPoint the way `ADSound` reads one: `cg_point_from_string` wants the string "{x, y}"."""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise _Bad('its %s is not a pair of numbers' % key)
    for one in value:
        if isinstance(one, bool) or not isinstance(one, (int, float)):
            raise _Bad('its %s is not a pair of numbers' % key)
        if not -50.0 <= float(one) <= 50.0:
            raise _Bad('its %s is further out than the arena goes' % key)
    return '{%g, %g}' % (float(value[0]), float(value[1]))


def _cutscene(raw: dict, where: str = 'during') -> list:
    """One of a wave's three cutscenes, in the shape `ADSound.__init__` 0x1000b2d68 reads.

    `where` is which of them: `during` is the wave's own `cutscene`, the dialogue that runs while the crowd
    is being fought, and `before` and `after` are the scenes either side of it (`PLACE_KEYS`).

    Written short or long: `"cutscene": "my_line"` is one line that holds the wave and can be skipped,
    which is what a cutscene almost always is, and the long form reaches everything the original's own
    scripted sounds can do - when it starts, whether it holds the wave, where it is heard from, and
    whether it walks while it talks.
    """
    written = raw.get(_WRITTEN_AS[where])
    if written is None:
        return []
    if isinstance(written, (str, dict)):
        # One line, written either way round: the name on its own, or the block of settings for it.  A lone
        # block is the shape somebody reaches for when their one line needs a time or a place, and reading
        # it as anything else would be reading a mistake into what they plainly meant.
        written = [written]
    if not isinstance(written, list):
        raise _Bad('its %s is not a sound, or a list of them' % _WRITTEN_AS[where])
    if len(written) > MAX_CUTSCENE:
        raise _Bad('a cutscene may have at most %i lines in it' % MAX_CUTSCENE)
    have = audio_files()
    out = []
    for one in written:
        if isinstance(one, str):
            one = {'sound': one}
        if not isinstance(one, dict):
            raise _Bad('something in its %s is neither a sound nor a block of settings'
                       % _WRITTEN_AS[where])
        key = _text(one, 'sound', required=True)
        if key not in have:
            raise _Bad('it asks for a sound that is not in the %s folder: %s' % (AUDIO_DIR_NAME, key))
        line = {'name': key,
                'blocker': bool(one.get('blocker', True)),
                'skippable': bool(one.get('skippable', True)),
                'stopsOtherSounds': bool(one.get('stops_other_sounds', False)),
                'loop': bool(one.get('loop', False)),
                'gain': _number(one, 'gain', 0.0, 10.0, 0.0)}
        after = one.get('after')
        if isinstance(after, str):
            after = {'sound': after}
        if isinstance(after, dict):
            # `spawn_after` is the original's own key, and `afterStart` is what separates "when that one
            # begins" (`check_spawn_on_start` 0x1000a19fc) from "when it has finished"
            # (`check_spawn_after_kill` 0x1000a20ac).
            line['spawn_after'] = {'enemy': _text(after, 'sound', required=True),
                                   'time': _number(after, 'time', 0.0, MAX_SPAWN_TIME, 0.0),
                                   'afterStart': _text(after, 'when', default='ends') == 'starts'}
        elif after is not None:
            raise _Bad('its after is neither a sound nor a block of settings')
        else:
            line['spawn_time'] = _number(one, 'at', 0.0, MAX_SPAWN_TIME, 0.0)
        if one.get('angle') is not None or one.get('distance') is not None:
            line['spawn_angle'] = _number(one, 'angle', -3600.0, 3600.0, 0.0) % 360.0
            line['spawn_distance'] = _number(one, 'distance', 0.0, MAX_DISTANCE, 6.0)
        if one.get('from') is not None:
            line['position'] = _point(one.get('from'), 'from')
            if one.get('to') is not None:
                line['finalPosition'] = _point(one.get('to'), 'to')
        out.append(line)
    if where != 'during' and all(line.get('loop') for line in out):
        # A `before` or `after` cutscene is a wave with nothing else in it, so the wave is over when the
        # cutscene is: `soundOrEnemyWithNameWasDeactivated:` 0x1000c6bb0 is what asks whether it is, and a
        # line that loops never deactivates to ask.  A wave with *nothing* in it is let by instead
        # (`BrickManager.update`), but this one is not empty - it has a sound that never ends - so the
        # challenge really would stop here.
        raise _Bad('a cutscene that plays %s a wave is nothing but loops, and a loop never ends - the '
                   'challenge could not go on past it' % where)
    names = [line['name'] for line in out]
    for line in out:
        wanted = (line.get('spawn_after') or {}).get('enemy')
        if wanted is not None and wanted not in names:
            # One scene at a time: a line can only wait for another line it is played alongside, and the
            # three cutscenes of a wave are three separate waves by the time the game sees them.
            raise _Bad('one of its cutscene lines waits for %s, which is not in the same cutscene' % wanted)
    return out


def _powerup(raw: dict) -> dict:
    """The wave's `PowerUp` block, in the shape `Brick.update` 0x1000a0ed0 reads, or None for a wave without
    one.

    Written short or long: `"powerup": 8` is a drop of any kind eight seconds in, and the long form names
    which kind.  Always `force_spawn_time`, for the reason set out at `POWERUP_KINDS`: the waiting kind of
    drop cannot arrive in a challenge at all.
    """
    written = raw.get('powerup')
    if written is None:
        return None
    if isinstance(written, bool):                         # `true` says when nothing, and is a mistake
        raise _Bad('its powerup is not a time, or a block of settings')
    if isinstance(written, (int, float)):
        written = {'at': written}
    if not isinstance(written, dict):
        raise _Bad('its powerup is not a time, or a block of settings')
    kind = _text(written, 'kind', default='any').lower()
    if kind not in POWERUP_KINDS:
        raise _Bad('it asks for a power-up the game does not have: %s (it has %s)'
                   % (kind, ', '.join(POWERUP_KINDS)))
    if written.get('after') is not None:
        # `checkSpawnAfterKill` 0x1000a20ac reads a `spawn_after` here and answers it with
        # `tryToPopPowerUpContainer`, which is the waiting kind - so in a challenge it would never drop.
        raise _Bad('a power-up cannot wait for a zombie to die: that drop waits for the air-drop cooldown, '
                   'which only runs down in Endless. Give it a time instead')
    out = {'force_spawn_time': _number(written, 'at', 0.0, MAX_SPAWN_TIME, 0.0)}
    if kind != 'any':
        out['type'] = kind
    return out


def powerup_kind_of(wave: dict) -> str:
    """'none', or one of `POWERUP_KINDS`, for the wave's drop as the editor's row reads it."""
    pud = wave.get('PowerUp')
    if not isinstance(pud, dict):
        return 'none'
    named = str(pud.get('type') or '').lower()
    return named if named in POWERUP_KINDS else 'any'


def powerup_time_of(wave: dict) -> float:
    """When the wave's drop arrives, in seconds from the wave starting; 0 for a wave without one."""
    pud = wave.get('PowerUp')
    if not isinstance(pud, dict):
        return 0.0
    for key in ('force_spawn_time', 'spawn_time'):        # the second for a wave read from the game's own
        try:
            return float(pud.get(key))
        except (TypeError, ValueError):
            continue
    return 0.0


def set_powerup(wave: dict, kind: str, at: float) -> None:
    """The wave's drop, as the editor sets it.  'none' takes it out; anything else is a drop that always
    comes, which is the only kind a challenge can have."""
    if kind == 'none' or kind not in POWERUP_KINDS:
        wave.pop('PowerUp', None)
        return
    pud = {'force_spawn_time': max(0.0, min(MAX_SPAWN_TIME, float(at)))}
    if kind != 'any':
        pud['type'] = kind
    wave['PowerUp'] = pud


# ==================================================================================== reading the files
def _scene_brick(waves: dict, brick: str, wave: dict, where: str) -> list:
    """The cutscene-only brick for a wave's `before` or `after` scene, added to `waves`.

    Answers the brick's name in a list, so the caller can splice it into `bricks` whether there is one or
    not.  The brick is `{'Sounds': [...]}` and nothing else, which is what `tutorial_7_brick_4` is: no
    `Enemies` key at all, so `brickIsCleared` 0x1000a1658 has nothing to wait for but the lines themselves,
    and the scene ends when the last of its blockers does.
    """
    lines = cutscene_of(wave, where)
    if not lines:
        return []
    name = '%s_%s' % (brick, where)
    waves[name] = {'Sounds': lines}
    return [name]


def _wave(raw: dict, name: str) -> dict:
    """One wave object, as the brick dictionary `Brick.__init__` reads.

    The slots are numbered as they go in - `Enemies` is a dictionary and the kind is read back off the front
    of the key (`name.split(' ')[0]`) - so two of a kind need two keys, exactly as `additions._wave` does it.
    """
    enemies, passers = {}, {}
    # All three of a wave's cutscenes (PLACES): the one it talks over its crowd with, and the scenes either
    # side of it.  A wave of nothing but a cutscene is one of the original's own shapes: tutorial_7_brick_4,
    # the closing line of "Meet The Farty", has no enemies at all.  `brickIsCleared` 0x1000a1658 holds such
    # a wave on its `blocker` until the line has finished, which is what makes it a scene rather than a gap.
    scenes = {where: _cutscene(raw, where) for where in PLACES}
    # What has to be in the wave *itself*.  A `before` or `after` is a wave of its own by the time the game
    # plays it, so it does nothing to end the wave it is written on: an empty wave between two scenes has no
    # enemy to kill and no sound to finish, and `soundOrEnemyWithNameWasDeactivated:` 0x1000c6bb0 - the only
    # thing that ever asks whether a wave is over - is never called at all.  The challenge would stop there.
    # Two scenes running into each other is still easy to write: the lines go in one cutscene, or they go in
    # the `after` of one wave and the `before` of the next.
    # A wave may hold nothing at all (user request, 2026-09-30).  It used to be refused, because a wave with
    # neither enemies nor sounds is one nothing can ever end - `soundOrEnemyWithNameWasDeactivated:`
    # 0x1000c6bb0 is the only thing that asks whether a wave is over - and the challenge stopped there.  A
    # wave like that now finishes itself (`BrickManager.update`), so it is a wave waiting to be filled in
    # rather than a dead end, which is what a challenge somebody has just made is made of.
    spec = _entries(raw, 'enemies', MAX_ENEMIES)
    known = _enemies()
    for i, one in enumerate(spec):
        kind = _text(one, 'kind', required=True)
        if not isinstance(known.get(kind), dict):
            raise _Bad('it asks for an enemy the game does not have: %s' % kind)
        if not _has_sounds(kind):
            raise _Bad('it asks for an enemy with no sounds: %s' % kind)
        at = {'spawn_angle': _number(one, 'angle', -3600.0, 3600.0, 0.0) % 360.0,
              'spawn_distance': _number(one, 'distance', MIN_DISTANCE, MAX_DISTANCE, 10.0)}
        after = one.get('after')
        if isinstance(after, dict):
            at['spawn_after'] = {'enemy': _text(after, 'enemy', required=True),
                                 'time': _number(after, 'time', 0.0, MAX_SPAWN_TIME, 0.0)}
        else:
            at['spawn_time'] = _number(one, 'at', 0.0, MAX_SPAWN_TIME, 0.0)
        enemies[slot_name(kind, i)] = at
    for one in _entries(raw, 'passers', MAX_PASSERS):
        # `PasserBy` is keyed by the kind itself rather than by a numbered slot (`init_passers_by`
        # 0x10009f6b4), so a wave holds one of each: three cows, and the jukebox that cannot be killed.
        kind = _text(one, 'kind', required=True)
        if not isinstance(known.get(kind), dict):
            raise _Bad('it asks for a passer-by the game does not have: %s' % kind)
        passers[kind] = {'spawn_angle': _number(one, 'angle', -3600.0, 3600.0, 0.0) % 360.0,
                         'spawn_distance': _number(one, 'distance', MIN_DISTANCE, MAX_DISTANCE, 11.0),
                         'spawn_time': _number(one, 'at', 0.0, MAX_SPAWN_TIME, 0.0)}
    wave = {'Enemies': enemies}
    if raw.get('rigged'):
        wave['Rigged'] = True
    elif raw.get('no_blast', True):
        wave['NoBlast'] = True
    if passers:
        wave['PasserBy'] = passers
    powerup = _powerup(raw)
    if powerup:
        wave['PowerUp'] = powerup
    if not _flag(raw, 'zombie_themes', True):
        wave[ZOMBIE_THEMES] = True
    diamonds = int(_number(raw, 'diamonds', 0.0, float(MAX_DIAMONDS), 0.0))
    if diamonds:
        wave[WAVE_DIAMONDS] = diamonds
    for where in PLACES:
        set_cutscene(wave, where, scenes[where])
    log.debug('custom wave %s: %i enemies, %i passers-by, cutscene lines %s',
              name, len(enemies), len(passers),
              ', '.join('%i %s' % (len(scenes[w]), w) for w in PLACES))
    return wave


def _challenge(raw: dict, fallback_id: str, arena: str, source: str = '', index=None) -> tuple:
    """(challenge id, the challenge dictionary, {brick name: the wave}) for one challenge object.

    `source` is the file it came out of and `index` its place in a pack's `challenges` list (None for a
    `.adchallenge`, which is one challenge on its own).  Both are carried on the dictionary so the editor
    can write a change back to the file it was read from - see `save_challenge`.
    """
    from .modifiers import GameModifiers
    title = _text(raw, 'title', required=True)
    cid = PREFIX + _slug(raw.get('id') or title or fallback_id, _slug(fallback_id))
    weapons, guns = [], 0
    known = _weapons()
    for one in _entries(raw, 'weapons', 3, required=True):
        name = _text(one, 'name', required=True)
        if name not in known:
            raise _Bad('it asks for a weapon the game does not have: %s' % name)
        entry = {'name': name}
        if one.get('ammo') is not None:
            entry['ammo'] = str(int(_number(one, 'ammo', 1.0, 9999.0, 999.0)))
        if not known[name].get('melee'):
            guns += 1
        weapons.append(entry)
    if not guns:
        # `initWithChallengeWeaponArray:` 0x1000a80f4 ends on `weapons_array[0]`, which on a loadout of
        # nothing but a melee weapon is an empty list: the original would raise there, and so would we.
        raise _Bad('it hands out no gun, only a melee weapon')
    modifiers = []
    for flag in _names(raw, 'modifiers'):
        if not GameModifiers.shared().has_setter(flag):
            raise _Bad('it asks for a modifier the game does not have: %s' % flag)
        modifiers.append(flag)
    #: `bricks` is what the game plays, in order, and holds the cutscene-only bricks as well; `wave_bricks`
    #: is the waves proper, which is what the editor counts and walks (`waves_of`).
    # A file from the day this was a challenge-wide modifier: every wave is given the setting it meant and
    # the flag goes, so the two can never disagree about a wave (see `_OLD_THEME_FLAG`).
    was_challenge_wide = _OLD_THEME_FLAG in modifiers
    modifiers = [m for m in modifiers if m != _OLD_THEME_FLAG]
    waves, bricks, wave_bricks = {}, [], []
    for i, one in enumerate(_entries(raw, 'waves', MAX_WAVES, required=True)):
        brick = '%s_w%i' % (cid, i + 1)
        wave = _wave(one, brick)
        if was_challenge_wide:
            wave[ZOMBIE_THEMES] = True
        waves[brick] = wave
        wave_bricks.append(brick)
        bricks.extend(_scene_brick(waves, brick, wave, 'before'))
        bricks.append(brick)
        bricks.extend(_scene_brick(waves, brick, wave, 'after'))
    if not bricks:
        raise _Bad('it has no waves')
    difficulty = _text(raw, 'difficulty', default=DEFAULT_DIFFICULTY).lower()
    if difficulty not in MARGINS:
        raise _Bad('its difficulty is not one of %s' % ', '.join(DIFFICULTIES))
    accuracy = raw.get('accuracy') if isinstance(raw.get('accuracy'), dict) else {}
    time_limit = raw.get('time') if isinstance(raw.get('time'), dict) else {}
    d = {
        'challenge_id': cid,
        'title': title,
        'objective': _text(raw, 'objective', default='A challenge somebody made.'),
        'tip': _text(raw, 'tip'),
        'icon': 'Challenge_icon_02',
        'icon_title': _text(raw, 'icon_title', default='CU')[:2].upper(),
        'weapons': weapons,
        'bricks': bricks,
        #: PORT ADDITION: the waves proper, without the cutscene-only bricks `_scene_brick` puts between
        #: them.  A wave is what the editor adds, deletes and numbers, and "wave 3" has to mean the third
        #: crowd however many scenes are being played around it.
        'custom_waves': wave_bricks,
        'ambient': {'ambientPlaylist': _text(raw, 'ambient', default='ambient_roman'),
                    'gain': _number(raw, 'ambient_gain', 0.0, 4.0, 0.5)},
        'mission_star': {'reward': min(REWARD_CAP,
                                       int(_number(raw, 'coins', 0.0, 99999.0, DEFAULT_REWARD)))},
        'accuracy_star': {'objective': int(_number(accuracy, 'objective', 0.0, 100.0, 50.0)),
                          'reward': min(REWARD_CAP, int(_number(accuracy, 'reward', 0.0, 99999.0, 150.0)))},
        'time_limit_star': {'objective': int(_number(time_limit, 'objective', 1.0, 3600.0, 180.0)),
                            'reward': min(REWARD_CAP, int(_number(time_limit, 'reward', 0.0, 99999.0, 150.0)))},
        #: PORT ADDITION: which arena's list this row belongs to.  `arena_of` reads it rather than walking
        #: `ARENAS`, so a challenge dictionary that has been carried through a game still knows its way back.
        'custom_arena': arena,
        #: PORT ADDITION: where it came from and how hard it was asked to be, which is what the editor
        #: needs to write a change back into the file the player owns.  Three keys of ours on a dictionary
        #: the game otherwise reads by the original's own names; nothing else looks at them.
        'custom_source': source,
        'custom_index': index,
        'custom_difficulty': difficulty,
    }
    if modifiers:
        d['Modifiers'] = modifiers
    requires = [PREFIX + _slug(r) for r in _names(raw, 'requires', 8)]
    if requires:
        d['challenges_requirement'] = requires
    return cid, d, waves


def is_zipped(path: str) -> bool:
    """Whether this file is a zipped pack rather than a plain one.  Read from the file and not from its
    name, because both are called `.adpack`: the first two bytes of every zip are `PK`."""
    try:
        with open(path, 'rb') as fh:
            return fh.read(2) == b'PK'
    except OSError:
        return False


def _unpack(path: str) -> dict:
    """The document out of a zipped pack, with its recordings put into the audio folder.

    A sound whose name is already taken by a *different* recording is brought in under another name, and
    this pack's own lines are pointed at that name before anything reads them - so two packs that both call
    a line `intro` can both be installed and both still say the right thing.  A sound already there byte for
    byte is left alone, so reading the same pack twice copies nothing.
    """
    import hashlib
    import zipfile
    from ..platform.filedialog import AUDIO_EXTENSIONS
    try:
        with zipfile.ZipFile(path) as bundle:
            names = bundle.namelist()
            if PACK_DOCUMENT not in names:
                raise _Bad('it is a zip with no %s in it, so it is not a pack' % PACK_DOCUMENT)
            inside = bundle.getinfo(PACK_DOCUMENT)
            if inside.file_size > MAX_FILE_BYTES:
                raise _Bad('the pack inside it is too big to be a challenge')
            raw = json.loads(bundle.read(PACK_DOCUMENT).decode('utf-8'))
            renamed = {}
            already = None                                # {what a recording is: the name it is under}
            for member in names:
                if member == PACK_DOCUMENT or member.endswith('/'):
                    continue
                folder, _sep, filename = member.rpartition('/')
                stem, extension = os.path.splitext(filename)
                if folder != PACK_AUDIO_DIR or extension.lower() not in AUDIO_EXTENSIONS:
                    continue                              # nothing else in the zip is any of our business
                body = bundle.read(member)
                if already is None:
                    already = _recordings_by_content()
                mine = hashlib.sha256(body).hexdigest()
                # The folder is searched by what a recording *is* rather than by what it is called.  By
                # name alone, a pack that had to rename a line once renamed it again on every read: the
                # name it wanted was still taken by the other pack's, so `intro_2` became `intro_3` and
                # then `intro_4`, a copy of the same audio per launch for as long as both packs were there.
                here = already.get(mine)
                if here is not None:
                    if here != stem:
                        renamed[stem] = here
                    continue                              # this recording is already in, under `here`
                key = stem
                if key in audio_files():
                    n = 2
                    while '%s_%i' % (key, n) in audio_files():
                        n += 1
                    key = '%s_%i' % (key, n)
                    renamed[stem] = key
                with open(os.path.join(audio_dir(make=True), key + extension.lower()), 'wb') as fh:
                    fh.write(body)
                already[mine] = key
                log.info('%s brought in its own recording %s as %s', os.path.basename(path), stem, key)
    except _Bad:
        raise
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
        raise _Bad('it could not be opened: %s' % exc)
    except ValueError as exc:
        raise _Bad('the pack inside it is not valid JSON: %s' % exc)
    if renamed:
        _point_at(raw, renamed)
    return raw


def _recordings_by_content() -> dict:
    """{what each recording in the audio folder is, as a digest: the name it is under}.

    Read when a zipped pack actually has sounds in it and not before, since it reads every recording there
    to answer.  The folder is a handful of files; the alternative is a copy of the same audio for every
    launch, which is what asking by name alone did.
    """
    import hashlib
    found = {}
    for name, where in audio_files().items():
        try:
            with open(where, 'rb') as fh:
                found.setdefault(hashlib.sha256(fh.read()).hexdigest(), name)
        except OSError:
            continue
    return found


def _point_at(raw, renamed: dict) -> None:
    """Every cutscene line in `raw` that names a recording we had to rename, pointed at its new name.

    Walked rather than reached for: a line may be written short (`"cutscene": "my_line"`) or long, and may
    sit under any of the three places a cutscene can play, in a pack or in a single challenge.
    """
    if isinstance(raw, dict):
        for key in _WRITTEN_AS.values():
            written = raw.get(key)
            if isinstance(written, str) and written in renamed:
                raw[key] = renamed[written]
            elif isinstance(written, list):
                for i, one in enumerate(written):
                    if isinstance(one, str) and one in renamed:
                        written[i] = renamed[one]
                    elif isinstance(one, dict) and one.get('sound') in renamed:
                        one['sound'] = renamed[one['sound']]
        for value in raw.values():
            _point_at(value, renamed)
    elif isinstance(raw, list):
        for value in raw:
            _point_at(value, renamed)


def _read(path: str, as_pack=None) -> list:
    """[(arena, challenge id, dictionary, waves)] for one file, or a `_Bad` saying why not.

    `as_pack` says whether to read it as a pack rather than as one challenge; left out, the suffix decides,
    which is what the folder is read by.  `pack_up` sets it, because what it is about to check is a file
    with a name of its own that is not final yet.
    """
    zipped = is_zipped(path)
    try:
        if os.path.getsize(path) > (MAX_PACK_BYTES if zipped else MAX_FILE_BYTES):
            raise _Bad('it is too big to be a challenge')
    except OSError as exc:
        raise _Bad('it could not be opened: %s' % exc)
    if zipped:
        raw = _unpack(path)
    else:
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                raw = json.load(fh)
        except (OSError, UnicodeDecodeError) as exc:
            raise _Bad('it could not be opened: %s' % exc)
        except ValueError as exc:
            raise _Bad('it is not valid JSON: %s' % exc)
    if not isinstance(raw, dict):
        raise _Bad('it is not a block of settings')
    version = raw.get('version')
    if version is not None and (isinstance(version, bool) or not isinstance(version, int)
                                or version > FORMAT_VERSION):
        raise _Bad('it was written for a newer version of the game')
    stem = os.path.splitext(os.path.basename(path))[0]
    if path.lower().endswith(PACK_SUFFIX) if as_pack is None else as_pack:
        if _text(raw, 'format', default=FORMAT_PACK) != FORMAT_PACK:
            raise _Bad('it does not say it is a %s' % FORMAT_PACK)
        arena = _text(raw, 'arena', default=stem)
        out = []
        for i, one in enumerate(_entries(raw, 'challenges', MAX_CHALLENGES, required=True)):
            cid, d, waves = _challenge(one, '%s_%i' % (stem, i + 1), arena, path, i)
            out.append((arena, cid, d, waves))
        if not out:
            raise _Bad('it has no challenges in it')
        return out
    if _text(raw, 'format', default=FORMAT_CHALLENGE) != FORMAT_CHALLENGE:
        raise _Bad('it does not say it is a %s' % FORMAT_CHALLENGE)
    arena = _text(raw, 'arena', default=LOOSE_ARENA)
    cid, d, waves = _challenge(raw, stem, arena, path, None)
    return [(arena, cid, d, waves)]


def load(force: bool = False) -> None:
    """Read the challenges folder, once, and again whenever the maker has written something.

    The plist cache is cleared afterwards: `data._load` is an `lru_cache`, so a challenge generated while
    the game is running would otherwise be a name the cache had already answered `None` for.
    """
    global _LOADED
    if _LOADED and not force:
        return
    from . import data
    PLISTS.clear()
    ARENAS.clear()
    PROBLEMS.clear()
    _LOADED = True
    # The folder is *read* here and made only by the Challenge maker (`paths.custom_challenges_dir`), so a
    # player who never opens that screen never finds an empty folder beside their game.  Not being there is
    # not a fault: it is the ordinary state of a copy nobody has written a challenge for.
    folder = paths.CUSTOM_CHALLENGES
    try:
        files = sorted(f for f in os.listdir(folder)
                       if f.lower().endswith((CHALLENGE_SUFFIX, PACK_SUFFIX)))
    except OSError as exc:
        log.info('the challenges folder was not read: %s', exc)
        data._load.cache_clear()
        return
    if len(files) > MAX_FILES:
        PROBLEMS.append((folder, 'only the first %i files in it were read' % MAX_FILES))
        files = files[:MAX_FILES]
    order: list = []                                      # arena titles, in the order they first appear
    holds: dict = {}
    for name in files:
        try:
            found = _read(os.path.join(folder, name))
        except _Bad as exc:
            log.warning('the custom challenge file %s was skipped: %s', name, exc)
            PROBLEMS.append((name, str(exc)))
            continue
        except Exception:                                 # a file must never stop the game loading
            log.exception('the custom challenge file %s could not be read', name)
            PROBLEMS.append((name, 'it could not be read'))
            continue
        for arena, cid, d, waves in found:
            if cid in PLISTS:
                PROBLEMS.append((name, 'another file has already used the name %s' % cid))
                continue
            PLISTS[cid] = d
            PLISTS.update(waves)
            if arena not in holds:
                order.append(arena)
                holds[arena] = []
            holds[arena].append(cid)
    for arena in order:
        ARENAS.append((arena, tuple(holds[arena])))
    log.info('%i custom arena(s), %i challenge(s), %i file(s) skipped',
             len(ARENAS), sum(len(a) for _t, a in ARENAS), len(PROBLEMS))
    data._load.cache_clear()
    # A cutscene's playlist is built from what was here a moment ago and cached by the engine, so a folder
    # read again has to drop them.  Guarded: the folder is read long before there is an engine to tell.
    try:
        from ..s3d.engine import S3DEngine
        S3DEngine.engine().forget_custom_play_lists()
    except Exception:
        log.debug('no engine to tell about the custom playlists yet', exc_info=True)


def plist(name: str):
    """What `data._load` falls back to for a name the bundle and `additions.PLISTS` do not have."""
    load()
    return PLISTS.get(name)


def arenas() -> list:
    load()
    return list(ARENAS)


def problems() -> list:
    load()
    return list(PROBLEMS)


def is_custom(challenge_id) -> bool:
    return bool(challenge_id) and str(challenge_id).startswith(PREFIX)


def playlist_model(name: str):
    """The S3D playlist for a custom wave's cutscene, or None for a name that is not one.

    `Brick.init_sounds` 0x10009f274 asks the engine for a playlist named after the brick and builds an
    `ADSound` per `Sounds` entry inside its activation; `ADSound.init_sound` then looks the sound up in
    that playlist by name.  So a wave of ours needs a playlist of its own name holding its recordings,
    and this builds one - in memory, out of the audio folder, rather than out of a `.sexp` under
    `game/meta`, which is Somethin' Else's folder.

    `spatialized` is set for a line that says where it is heard from, because that decides how the buffer
    is loaded: a placed sound is mixed to mono (`acquire_buffer`), as the original's placed sounds are,
    and a line with no position stays stereo and is heard from everywhere at once, like narration.
    """
    from ..s3d import model as s3dmodel
    load()
    # An ambience a player imported (user request): one recording, played under the arena on a loop.
    # `startWithambient:gain:` 0x100098004 takes the playlist's bed with `any_sound_containing('ambient')`,
    # which is why `import_ambience` puts that word in the file's name; streamed, because an ambience is
    # minutes long and the original streams its own.
    if str(name).startswith(AMBIENCE_PREFIX):
        path = audio_files().get(name)
        if path is None:
            return None
        return s3dmodel.PlayListModel(
            xid=name, name=name, repeat=s3dmodel.REPEAT_NONE,
            sounds=[s3dmodel.SoundEntry(path=os.path.dirname(path), name=name,
                                        extension=os.path.splitext(path)[1].lstrip('.'),
                                        spatialized=False, preload=False, unloadonstop=False,
                                        stream=True)])
    wave = PLISTS.get(name)
    if not isinstance(wave, dict):
        return None
    entries = wave.get('Sounds') or []
    if not entries:
        return None
    have = audio_files()
    sounds = []
    for line in entries:
        path = have.get(line.get('name'))
        if path is None:                                  # deleted since the folder was read
            log.info('the cutscene sound %s is no longer in the audio folder', line.get('name'))
            continue
        placed = any(line.get(k) is not None for k in ('position', 'spawn_angle', 'spawn_distance'))
        sounds.append(s3dmodel.SoundEntry(
            path=os.path.dirname(path), name=line['name'],
            extension=os.path.splitext(path)[1].lstrip('.'),
            spatialized=placed, preload=True, unloadonstop=False, stream=False))
    if not sounds:
        return None
    return s3dmodel.PlayListModel(xid=name, name=name, repeat=s3dmodel.REPEAT_NONE, sounds=sounds)


def arena_of(challenge_id):
    """The arena a custom challenge belongs to, or None for anything that is not one.

    Read off the challenge's own dictionary rather than by walking `ARENAS`, so that a wave's name - which
    is in `PLISTS` too and belongs to no arena - answers None rather than matching nothing slowly.
    """
    if not is_custom(challenge_id):
        return None
    load()
    return (PLISTS.get(challenge_id) or {}).get('custom_arena')


def arena_challenges(arena) -> tuple:
    load()
    for title, ids in ARENAS:
        if title == arena:
            return ids
    return ()


def challenge_after(challenge_id):
    """The challenge after this one in its arena - what Next challenge opens - or None for the last of one,
    and for anything that is not a custom challenge."""
    ids = arena_challenges(arena_of(challenge_id))
    if challenge_id in ids and ids.index(challenge_id) + 1 < len(ids):
        return ids[ids.index(challenge_id) + 1]
    return None


# ========================================================================================== the generator
#: `-[ADEnemy update:]`: the walk ends three units out and the attack lands at 0.3.
AGGRESSIVE_AT = 3.0
ATTACK_AT = 0.3

#: What an arrival sound is taken to last.  `spawn` 0x10005fbc0 holds an enemy still until its recording has
#: finished, and the recordings run from 1.3 seconds for a Zombie to 5.7 for a Hulk.  The shortest of them
#: is the one taken here - a player cannot count on the longer one - and reading each file to find out is
#: what `tools/arena_pressure.py` does with a decoder this package does not carry.  One second is the
#: pessimistic end, which for a generator is the right end to be wrong at.
SPAWN_SOUND = 1.0

#: PORT JUDGEMENT: seconds a player spends finding and facing something by ear before firing at it - the
#: `--overhead` of `tools/arena_pressure.py`, whose default this is.
OVERHEAD = 0.8

#: How much slack the tightest moment of a generated wave is asked to leave, by how hard the challenge
#: rolled.  For scale, the port's own chapter 1 runs from 15.7 seconds down to 2.2 and chapter 2 begins 1.4
#: seconds short, so these are a chapter 1 that goes as far as the start of chapter 2.
MARGINS = {'quiet': 9.0, 'busy': 5.0, 'desperate': 2.0}

#: The same three in the order the editor steps them, easiest first, and what a file that does not say
#: gets.  A hand-written challenge has no difficulty of its own until somebody rerolls its waves, and the
#: middle one is the honest answer to "how hard was this meant to be" when nobody said.
DIFFICULTIES = ('quiet', 'busy', 'desperate')
DEFAULT_DIFFICULTY = 'busy'

#: Bearings for a generated crowd.  A turn of about 137.5 degrees between arrivals is the one that never
#: settles into a pattern however many there are, so no two in a row come from anywhere near each other and
#: nothing repeats until the wave is over.  The arrangement is written into the file and played from there,
#: so a challenge is the same challenge every time: a star won against one arrangement has to mean the same
#: as a star won against the next.
GOLDEN_TURN = 137.507764

#: What the **generator** may hand out, when the player owns it.  The crowd weapons are left out: a shotgun
#: or a bazooka is priced pack by pack rather than enemy by enemy (`area_pressure`), and the sizing below
#: counts one thing at a time, so a wave sized for a bazooka would be a wave with nothing to do in it.
#:
#: Only the generator's.  The editor offers every gun the player has bought (`ChallengeEditorScreen._guns`):
#: not being able to size a crowd for a shotgun says nothing about whether a challenge may hand one out, and
#: using this list there hid half the armory from somebody placing their own zombies (user request,
#: 2026-09-30).
GENERATOR_GUNS = ('pistol', 'microsmg', 'hunting', 'tactical', 'machinegun')
GENERATOR_MELEE = ('wok', 'banjo', 'golf', 'prod', 'claymore')

#: The two halves of a generated name.  Content rather than anything a screen says: it is written into the
#: player's own file, where they can change it, and it is read back out of that file afterwards - so it is
#: not offered to a translator, for the same reason the name of a saved game is not.
_FIRST = ('Dead', 'Cold', 'Last', 'Broken', 'Quiet', 'Long', 'Iron', 'Bitter', 'Hollow', 'Restless',
          'Narrow', 'Bad', 'Empty', 'Slow', 'Open', 'Crooked', 'Low', 'Far', 'Idle', 'Wrong')
_SECOND = ('Air', 'Ground', 'Shift', 'Hour', 'Light', 'Mile', 'Call', 'Season', 'Company', 'Morning',
           'Street', 'Weather', 'Quarter', 'Business', 'Country', 'Mile', 'Watch', 'Round', 'Yard', 'Turn')
_ARENA_FIRST = ('The Yard', 'The Lot', 'The Back Road', 'The Siding', 'The Long Field', 'The Stockade',
                'The Outer Fence', 'The Dry Creek', 'The Old Works', 'The Far Gate')

AMBIENTS = ('ambient_roman', 'ambient_city', 'ambient_arena', 'ambient_ruins', 'ambient_warehouse',
            'ambient_factory', 'ambient_ghosttown', 'ambient_cave', 'ambient_outside', 'ambient_beach')


def _circling(entry: dict) -> float:
    circling = entry.get('circling')
    if not isinstance(circling, dict):
        return 0.0
    try:
        return float(circling.get('circlingFactor') or 0)
    except (TypeError, ValueError):
        return 0.0


#: kind -> (life, speed, charging speed, how much of the speed closes the distance).  Kept because sizing a
#: wave asks for them tens of thousands of times and `enemies.plist` does not change while the game runs.
_STATS: dict = {}


def _stats(kind: str) -> tuple:
    if kind not in _STATS:
        entry = _enemies().get(kind) or {}
        speed = float(entry.get('speed') or 0)
        _STATS[kind] = (float(entry.get('life') or 1), speed,
                        float(entry.get('agressiveSpeed') or speed or 1.0),
                        max(0.05, 1.0 - _circling(entry)))
    return _STATS[kind]


def deadline(kind: str, distance: float, at: float) -> float:
    """Seconds from the wave starting until this enemy reaches the player, which is the end of the game.

    `-[ADEnemy update:]` walks it in at `speed` until it is three units away, then closes at
    `agressiveSpeed` until `attack_distance` (0.3).  An enemy with a `circling` dict does not walk straight
    at the player: state 2 heads along `(1 - circlingFactor)` towards and `circlingFactor` sideways, so only
    that fraction of its speed closes the distance - a Clown at 0.9 covers two tenths of a unit a second out
    of two.  The charge has no circling in it and comes straight in.
    """
    _life, speed, aggressive, turning = _stats(kind)
    if not speed:
        return float('inf')                               # it never comes to you
    walk = max(0.0, distance - AGGRESSIVE_AT) / (speed * turning)
    close = (min(distance, AGGRESSIVE_AT) - ATTACK_AT) / aggressive
    return at + SPAWN_SOUND + walk + close


def sustained_damage(weapon: str) -> float:
    """Damage a second with the reloads in it, which is what a wave is actually fought with (level 1).

    Level 1 whatever the player has spent diamonds on: a generated challenge should be winnable with the
    gun as it comes out of the armory, and an upgraded one is then a wave with room in it rather than a
    wave that has become possible.
    """
    entry = _weapons().get(weapon) or {}
    level = entry.get('level_1') or {}
    damage = float(level.get('damages') or 0)
    rate = float(level.get('fireRate') or 1) or 1.0
    if entry.get('melee'):
        return damage / rate
    capacity = float(level.get('capacity') or 1) or 1.0
    reload_time = float(level.get('reloadTime') or 0)
    return (capacity * damage) / (capacity * rate + reload_time)


def wave_margin(wave: dict, damage_per_second: float) -> float:
    """The slack at the tightest moment of a wave: seconds to spare, or negative for a wave nothing can win.

    Every enemy has to be dead before it arrives, and the best a player can do is take them in the order
    their clocks run out - so this walks that order and asks how far the gun keeps up.  Deliberately
    generous, as `tools/arena_pressure.py` is: every shot hits the thing with the nearest deadline, and
    `OVERHEAD` is the whole allowance for finding it by ear.  Nothing here reads `spawn_after` or a rigged
    ring, because the generator writes neither.
    """
    rows = []
    for slot, place in (wave.get('Enemies') or {}).items():
        kind = str(slot).split(' ')[0]
        rows.append((deadline(kind, float(place['spawn_distance']), float(place.get('spawn_time') or 0)),
                     _stats(kind)[0]))
    rows.sort()
    spent, margin = 0.0, float('inf')
    for due, life in rows:
        spent += life / damage_per_second + OVERHEAD
        margin = min(margin, due - spent)
    return margin


def _crowd(kinds, count: int, distance: float, every: float, turn_from: float) -> dict:
    """A crowd walking in one at a time from bearings all round - the shape everything generated takes."""
    enemies = {}
    for i in range(count):
        enemies['%s %i' % (kinds[i % len(kinds)], i + 1)] = {
            'spawn_angle': round((turn_from + i * GOLDEN_TURN) % 360.0, 2),
            'spawn_distance': distance,
            'spawn_time': round(i * every, 2)}
    return {'Enemies': enemies, 'NoBlast': True}


def _size_wave(kinds, count: int, distance: float, turn_from: float, damage_per_second: float,
               target: float) -> dict:
    """The same crowd, made winnable: spread out, then stood further off, then made smaller.

    Three levers, in the order that costs a player the least.  **Spacing** first - `every`, the gap between
    arrivals, is the whole of whether a wave is hard, because nothing here has any health to lose: a crowd
    arriving more slowly than it can be shot never gets harder however large it is.  Then **distance**,
    which buys the same time without thinning the crowd.  Only then the **count**, which is the one that
    changes what the wave is.

    It has to be able to give up.  A Colossus has 500 life and the Micro SMG does thirteen and a half a
    second with its reloads in: eight of them is thirty seconds of shooting each and no spacing in the
    world makes that a wave.  When nothing reaches the target the widest arrangement tried is the one
    returned, so a roll that asked for too much is a hard challenge rather than an impossible one.
    """
    far_options = [distance, min(MAX_DISTANCE, distance + 4.0), min(MAX_DISTANCE, distance + 8.0)]
    best_wave, best_margin = None, float('-inf')
    for n in range(count, 0, -1):
        for far in far_options:
            every = 0.6
            while every <= 12.0:
                wave = _crowd(kinds, n, far, every, turn_from)
                margin = wave_margin(wave, damage_per_second)
                if margin > best_margin:
                    best_wave, best_margin = wave, margin
                if margin >= target:
                    return wave
                every = round(every + 0.2, 2)
    return best_wave


def _loadout(rng) -> list:
    """One or two guns and a melee weapon, out of what the player has actually bought.

    A challenge naming a gun the player does not own is one its own row sends to the armory
    (`challenge_chosen`), which for something the game generated for them would be a dead end.
    """
    from .inventory import Inventory
    inventory = Inventory.shared()
    guns = [w for w in GENERATOR_GUNS if inventory.has_unlocked_weapon(w)]
    melee = [w for w in GENERATOR_MELEE if inventory.has_unlocked_weapon(w)]
    if not guns:
        guns = ['pistol']                                 # free, and owned from the first launch
    if not melee:
        melee = ['wok']
    rng.shuffle(guns)
    chosen = guns[:1] if len(guns) == 1 or rng.random() < 0.5 else guns[:2]
    return chosen + [rng.choice(melee)]


def _ammo_for(waves, weapon: str, share: float) -> int:
    """Rounds enough to clear what this gun is given, and not many more.

    Counted honestly - a round does its damage, an enemy takes as many as its life asks for - and then half
    again, so a player has room to miss and the accuracy star still means something.  `share` is what this
    gun is expected to do of the work when the challenge hands out two.
    """
    level = (_weapons().get(weapon) or {}).get('level_1') or {}
    damage = float(level.get('damages') or 1) or 1.0
    rounds = 0
    for wave in waves:
        for slot in (wave.get('Enemies') or {}):
            rounds += math.ceil(_stats(str(slot).split(' ')[0])[0] / damage)
    return int(min(999, max(6, math.ceil(rounds * share * 1.5))))


def build_waves(difficulty: str, wave_count: int, damage_per_second: float, rng=None) -> list:
    """The waves of a challenge: crowds of whatever the Zombiepedia has unlocked, each sized so it can be
    won with `damage_per_second` and no more.

    Apart from `build_challenge` this is what the editor's Reroll asks for, which is why it takes the
    difficulty and the count rather than rolling them: there, they are the player's to choose.
    """
    rng = rng or random.Random()
    roster = unlocked_kinds() or ['Zombie']
    target = MARGINS.get(difficulty, MARGINS[DEFAULT_DIFFICULTY])
    waves = []
    for i in range(max(1, min(MAX_WAVES, wave_count))):
        kinds = rng.sample(roster, min(len(roster), rng.randint(1, 4)))
        # A random number of enemies, growing wave by wave: the last one is the one a player remembers.
        count = min(MAX_ENEMIES, rng.randint(3 + 2 * i, 6 + 3 * i))
        distance = round(rng.uniform(9.0, 12.0), 1)
        waves.append(_size_wave(kinds, count, distance, rng.uniform(0.0, 360.0), damage_per_second, target))
    return waves


def build_challenge(rng=None) -> dict:
    """One random challenge, as a `.adchallenge` object ready to be written out.

    The enemies are whatever the Zombiepedia has unlocked, so a fresh profile is given Rejects, Zombies,
    Farties, Hulks, Snufflehogs, Chainsaws and Clowns, and a Whisperer joins them at 150 kills, a Berserk at
    250, a Riot Gear Zombie at 350, a Zombie Dog at 400 and a Colossus at 450 - the same twelve, and in the
    same order, as the Zombiepedia opens them.
    """
    rng = rng or random.Random()
    loadout = _loadout(rng)
    best = max(sustained_damage(w) for w in loadout if not (_weapons().get(w) or {}).get('melee'))
    mood = rng.choice(DIFFICULTIES)
    wave_count = rng.randint(3, 5)
    waves = build_waves(mood, wave_count, best, rng)
    # Counted off the waves rather than off what was asked for: `_size_wave` may have made one smaller to
    # make it winnable, and the sentence below says how many are out there.
    enemy_total = sum(len(wave.get('Enemies') or {}) for wave in waves)
    guns = [w for w in loadout if not (_weapons().get(w) or {}).get('melee')]
    share = 1.0 if len(guns) == 1 else 0.7
    weapons = [{'name': w, 'ammo': _ammo_for(waves, w, share)} for w in guns]
    weapons += [{'name': w} for w in loadout if w not in guns]
    clear = sum(_clear_time(wave, best) for wave in waves)
    title = '%s %s' % (rng.choice(_FIRST), rng.choice(_SECOND))
    return {
        'format': FORMAT_CHALLENGE,
        'version': FORMAT_VERSION,
        'id': _slug(title) + '_' + ('%04x' % rng.randrange(1 << 16)),
        'title': title,
        'objective': _OBJECTIVES[mood] % enemy_total,
        'tip': _TIPS[mood],
        'ambient': rng.choice(AMBIENTS),
        'ambient_gain': 0.5,
        'difficulty': mood,
        'weapons': weapons,
        'coins': DEFAULT_REWARD,
        'accuracy': {'objective': rng.choice((35, 40, 45, 50, 55)), 'reward': 150},
        # Half again on what the guns alone need, so the time star is worth going for and is not given away.
        'time': {'objective': int(max(30, round(clear * 1.5 / 10.0) * 10)), 'reward': 150},
        'waves': [_wave_object(wave) for wave in waves],
    }


#: What a generated challenge's overview says.  One `%i` - how many are out there - so a translator writes
#: the sentence round the number in their own order (`%1$i`) and with their own word forms.
_OBJECTIVES = {
    'quiet': 'There are %i of them out there, and time enough to hear each one arrive.',
    'busy': 'They keep arriving. %i of them, and the next is walking while you deal with this one.',
    'desperate': 'There is no room in this one: %i of them, and barely a moment between them.',
}
#: What an unfilled challenge says instead.  A generated objective counts the zombies, and "0 of them, and
#: the next is walking while you deal with this one" is not a sentence to hand anybody.  Recognised by
#: `generated_objective` like the three above, so filling the challenge in and rerolling replaces it.
_EMPTY_OBJECTIVE = 'Nothing in this one yet. Put some zombies in it and say what it asks of you.'

_TIPS = {
    'quiet': 'Take them as they arrive rather than as you hear them. The loudest is rarely the nearest.',
    'busy': 'Reload in the gaps, not when you run out. The gaps are what this challenge is made of.',
    'desperate': 'Whichever one is closest, whatever it is. Nothing here waits for you to finish.',
}


def _clear_time(wave: dict, damage_per_second: float) -> float:
    """How long the guns alone need to clear a wave, which is what the time star is set from."""
    total = 0.0
    for slot in (wave.get('Enemies') or {}):
        total += _stats(str(slot).split(' ')[0])[0] / damage_per_second + OVERHEAD
    last = max((float(p.get('spawn_time') or 0) for p in (wave.get('Enemies') or {}).values()), default=0.0)
    return max(total, last)


def _wave_object(wave: dict) -> dict:
    """A built wave back in the file's own shape, so what is written is what `_read` reads."""
    enemies = []
    for slot, place in (wave.get('Enemies') or {}).items():
        enemies.append({'kind': str(slot).split(' ')[0], 'angle': place['spawn_angle'],
                        'distance': place['spawn_distance'], 'at': place.get('spawn_time', 0.0)})
    return {'no_blast': True, 'enemies': enemies}


def build_pack(count: int = 0, rng=None) -> dict:
    """An arena and the challenges in it, as a `.adpack` object ready to be written out."""
    rng = rng or random.Random()
    count = count or rng.randint(3, 5)
    arena = '%s %s' % (rng.choice(_ARENA_FIRST), rng.choice(('Arena', 'Grounds', 'Run', 'Stretch')))
    challenges = []
    for _i in range(min(MAX_CHALLENGES, count)):
        one = build_challenge(rng)
        one.pop('format', None)
        one.pop('version', None)
        challenges.append(one)
    return {'format': FORMAT_PACK, 'version': FORMAT_VERSION, 'arena': arena, 'challenges': challenges}


# --------------------------------------------------------------------------------------- writing it out
def _document_of(path: str) -> dict:
    """The pack or challenge document in a file, zipped or not, without touching its recordings.

    Not `_unpack`: that installs the sounds and may rename them, which is right when the folder is being
    read and wrong when a file is about to be written back.
    """
    import zipfile
    if not is_zipped(path):
        with open(path, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    with zipfile.ZipFile(path) as bundle:
        return json.loads(bundle.read(PACK_DOCUMENT).decode('utf-8'))


def _rewrite_zip(path: str, document: dict, adding=None) -> None:
    """A zipped pack with its document replaced and its recordings carried across.

    Written beside itself and moved into place, so a save that is interrupted leaves the pack it had rather
    than half of a new one - the whole arena is in this file and there is no second copy of it.  `adding` is
    {the name a cutscene calls it by: the file on disk} for recordings to put in at the same time.
    """
    import zipfile
    temp = path + '.writing'
    try:
        with zipfile.ZipFile(path) as old:
            keep = [m for m in old.infolist() if m.filename != PACK_DOCUMENT]
            with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as new:
                new.writestr(PACK_DOCUMENT, json.dumps(document, indent=2, ensure_ascii=False) + '\n')
                for member in keep:
                    new.writestr(member, old.read(member.filename))
                for name, where in (adding or {}).items():
                    inside = '%s/%s%s' % (PACK_AUDIO_DIR, name, os.path.splitext(where)[1].lower())
                    if inside not in [m.filename for m in keep]:
                        new.write(where, inside)
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.remove(temp)


def add_to_pack(challenge_id, name: str) -> bool:
    """Put a recording into the zipped pack a challenge lives in, so the pack still carries everything.

    Answers whether it went anywhere - False for a challenge in a plain file, which keeps its recordings in
    the audio folder beside it and has nothing to carry them in.
    """
    path, _index = source_of(challenge_id)
    if not path or not os.path.isfile(path) or not is_zipped(path):
        return False
    where = audio_files().get(name)
    if where is None:
        return False
    _rewrite_zip(path, _document_of(path), adding={name: where})
    log.info('%s now carries the recording %s', os.path.basename(path), name)
    return True


def sounds_named_by(raw) -> list:
    """Every recording the cutscenes in a document ask for, once each, in the order they turn up."""
    found: list = []

    def walk(value):
        if isinstance(value, dict):
            # An ambience a player imported is a recording in the same folder, named on the challenge
            # rather than in a cutscene, and an arena handed over without it is an arena that sounds wrong.
            # The ten the game ships are named here too and are dropped by the caller, which keeps only
            # what the audio folder actually holds.
            if isinstance(value.get('ambient'), str) and value['ambient'] not in found:
                found.append(value['ambient'])
            for key in _WRITTEN_AS.values():
                written = value.get(key)
                if isinstance(written, str):
                    written = [written]
                for one in written if isinstance(written, list) else ():
                    name = one if isinstance(one, str) else (one or {}).get('sound')
                    if isinstance(name, str) and name not in found:
                        found.append(name)
            for inner in value.values():
                walk(inner)
        elif isinstance(value, list):
            for inner in value:
                walk(inner)

    walk(raw)
    return found


def pack_files(arena: str) -> list:
    """The files an arena is made of, each once, in the order its challenges are listed."""
    load()
    out = []
    for cid in arena_challenges(arena):
        path, _index = source_of(cid)
        if path and os.path.isfile(path) and path not in out:
            out.append(path)
    return out


def is_one_file(arena: str) -> bool:
    """Whether this arena is already a single zipped pack carrying its own recordings."""
    files = pack_files(arena)
    return len(files) == 1 and is_zipped(files[0])


def pack_up(arena: str) -> tuple:
    """PORT ADDITION (user request, 2026-10-01): make an arena *be* one `.adpack`, recordings and all.

    Answers (the path it is now, how many recordings it carries, the names it could not find, how many
    files it replaced).  A pack with dialogue in it was a file *and* a folder of recordings to send
    alongside, and somebody handed only the file heard nothing.

    The arena is **converted**, not copied: the zip takes the place of the files it was made from.  A copy
    left beside its source is the same arena twice, and `load` refuses the second one challenge by
    challenge - "another file has already used the name" six times over, which is what trying it did
    (2026-10-01).  One arena, one file.

    Written from the files the arena is already made of rather than from `PLISTS`, for the reason
    `save_challenge` patches rather than rebuilds: what a later version adds, or the order somebody put
    their keys in, is theirs and survives being shared.
    """
    import zipfile
    load()
    was = pack_files(arena)
    challenges = []
    for cid in arena_challenges(arena):
        path, index = source_of(cid)
        if not path or not os.path.isfile(path):
            continue
        document = _document_of(path)
        if index is None:
            one = dict(document)
            one.pop('format', None)
            one.pop('version', None)
            one.pop('arena', None)
            challenges.append(one)
        else:
            holds = document.get('challenges') or []
            if index < len(holds):
                challenges.append(holds[index])
    if not challenges:
        raise _Bad('there is nothing in that arena to pack up')
    document = {'format': FORMAT_PACK, 'version': FORMAT_VERSION, 'arena': arena,
                'challenges': challenges}
    have = audio_files()
    # Everything the arena names, less the names that are the game's own playlists rather than recordings:
    # `sounds_named_by` collects each challenge's ambience too, and ten of those ship with the game.
    wanted = [name for name in sounds_named_by(document) if name in have]
    missing = [name for name in sounds_named_by(document)
               if name not in have and name not in AMBIENTS]
    folder = paths.custom_challenges_dir()
    out = os.path.join(folder, _slug(arena, 'arena') + PACK_SUFFIX)
    temp = out + '.writing'
    try:
        with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr(PACK_DOCUMENT, json.dumps(document, indent=2, ensure_ascii=False) + '\n')
            for name in wanted:
                bundle.write(have[name], '%s/%s' % (PACK_AUDIO_DIR, os.path.basename(have[name])))
        # Read before anything is taken away: a conversion that cannot be read back is a conversion that
        # does not happen, and the arena stays as it was.  As a pack, said rather than left to the name:
        # the file it is being checked under is not the name it will have.
        _read(temp, as_pack=True)
        for old in was:
            if os.path.abspath(old) != os.path.abspath(out):
                os.remove(old)
        os.replace(temp, out)
    finally:
        if os.path.exists(temp):
            os.remove(temp)
    load(force=True)
    log.info('%s is now one file, %s, carrying %i recording(s)', arena, out, len(wanted))
    return out, len(wanted), missing, len(was)


def write(document: dict, suffix: str) -> str:
    """Write a generated document into the challenges folder and return the path it went to.

    A name already taken is never overwritten: a player who has edited what was generated last time keeps
    what they edited.
    """
    folder = paths.custom_challenges_dir()
    # A challenge is named after itself and a pack after its arena: a pack has no title of its own, and a
    # challenge that names an arena it is joining would otherwise take that arena's name for its file.
    stem = _slug(document.get('title') or document.get('arena') or 'challenge')
    path = os.path.join(folder, stem + suffix)
    n = 2
    while os.path.exists(path):
        path = os.path.join(folder, '%s_%i%s' % (stem, n, suffix))
        n += 1
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(document, fh, indent=2, ensure_ascii=False)
        fh.write('\n')
    log.info('wrote a generated challenge to %s', path)
    return path


# ------------------------------------------------------------------------------------------- editing
def source_of(challenge_id) -> tuple:
    """(the file it came from, its place in that file's `challenges` list) - the index being None for a
    `.adchallenge`, which holds one challenge and nothing else."""
    d = PLISTS.get(challenge_id) or {}
    return d.get('custom_source') or '', d.get('custom_index')


def objective_for(difficulty: str, enemies: int) -> str:
    return _OBJECTIVES.get(difficulty, _OBJECTIVES[DEFAULT_DIFFICULTY]) % enemies


def tip_for(difficulty: str) -> str:
    return _TIPS.get(difficulty, _TIPS[DEFAULT_DIFFICULTY])


def generated_objective(text: str):
    """The difficulty whose objective this is, or None for a sentence somebody wrote themselves.

    The editor offers the three the generator writes and keeps anything else as a choice of its own, so
    editing a hand-written challenge never quietly throws its own words away.
    """
    if text == _EMPTY_OBJECTIVE:
        return DEFAULT_DIFFICULTY
    for mood, template in _OBJECTIVES.items():
        head, _sep, tail = template.partition('%i')
        if text.startswith(head) and text.endswith(tail) and len(text) >= len(head) + len(tail):
            return mood
    return None


def generated_tip(text: str):
    for mood, written in _TIPS.items():
        if text == written:
            return mood
    return None


def save_challenge(challenge_id, changes: dict, waves=None) -> str:
    """Write a change back into the file the challenge was read from, and read the folder again.

    The file is **patched, not rebuilt**: it is read as JSON, the keys that changed are set on the
    challenge object in it, and it is written out again.  Anything the port would not have thought to
    round-trip - a key a later version adds, the order somebody put their keys in, a wave shape the
    generator never writes - survives being edited, which a rebuild from `PLISTS` could not promise.  A
    pack's other challenges are not touched at all.

    Returns the path written.  Raises `_Bad` when there is nothing to write to.
    """
    path, index = source_of(challenge_id)
    if not path or not os.path.isfile(path):
        raise _Bad('the file it came from is no longer there')
    document = _document_of(path)
    if index is None:
        one = document
    else:
        holds = document.get('challenges')
        if not isinstance(holds, list) or index >= len(holds) or not isinstance(holds[index], dict):
            raise _Bad('the file it came from has changed underneath it')
        one = holds[index]
    one.update(changes)
    if waves is not None:
        one['waves'] = [_wave_to_object(wave) for wave in waves]
        # Every wave now says for itself whether it plays its zombies' music, so the challenge-wide flag
        # this used to be goes with the same write.  Left in, `_challenge` would read it back onto every
        # wave and a wave turned back on would turn itself off again the moment it was read.
        if isinstance(one.get('modifiers'), list) and _OLD_THEME_FLAG in one['modifiers']:
            one['modifiers'] = [m for m in one['modifiers'] if m != _OLD_THEME_FLAG]
            log.info('%s: the old challenge-wide theme flag is now on its waves', challenge_id)
    if is_zipped(path):
        _rewrite_zip(path, document)
    else:
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(document, fh, indent=2, ensure_ascii=False)
            fh.write('\n')
    log.info('wrote an edit of %s back to %s', challenge_id, path)
    load(force=True)
    return path


def _wave_to_object(wave: dict) -> dict:
    """A wave in the brick shape back in the file's own shape, whatever is in it.

    `_wave_object` is the generator's own narrow version - it only ever writes plain crowds.  This one is
    the general inverse of `_wave`, so a hand-written wave that is rerolled keeps nothing it should not and
    a wave that is *not* rerolled is never passed through here at all.
    """
    out: dict = {'enemies': []}
    if wave.get('Rigged'):
        out['rigged'] = True
    out['no_blast'] = bool(wave.get('NoBlast'))
    for slot, place in (wave.get('Enemies') or {}).items():
        one = {'kind': str(slot).split(' ')[0], 'angle': place.get('spawn_angle', 0.0),
               'distance': place.get('spawn_distance', 10.0)}
        after = place.get('spawn_after')
        if isinstance(after, dict):
            one['after'] = {'enemy': after.get('enemy'), 'time': after.get('time', 0)}
        else:
            one['at'] = place.get('spawn_time', 0.0)
        out['enemies'].append(one)
    passers = wave.get('PasserBy') or {}
    if passers:
        out['passers'] = [{'kind': kind, 'angle': p.get('spawn_angle', 0.0),
                           'distance': p.get('spawn_distance', 11.0), 'at': p.get('spawn_time', 0.0)}
                          for kind, p in passers.items()]
    for where in PLACES:
        lines = cutscene_of(wave, where)
        if lines:
            out[_WRITTEN_AS[where]] = [_cutscene_to_object(line) for line in lines]
    kind = powerup_kind_of(wave)
    if kind != 'none':
        out['powerup'] = {'at': powerup_time_of(wave)}
        if kind != 'any':
            out['powerup']['kind'] = kind
    if not zombie_themes_in(wave):
        out['zombie_themes'] = False
    if diamonds_in(wave):
        out['diamonds'] = diamonds_in(wave)
    return out


def _cutscene_to_object(line: dict) -> dict:
    """One `Sounds` entry back in the file's own shape - the inverse of a line of `_cutscene`."""
    from .adsound import cg_point_from_string
    one: dict = {'sound': line.get('name')}
    after = line.get('spawn_after')
    if isinstance(after, dict):
        one['after'] = {'sound': after.get('enemy'), 'time': after.get('time', 0),
                        'when': 'starts' if after.get('afterStart') else 'ends'}
    else:
        one['at'] = line.get('spawn_time', 0.0)
    one['blocker'] = bool(line.get('blocker'))
    one['skippable'] = bool(line.get('skippable'))
    if line.get('stopsOtherSounds'):
        one['stops_other_sounds'] = True
    if line.get('loop'):
        one['loop'] = True
    if line.get('gain'):
        one['gain'] = line['gain']
    if line.get('spawn_angle') is not None:
        one['angle'] = line['spawn_angle']
        one['distance'] = line.get('spawn_distance', 6.0)
    if line.get('position') is not None:
        one['from'] = list(cg_point_from_string(line['position']))
        if line.get('finalPosition') is not None:
            one['to'] = list(cg_point_from_string(line['finalPosition']))
    return one


def waves_of(challenge_id) -> list:
    """The challenge's waves, in the brick shape, in the order they are played.

    `custom_waves` rather than `bricks`: the cutscene-only bricks between the waves are not waves, and a
    screen that walked them would number the third crowd as the fifth and write each scene back out as a
    wave of its own.  `bricks` is the fallback for a challenge dictionary from before `custom_waves`
    existed, where the two were the same list.
    """
    load()
    d = PLISTS.get(challenge_id) or {}
    return [PLISTS[brick] for brick in (d.get('custom_waves') or d.get('bricks') or ())
            if brick in PLISTS]


# ------------------------------------------------------------------------- placing zombies by hand
def blank_wave() -> dict:
    """A wave with nothing in it yet.  `NoBlast` because that is what a wave of the port's own is unless
    it says otherwise: nothing in it explodes whatever the player is carrying."""
    return {'Enemies': {}, 'NoBlast': True}


def slot_name(kind: str, at: int) -> str:
    """The key a zombie has in a wave: its kind, and its place in the wave counting from one.

    `Enemies` is a dictionary and the kind is read back off the front of the key (`name.split(' ')[0]`,
    `Enemy.__init__` 0x10005ddd4), so two of a kind need two keys and the rest of the key is only there to
    tell them apart.

    The *place* and not the number of that kind, and this is the only function that decides it (user
    request, 2026-09-30).  There used to be two answers: `_wave` numbered by the place in the wave when it
    read a file, and `free_slot` numbered per kind when the editor added one, so a wave of a Zombie, a
    Chainsaw and a Zombie was `Zombie 1, Chainsaw 1, Zombie 2` in the editor and `Zombie 1, Chainsaw 2,
    Zombie 3` once saved and read again.  Every save renamed most of the wave, and a screen still holding
    the name it was given could not find its zombie - `KeyError: 'Chainsaw 1'`, which is what editing a
    second wave did.  One scheme, kept by `renumber` after anything that moves a zombie, and the names a
    screen is holding survive a save.
    """
    return '%s %i' % (kind, at + 1)


def kind_of(slot) -> str:
    """The kind off the front of a key, the way `Enemy.__init__` 0x10005ddd4 reads it."""
    return str(slot).split(' ')[0]


def renumber(wave: dict) -> dict:
    """Put the wave's keys back in the shape `slot_name` gives, in the order they are in.

    Answers {the key it had: the key it has}, so a caller holding one can follow it.  Called after anything
    that adds, removes or moves a zombie, which is what keeps the editor's names and the file's the same.
    """
    enemies = wave.get('Enemies') or {}
    moved, fresh = {}, {}
    for at, (slot, place) in enumerate(list(enemies.items())):
        key = slot_name(kind_of(slot), at)
        moved[slot] = key
        fresh[key] = place
    if enemies or 'Enemies' in wave:
        wave['Enemies'] = fresh
    return moved


def free_slot(wave: dict, kind: str) -> str:
    """The key another `kind` would have if it were added to this wave now - the end of it."""
    return slot_name(kind, len(wave.get('Enemies') or {}))


def add_enemy(wave: dict, kind: str, angle: float, distance: float, at: float) -> str:
    key = free_slot(wave, kind)
    wave.setdefault('Enemies', {})[key] = {'spawn_angle': round(float(angle) % 360.0, 2),
                                           'spawn_distance': float(distance), 'spawn_time': float(at)}
    return renumber(wave).get(key, key)


def remove_enemy(wave: dict, slot: str) -> bool:
    """Take one zombie out of a wave and put the wave's keys back in order.  True if there was one."""
    enemies = wave.get('Enemies') or {}
    if slot not in enemies:
        return False
    enemies.pop(slot)
    renumber(wave)
    return True


def rename_kind(wave: dict, slot: str, kind: str) -> str:
    """Make the zombie at `slot` a `kind` instead, without moving it, and answer its new key.

    In place rather than out and back in again: a zombie's key holds its place in the wave, so taking it out
    and appending it would move it to the end and rename everything after it.
    """
    enemies = wave.get('Enemies') or {}
    if slot not in enemies:
        return slot
    at = list(enemies).index(slot)
    fresh = {}
    for i, (key, place) in enumerate(list(enemies.items())):
        fresh[slot_name(kind if i == at else kind_of(key), i)] = place
    wave['Enemies'] = fresh
    return slot_name(kind, at)


def move_enemy(waves: list, from_wave: int, slot: str, to_wave: int) -> str:
    """Move one zombie into another wave, and answer the key it has there.

    Its bearing, distance and arrival time go with it: the wave is what changed, not where it comes from.
    Both waves are put back in order afterwards, since one lost a zombie and the other gained one.
    """
    place = (waves[from_wave].get('Enemies') or {}).pop(slot)
    key = free_slot(waves[to_wave], kind_of(slot))
    waves[to_wave].setdefault('Enemies', {})[key] = place
    renumber(waves[from_wave])
    return renumber(waves[to_wave]).get(key, key)


def wave_is_empty(wave: dict) -> bool:
    """A wave with nothing in it at all, which `_read` refuses and no player meant to make."""
    return not (wave.get('Enemies') or {}) and not (wave.get('Sounds') or [])


def starter_challenge(title: str, rng=None) -> dict:
    """A challenge object for one somebody has just named: theirs, and empty.

    One wave with nothing in it (user request, 2026-09-30).  It started as one generated crowd, so that a
    challenge could be played the moment it was named, but a crowd nobody asked for is a crowd they have to
    delete a zombie at a time before they can place their own - and placing their own is what naming a
    challenge is for.  A challenge still needs at least one wave (`_read` refuses one with none), so one
    empty wave is as empty as a challenge gets.

    It is not playable until something is put in it, which its row in the arena says (`nothing in it yet`).
    `Reroll the waves` in the editor is the way back to a generated crowd for anybody who wants one.
    """
    rng = rng or random.Random()
    loadout = _loadout(rng)
    waves = [blank_wave()]
    guns = [w for w in loadout if not is_melee(w)]
    weapons = [{'name': w, 'ammo': 120} for w in guns]
    weapons += [{'name': w} for w in loadout if is_melee(w)]
    return {
        'format': FORMAT_CHALLENGE, 'version': FORMAT_VERSION,
        'id': _slug(title) + '_' + ('%04x' % rng.randrange(1 << 16)),
        'title': title,
        'objective': _EMPTY_OBJECTIVE,
        'tip': tip_for(DEFAULT_DIFFICULTY),
        'ambient': rng.choice(AMBIENTS), 'ambient_gain': 0.5,
        'difficulty': DEFAULT_DIFFICULTY,
        'weapons': weapons, 'coins': DEFAULT_REWARD,
        'accuracy': {'objective': 45, 'reward': 150},
        'time': {'objective': 120, 'reward': 150},
        'waves': [_wave_object(wave) for wave in waves],
    }


def create_challenge(title: str, arena=None, rng=None) -> str:
    """A new challenge of that name, as a file of its own or appended to an arena's pack.

    Returns its id.  `arena` names an arena that already exists - its pack gains a challenge - or is left
    out, in which case the challenge is a `.adchallenge` of its own and gathers with the other loose ones.
    """
    load()
    document = starter_challenge(title, rng)
    ids = arena_challenges(arena) if arena else ()
    path, _index = source_of(ids[0]) if ids else ('', None)
    if path and path.lower().endswith(PACK_SUFFIX) and os.path.isfile(path):
        with open(path, 'r', encoding='utf-8') as fh:
            pack = json.load(fh)
        holds = pack.get('challenges')
        if not isinstance(holds, list):
            raise _Bad('that arena\'s file cannot be added to')
        if len(holds) >= MAX_CHALLENGES:
            raise _Bad('an arena holds at most %i challenges' % MAX_CHALLENGES)
        document.pop('format', None)
        document.pop('version', None)
        holds.append(document)
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(pack, fh, indent=2, ensure_ascii=False)
            fh.write('\n')
    else:
        if arena and arena != LOOSE_ARENA:
            document['arena'] = arena
        write(document, CHALLENGE_SUFFIX)
    load(force=True)
    return PREFIX + _slug(document['id'])


def create_arena(name: str, rng=None) -> str:
    """A new arena of that name, holding one challenge to start it off.

    An arena with nothing in it is a file `_read` refuses ("it has no challenges in it") and a row that
    opens on nothing, so naming an arena makes its first challenge at the same time.  Returns the name.
    """
    rng = rng or random.Random()
    one = starter_challenge('%s 1' % name, rng)
    one.pop('format', None)
    one.pop('version', None)
    write({'format': FORMAT_PACK, 'version': FORMAT_VERSION, 'arena': name, 'challenges': [one]},
          PACK_SUFFIX)
    load(force=True)
    return name


def rename_arena(old: str, new: str) -> int:
    """Rename every file that puts its challenges in `old`, and answer how many were changed.

    A pack says its arena once, at the top.  The loose `.adchallenge` files that gather under the default
    name say it each - or, having never said it at all, need telling for the first time.
    """
    load()
    touched = set()
    for cid in arena_challenges(old):
        path, _index = source_of(cid)
        if not path or path in touched or not os.path.isfile(path):
            continue
        touched.add(path)
        with open(path, 'r', encoding='utf-8') as fh:
            document = json.load(fh)
        document['arena'] = new
        with open(path, 'w', encoding='utf-8') as fh:
            json.dump(document, fh, indent=2, ensure_ascii=False)
            fh.write('\n')
    load(force=True)
    log.info('renamed the arena %s to %s across %i file(s)', old, new, len(touched))
    return len(touched)


def delete_challenge(challenge_id) -> str:
    """Delete the file a challenge came from, and read the folder again.

    A challenge inside a pack takes the whole pack with it, which is why the editor says so before asking.
    Splitting a pack up would be a different file from the one the player put there.
    """
    path, _index = source_of(challenge_id)
    if not path or not os.path.isfile(path):
        raise _Bad('the file it came from is no longer there')
    os.remove(path)
    log.info('deleted %s', path)
    load(force=True)
    return path


def generate_challenge(rng=None) -> tuple:
    """(the path written, the title).  The folder is read again afterwards, so the new row is there at once."""
    document = build_challenge(rng)
    path = write(document, CHALLENGE_SUFFIX)
    load(force=True)
    return path, document['title']


def generate_pack(count: int = 0, rng=None) -> tuple:
    """(the path written, the arena's name, how many challenges are in it)."""
    document = build_pack(count, rng)
    path = write(document, PACK_SUFFIX)
    load(force=True)
    return path, document['arena'], len(document['challenges'])
