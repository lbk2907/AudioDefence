"""PORT ADDITION (user request, 2026-10-05): 3D sounds made from research recordings, by the game itself.

A research set of recordings comes as a SOFA file (`.sofa`); the game hears with an `.mhr` (s3d/sound3d.py).
OpenAL Soft's makemhr turns one into the other, and the game carries it on Windows (vendor/makemhr, GPL 2 or
later - its README.txt and COPYING.GPLv2 travel with it).  So a `.sofa` put in the player's `hrtf` folder, beside
the game, is made into an `.mhr` of the same name there: from Settings -> Sound -> 3D sound, in the background,
said when ready (ui/settings.py), and from tools/make_3d_sounds.py for whoever has the repository.

A file is made again when its `.sofa` is newer than its `.mhr`, and not tried twice in one run when makemhr
gives up on it.  makemhr writes to `<name>.mhr.part`, which 3D sound does not list, and the file is renamed
only once it is whole.  The settings are the README's: the game's sample rate, and makemhr's own defaults for
the rest, which keep every response within the 128 points OpenAL Soft and the phone's mixer take.  The Mac and
the phone have no makemhr: there a `.sofa` is made into an `.mhr` on a Windows computer.
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading

from .. import paths
from ..platform import host
from . import sound3d

log = logging.getLogger('s3d.makehrtf')

MAKEMHR = os.path.join(paths.VENDOR, 'makemhr', 'makemhr.exe')
#: the game's sample rate (device.SAMPLE_RATE), which the README's command gives makemhr as well
RATE = 44100
#: how long one set may take before makemhr is given up on: the largest sets take a minute or two
TIMEOUT = 600
#: makemhr's threads: all but one of the processor's, the one left for the game.  makemhr's own default is two,
#: and the work divides: MIT's KEMAR took 42 s on two of twelve and 15 s on eight, to the same file
THREADS = max(2, (os.cpu_count() or 3) - 1)

_failed: dict = {}                                # .sofa path -> its time when makemhr gave up on it
_busy = threading.Lock()


def can_make() -> bool:
    """Whether this game can make a 3D sound itself: Windows, with makemhr where the build puts it."""
    return host.WINDOWS and os.path.isfile(MAKEMHR)


def target_of(sofa: str) -> str:
    return os.path.splitext(sofa)[0] + '.mhr'


def waiting(folder: str | None = None, everything: bool = False) -> list:
    """The `.sofa` files in the folder (the player's `hrtf` folder) with no `.mhr` as new as they are - or all of
    them - in alphabetical order, leaving out any makemhr gave up on in this run unless they have changed."""
    folder = os.path.abspath(folder or sound3d.folder())
    try:
        names = sorted((n for n in os.listdir(folder) if n.lower().endswith('.sofa')), key=str.lower)
    except OSError:
        return []
    found = []
    for name in names:
        sofa = os.path.join(folder, name)
        try:
            when = os.path.getmtime(sofa)
        except OSError:
            continue
        if _failed.get(sofa) == when:
            continue
        mhr = target_of(sofa)
        if everything or not os.path.isfile(mhr) or os.path.getmtime(mhr) < when:
            found.append(sofa)
    return found


def make(sofa: str) -> str:
    """Make the `.mhr` beside one `.sofa`.  '' when it is made, else why not, in makemhr's own last words."""
    if not can_make():
        return 'makemhr is not here'
    mhr = target_of(sofa)
    part = mhr + '.part'
    command = [MAKEMHR, '-r', str(RATE), '-j', str(THREADS), '-i', sofa, '-o', part]
    try:
        done = subprocess.run(command, cwd=os.path.dirname(MAKEMHR), capture_output=True, text=True,
                              errors='replace', timeout=TIMEOUT,
                              creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except (OSError, subprocess.SubprocessError) as exc:
        _remove(part)
        return _gave_up(sofa, str(exc))
    lines = [line.strip() for line in (done.stdout + '\n' + done.stderr).replace('\r', '\n').split('\n')
             if line.strip()]
    try:
        with open(part, 'rb') as fh:
            whole = fh.read(8) == b'MinPHR03'
    except OSError:
        whole = False
    if done.returncode != 0 or not whole:
        _remove(part)
        reason = next((line for line in reversed(lines) if 'rror' in line), lines[-1] if lines else '')
        return _gave_up(sofa, reason or 'makemhr stopped with code %d' % done.returncode)
    try:
        os.replace(part, mhr)
    except OSError as exc:
        _remove(part)
        return _gave_up(sofa, str(exc))
    _failed.pop(sofa, None)
    log.info('3D sound made: %s', mhr)
    return ''


def make_in_background(files: list, made, finished) -> bool:
    """Make each file on a thread of its own, one after another, calling `made(sofa, problem)` after each and
    `finished()` at the end - on that thread: the caller hands them to the main one.  False, and nothing
    started, while a run is still going."""
    if not _busy.acquire(blocking=False):
        return False

    def run():
        try:
            for sofa in files:
                made(sofa, make(sofa))
        finally:
            _busy.release()
            finished()
    threading.Thread(target=run, name='make 3D sounds', daemon=True).start()
    return True


def busy() -> bool:
    return _busy.locked()


def _gave_up(sofa: str, reason: str) -> str:
    try:
        _failed[sofa] = os.path.getmtime(sofa)
    except OSError:
        pass
    log.warning('3D sound not made from %s: %s', sofa, reason)
    return reason


def _remove(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass
