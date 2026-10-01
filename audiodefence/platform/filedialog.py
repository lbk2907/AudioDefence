"""PORT ADDITION (user request): the system's own "open a file" dialog.

A phone has no file system a player can see, so the original never needed one and there is no method in
the binary this departs from.  On Windows the port needs one for the Challenge maker: a cutscene is a
recording the player already has somewhere, and the only honest way to ask which one is to let them find
it the way they find every other file.

Windows gets the real Explorer dialog through `comdlg32.GetOpenFileNameW`, which is what every program
that opens a file uses and is already on the machine - no new dependency, and a screen reader reads it
because it is the system's own window rather than something drawn here.  The Mac gets AppleScript's
`choose file`, which is Finder's.

The dialog is modal: the game stops while it is open, as it does for any system dialog, and carries on
when it closes.  Nothing here raises - a dialog that cannot be shown answers None, which every caller
reads as "no file was chosen".
"""
from __future__ import annotations

import ctypes
import logging
import os
import subprocess

from . import host

log = logging.getLogger('filedialog')

#: What the picker offers for a cutscene.  Everything here is something PyAV decodes - the same decoder
#: that reads the game's own `.m4a` (`s3d/decoder.py`) - so the list is what FFmpeg reads and not a
#: shorter one of the port's choosing.  The order is the order the dialog's filter shows them in.
AUDIO_EXTENSIONS = ('.wav', '.mp3', '.ogg', '.oga', '.opus', '.flac', '.m4a', '.aac', '.mp4',
                    '.wma', '.aif', '.aiff', '.aifc', '.caf', '.w64', '.au')

_OFN_FILEMUSTEXIST = 0x00001000
_OFN_PATHMUSTEXIST = 0x00000800
_OFN_NOCHANGEDIR = 0x00000008
_OFN_EXPLORER = 0x00080000


class _OpenFileNameW(ctypes.Structure):
    """OPENFILENAMEW as 64-bit Windows lays it out (commdlg.h)."""
    _fields_ = [
        ('lStructSize', ctypes.c_uint32),
        ('hwndOwner', ctypes.c_void_p),
        ('hInstance', ctypes.c_void_p),
        ('lpstrFilter', ctypes.c_wchar_p),
        ('lpstrCustomFilter', ctypes.c_wchar_p),
        ('nMaxCustFilter', ctypes.c_uint32),
        ('nFilterIndex', ctypes.c_uint32),
        ('lpstrFile', ctypes.c_wchar_p),
        ('nMaxFile', ctypes.c_uint32),
        ('lpstrFileTitle', ctypes.c_wchar_p),
        ('nMaxFileTitle', ctypes.c_uint32),
        ('lpstrInitialDir', ctypes.c_wchar_p),
        ('lpstrTitle', ctypes.c_wchar_p),
        ('Flags', ctypes.c_uint32),
        ('nFileOffset', ctypes.c_uint16),
        ('nFileExtension', ctypes.c_uint16),
        ('lpstrDefExt', ctypes.c_wchar_p),
        ('lCustData', ctypes.c_void_p),
        ('lpfnHook', ctypes.c_void_p),
        ('lpTemplateName', ctypes.c_wchar_p),
        ('pvReserved', ctypes.c_void_p),
        ('dwReserved', ctypes.c_uint32),
        ('FlagsEx', ctypes.c_uint32),
    ]


def _windows_filter(extensions) -> str:
    """The dialog's filter: pairs of label and pattern, each ending in a NUL and the lot in one more."""
    patterns = ';'.join('*%s' % e for e in extensions)
    parts = ['Audio files', patterns, 'All files', '*.*']
    return '\0'.join(parts) + '\0\0'


def choose_audio_file(title: str = 'Choose a sound', start_in: str = ''):
    """The path a player picked, or None if they cancelled or no dialog could be shown."""
    if host.MAC:
        return _mac_choose(title, start_in)
    if not host.WINDOWS:
        log.info('no file dialog on this platform')
        return None
    try:
        buffer = ctypes.create_unicode_buffer(4096)
        ofn = _OpenFileNameW()
        ofn.lStructSize = ctypes.sizeof(_OpenFileNameW)
        ofn.lpstrFilter = _windows_filter(AUDIO_EXTENSIONS)
        ofn.nFilterIndex = 1
        ofn.lpstrFile = ctypes.cast(buffer, ctypes.c_wchar_p)
        ofn.nMaxFile = len(buffer)
        ofn.lpstrTitle = title
        if start_in and os.path.isdir(start_in):
            ofn.lpstrInitialDir = start_in
        # NOCHANGEDIR matters: the game reads its own data by relative path in places, and a dialog that
        # left the working directory somewhere else would break that for the rest of the run.
        ofn.Flags = _OFN_FILEMUSTEXIST | _OFN_PATHMUSTEXIST | _OFN_NOCHANGEDIR | _OFN_EXPLORER
        if not ctypes.windll.comdlg32.GetOpenFileNameW(ctypes.byref(ofn)):
            return None                                   # cancelled, or the dialog refused to open
        chosen = buffer.value
        return chosen if chosen and os.path.isfile(chosen) else None
    except Exception:                                     # a dialog is never worth crashing the game for
        log.exception('the file dialog could not be shown')
        return None


def _mac_choose(title: str, start_in: str):
    """Finder's own chooser, through AppleScript.  `choose file` raises when it is cancelled, which
    osascript reports as a non-zero exit - read here as "no file"."""
    kinds = ', '.join('"%s"' % e.lstrip('.') for e in AUDIO_EXTENSIONS)
    where = ' default location POSIX file "%s"' % start_in if start_in and os.path.isdir(start_in) else ''
    script = ('set theFile to choose file with prompt "%s"%s of type {%s}\n'
              'POSIX path of theFile' % (title.replace('"', "'"), where, kinds))
    try:
        done = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.SubprocessError):
        log.exception('the file dialog could not be shown')
        return None
    if done.returncode != 0:
        return None
    chosen = (done.stdout or '').strip()
    return chosen if chosen and os.path.isfile(chosen) else None
