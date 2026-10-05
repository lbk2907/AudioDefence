"""PORT ADDITION (user request, 2026-10-05): Settings -> Sound -> 3D sound - which head the game hears with.

A 3D sound - an HRTF - is a recording of how one head hears a sound from each direction, and every head hears
a little differently, so one that tells ahead from behind clearly for one player can blur them for another.
The original has one, the IRCAM set built into its binary, which the port plays as `audiodefence_ircam1050`
(tools/build_hrtf.py).  The port offers:

* **The game's own**, the default: the original's.
* **OpenAL Soft's built-in** (Windows, the Mac): the one compiled into OpenAL Soft.  The phone has no OpenAL
  Soft - its sound is the app's own mixer (s3d/android.py) - and so not this either.
* **The player's own**: any `.mhr` file in the `hrtf` folder in the game's own folder (`folder()`), made
  with OpenAL Soft's makemhr from a research set of recordings (the README, "Your own 3D sound").  None is
  built into the game: each set has terms of its own, and the player brings the file under them (user
  request).  The folder is beside AudioDefence.exe - beside the app on the Mac - as the `localization`
  folder is (user request): the updater deletes files only from the folders a build owns (updater.OWNED_DIRS),
  and the phone's unpacking only from its `game` folder, so a player's files there are left alone.  On a
  computer the file is put in the folder; on the phone, where the folder is inside the app and Android shows
  an app only the files it made, it is added through Android's file picker (Settings -> Sound -> Add 3D
  sound file), and taken out with Remove 3D sound file.

The choice is `sound3d` in settings.json: 'game', 'builtin' or 'file:' and the file's name without `.mhr`.
A file that has gone is the game's own again.  The device switches as the choice is made, with nothing
stopped: OpenAL Soft resets its device with the other HRTF (device.Device.use_3d_sound), the phone's mixer
takes the other file (Bridge.setHrtf).
"""
from __future__ import annotations

import os

from .. import paths
from ..platform import host

GAME = 'game'
BUILTIN = 'builtin'
FILE = 'file:'
#: the game's own HRTF, in assets/hrtf (device.HRTF_NAME), and OpenAL Soft's own, by the names OpenAL Soft
#: lists them under
GAME_NAME = 'audiodefence_ircam1050'
BUILTIN_NAME = 'Built-In HRTF'
LABELS = {GAME: "The game's own", BUILTIN: "OpenAL Soft's built-in"}


def folder() -> str:
    """The player's own 3D sounds: `hrtf` in the game's folder, made when first asked for - where it can be:
    a game in a folder it may not write to has no such folder, and none of the player's own to offer."""
    path = os.path.join(paths.EXE_DIR, 'hrtf')
    try:
        os.makedirs(path, exist_ok=True)
    except OSError:
        pass
    return path


def own_files() -> list:
    """The names of the player's own .mhr files, without `.mhr`, in alphabetical order.  A file named like
    the game's own or OpenAL Soft's would be listed by OpenAL Soft under another name, so it is left out."""
    try:
        names = [name[:-4] for name in os.listdir(folder()) if name.lower().endswith('.mhr')]
    except OSError:
        return []
    return sorted((name for name in names if name and name not in (GAME_NAME, BUILTIN_NAME)), key=str.lower)


def path_of(choice: str) -> str:
    """The file a player's own choice is, or ''."""
    return os.path.join(folder(), choice[len(FILE):] + '.mhr') if choice.startswith(FILE) else ''


def choices() -> list:
    """(choice, what the list says) for each 3D sound there is to choose."""
    offered = [(GAME, LABELS[GAME])]
    if not host.ANDROID:
        offered.append((BUILTIN, LABELS[BUILTIN]))
    offered += [(FILE + name, name) for name in own_files()]
    return offered


def usable(choice: str) -> str:
    """The choice, or the game's own where it cannot be had here: a file that has gone, the built-in on
    the phone, anything not understood."""
    if choice == BUILTIN and not host.ANDROID:
        return choice
    if choice.startswith(FILE) and os.path.isfile(path_of(choice)):
        return choice
    return GAME


def label(choice: str) -> str:
    return LABELS.get(choice) or choice[len(FILE):]


def openal_name(choice: str) -> str:
    """What OpenAL Soft lists this choice under: a file by its name without `.mhr`."""
    if choice == BUILTIN:
        return BUILTIN_NAME
    if choice.startswith(FILE):
        return choice[len(FILE):]
    return GAME_NAME


def stored() -> str:
    """The choice in settings.json, as it can be had (`usable`).  Read from the file's store directly, so
    the sound device can ask for it before the rest of the game is there."""
    from ..platform.defaults import UserDefaults
    value = UserDefaults.standard().object('sound3d')
    return usable(value) if isinstance(value, str) else GAME
