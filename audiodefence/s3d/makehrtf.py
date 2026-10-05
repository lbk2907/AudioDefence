"""PORT ADDITION (user request, 2026-10-05): 3D sounds made from research recordings, by the game itself.

A research set of recordings comes as a SOFA file (`.sofa`); the game hears with an `.mhr` (s3d/sound3d.py).
OpenAL Soft's makemhr turns one into the other, and the game carries it on Windows (vendor/makemhr, GPL 2 or
later - its README.txt and COPYING.GPLv2 travel with it).  So a `.sofa` put in the player's `hrtf` folder, beside
the game, is made into an `.mhr` of the same name there when the game starts, before the logo, its progress
said as it goes (ui/make_sounds.py); and by tools/make_3d_sounds.py for whoever has the repository.

A file is made again when its `.sofa` is newer than its `.mhr`, and not tried twice in one run when makemhr
gives up on it.  makemhr writes to `<name>.mhr.part`, which 3D sound does not list, and the file is renamed
only once it is whole.  The settings are the README's: the game's sample rate, and makemhr's own defaults for
the rest, which keep every response within the 128 points OpenAL Soft and the phone's mixer take.  The Mac and
the phone have no makemhr: there a `.sofa` is made into an `.mhr` on a Windows computer.
"""
from __future__ import annotations

import logging
import os
import queue
import re
import subprocess
import threading
import time

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
#: makemhr's stages as it reports them, and the share of the whole each comes to - timed over MIT's KEMAR on
#: eleven threads: loading 0.2 s, onsets 2.3 s, magnitudes 2.4 s, minimum phase 8.1 s, the rest at once.  Each
#: line it writes says how far into its stage it is ("Calculating HRIR onsets... 46 of 1420", "38% done (630 of
#: 1656)"), which is turned into how far into the whole (`progress`).
STAGES = (('Loading HRIRs', 0.0, 3.0), ('Calculating HRIR onsets', 3.0, 20.0),
          ('Calculating HRIR magnitudes', 20.0, 38.0), ('% done', 38.0, 98.0))
_COUNT = re.compile(r'(\d+) of (\d+)')

_failed: dict = {}                                # .sofa path -> its time when makemhr gave up on it


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


def progress_of(line: str) -> float | None:
    """How far into the whole one of makemhr's lines says it is, 0 to 100, or None for a line that does not."""
    if line.startswith('Operation completed'):
        return 100.0
    for marker, start, end in STAGES:
        if marker in line:
            count = _COUNT.search(line)
            done, total = (int(count.group(1)), int(count.group(2))) if count else (0, 1)
            return start + (end - start) * min(1.0, done / max(total, 1))
    return None


#: what `make` answers when it was stopped (`cancelled`), rather than given up on
STOPPED = 'stopped'


def make(sofa: str, progress=None, cancelled=None) -> str:
    """Make the `.mhr` beside one `.sofa`.  '' when it is made, STOPPED when `cancelled()` said so, else why not,
    in makemhr's own last words.  `progress(percent)` is told as makemhr goes, from this thread."""
    if not can_make():
        return 'makemhr is not here'
    mhr = target_of(sofa)
    part = mhr + '.part'
    command = [MAKEMHR, '-r', str(RATE), '-j', str(THREADS), '-i', sofa, '-o', part]
    try:
        process = subprocess.Popen(command, cwd=os.path.dirname(MAKEMHR), stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except OSError as exc:
        return _gave_up(sofa, str(exc))
    said: queue.Queue = queue.Queue()

    def read() -> None:                                   # on a thread of its own, so a stop is never kept
        line = bytearray()                                # waiting for makemhr's next line
        for byte in iter(lambda: process.stdout.read(1), b''):
            if byte not in b'\r\n':                       # a line ends at \r while a stage counts up
                line += byte
            elif line:
                said.put(line.decode('utf-8', 'replace').strip())
                line.clear()
        said.put(None)
    threading.Thread(target=read, name='makemhr output', daemon=True).start()
    lines, began = [], time.monotonic()
    while True:
        stopped = cancelled is not None and cancelled()
        if stopped or time.monotonic() - began > TIMEOUT:
            process.kill()
            process.wait()
            _remove(part)
            return STOPPED if stopped else _gave_up(sofa, 'it took longer than %d seconds' % TIMEOUT)
        try:
            text = said.get(timeout=0.1)
        except queue.Empty:
            continue
        if text is None:
            break
        if text:
            lines.append(text)
            del lines[:-20]
            percent = progress_of(text)
            if percent is not None and progress is not None:
                progress(percent)
    code = process.wait()
    try:
        with open(part, 'rb') as fh:
            whole = fh.read(8) == b'MinPHR03'
    except OSError:
        whole = False
    if code != 0 or not whole:
        _remove(part)
        reason = next((text for text in reversed(lines) if 'rror' in text), lines[-1] if lines else '')
        return _gave_up(sofa, reason or 'makemhr stopped with code %d' % code)
    try:
        os.replace(part, mhr)
    except OSError as exc:
        _remove(part)
        return _gave_up(sofa, str(exc))
    _failed.pop(sofa, None)
    log.info('3D sound made: %s', mhr)
    return ''


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
