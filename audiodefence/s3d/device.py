"""OpenAL Soft configuration and output device for the port.

The game's own HRTF (``assets/hrtf/audiodefence_ircam1050.mhr``, built by tools/build_hrtf.py from the set
embedded in the original binary) is made visible to OpenAL Soft through a private ``alsoft.ini`` named by the
``ALSOFT_CONF`` environment variable, so the user's own OpenAL configuration is never touched.

The file is written to the system's temporary folder (user request, 2026-10-03, after Papa Sangre for
Windows, which does the same).  It is plumbing, not a setting: rewritten from scratch at every start, with an
absolute path to wherever this copy of the game is, and nothing a player changes in it lasts.  Next to the
settings and the save it looked like one of them.

PORT ADDITION (user request, 2026-10-05): the HRTF is the one chosen in Settings -> Sound -> 3D sound
(s3d/sound3d.py), the game's own by default.  OpenAL Soft is shown the player's own folder as well, and its
default places after them - the empty entry that the trailing comma of `hrtf-paths` is - which is what lists
its built-in HRTF.  What else may be in those default places is not offered: `use_3d_sound` takes only what
3D sound lists.
"""
from __future__ import annotations

import logging
import os
import tempfile

from .. import paths
from . import openal as oal
from . import sound3d

log = logging.getLogger('s3d')

HRTF_NAME = 'audiodefence_ircam1050'
SAMPLE_RATE = 44100


def config_path() -> str:
    """Where the private alsoft.ini goes: a folder of the game's own in the system's temporary folder, or
    the temporary folder itself if that cannot be made."""
    folder = os.path.join(tempfile.gettempdir(), 'AudioDefence')
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        folder = tempfile.gettempdir()
    return os.path.join(folder, 'alsoft.ini')


def write_alsoft_config() -> str:
    path = config_path()
    lines = [
        '# Written by Audio Defence at start-up; edits are overwritten.',
        '[general]',
        'stereo-encoding = hrtf',
        'hrtf = true',
        f'hrtf-paths = {paths.HRTF_DIR},{sound3d.folder()},',
        f'default-hrtf = {HRTF_NAME}',
        f'frequency = {SAMPLE_RATE}',
        'output-limiter = true',
        '',
    ]
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write('\n'.join(lines))
    return path


#: how long after the system says the default output changed before the game moves to it.  Windows says it
#: several times over for one change - once for each role a device can play - and the game moves once.
FOLLOW_AFTER = 0.5


class Device:
    """Opens the default playback device with the game's HRTF enabled, and keeps to the default device when
    the system changes it."""

    def __init__(self):
        os.environ['ALSOFT_CONF'] = write_alsoft_config()
        self.al = oal.AL()
        self.device = self.al.alcOpenDevice(None)
        if not self.device:
            raise oal.OpenALError('could not open the audio output device')
        attrs = {oal.ALC_FREQUENCY: SAMPLE_RATE, oal.ALC_HRTF_SOFT: oal.ALC_TRUE,
                 oal.ALC_MONO_SOURCES: 255, oal.ALC_STEREO_SOURCES: 64}
        self.context = self.al.alcCreateContext(self.device, oal.attr_list(attrs))
        if not self.context:
            raise oal.OpenALError('could not create the audio context')
        self.al.make_current(self.context)
        names = self.al.hrtf_names(self.device)
        self.hrtf_found = HRTF_NAME in names
        #: what the device is opened with, and so what it is opened with again on another output
        self.base_attrs = attrs
        self.attrs = self._attrs_for(names.index(HRTF_NAME) if self.hrtf_found else None)
        if self.hrtf_found:
            self.al.reset_device(self.device, self.attrs)
        self.hrtf_status = self.al.get_int(self.device, oal.ALC_HRTF_STATUS_SOFT)
        if not self.hrtf_found or self.hrtf_status != 1:              # ALC_HRTF_ENABLED_SOFT
            # the built-in HRTF (or none) would sound plausible but not like the original
            log.error('game HRTF %s not in use (found=%s, status=%s, offered=%s)',
                      HRTF_NAME, self.hrtf_found, self.hrtf_status, names)
        #: Settings -> Sound -> 3D sound, as it is in use
        self.sound_3d = sound3d.GAME
        chosen = sound3d.stored()
        if chosen != sound3d.GAME and not self.use_3d_sound(chosen):
            log.warning("3D sound %s could not be used: the game's own instead", chosen)
        log.info('sound goes to %s', self.output_name())
        self._events = None
        self._follow_pending = False
        self.follow_default_device()

    def _attrs_for(self, hrtf_id) -> list:
        listed = []
        for k, v in {**self.base_attrs, **({} if hrtf_id is None else {oal.ALC_HRTF_ID_SOFT: hrtf_id})}.items():
            listed += [k, v]
        return listed

    def current_hrtf(self) -> str:
        name = self.al.alcGetString(self.device, oal.ALC_HRTF_SPECIFIER_SOFT) if self.device else None
        return name.decode('utf-8', 'replace') if name else ''

    def use_3d_sound(self, choice: str) -> bool:
        """PORT ADDITION: Settings -> Sound -> 3D sound - the device reset with that HRTF, everything playing
        carrying on.  OpenAL Soft lists the folders again each time it is asked, so a file put in the player's
        folder meanwhile is found.  False, and the HRTF in use kept, where the choice is not listed or does not
        load - a file that is not an HRTF, or one OpenAL Soft cannot read."""
        if not self.device or choice != sound3d.usable(choice):
            return False
        names = self.al.hrtf_names(self.device)
        wanted = sound3d.openal_name(choice)
        if wanted not in names:
            log.warning('3D sound %s is not among %s', wanted, names)
            return False
        before = self.attrs
        self.attrs = self._attrs_for(names.index(wanted))
        if (self.al.reset_device(self.device, self.attrs)
                and self.al.get_int(self.device, oal.ALC_HRTF_STATUS_SOFT) == 1
                and self.current_hrtf() == wanted):
            self.sound_3d = choice
            self.hrtf_status = 1
            log.info('3D sound: %s', wanted)
            return True
        log.warning('3D sound %s did not load (in use: %s); back to the one before', wanted, self.current_hrtf())
        self.attrs = before
        self.al.reset_device(self.device, self.attrs)
        self.hrtf_status = self.al.get_int(self.device, oal.ALC_HRTF_STATUS_SOFT)
        return False

    def output_name(self) -> str:
        name = self.al.alcGetString(self.device, oal.ALC_ALL_DEVICES_SPECIFIER) if self.device else None
        return name.decode('utf-8', 'replace') if name else ''

    # --- keeping to the default output ---------------------------------------------------------
    # PORT ADDITION (user request, 2026-09-29): the device was opened once, on whatever was the default
    # output when the game started, and stayed there.  Choosing another output in Windows - headphones for
    # speakers - left the game playing into the old one while the speech moved (SAPI 5 follows the default
    # of its own accord).  OpenAL Soft says when the default changes (ALC_SOFT_system_events) and can move
    # an open device to another output with its contexts, sources and buffers intact
    # (ALC_SOFT_reopen_device), so nothing that is playing stops.  A library without either keeps to the
    # device it opened, as before.

    def follow_default_device(self) -> None:
        """Ask to be told when the default output changes."""
        al = self.al
        try:
            if not (al.alcIsExtensionPresent(self.device, b'ALC_SOFT_system_events')
                    and al.alcIsExtensionPresent(self.device, b'ALC_SOFT_reopen_device')
                    and al.event_supported(oal.ALC_EVENT_TYPE_DEFAULT_DEVICE_CHANGED_SOFT,
                                           oal.ALC_PLAYBACK_DEVICE_SOFT)):
                log.info('the sound stays on this output: the system does not say when the default changes')
                return
            self._events = oal.ALC_EVENT_PROC(self._event)     # kept: OpenAL holds only its address
            al.event_callback(self._events)
            al.event_control([oal.ALC_EVENT_TYPE_DEFAULT_DEVICE_CHANGED_SOFT], True)
        except (oal.OpenALError, OSError, AttributeError) as exc:
            log.info('the sound stays on this output: %s', exc)
            self._events = None

    def _event(self, event_type, device_type, _device, _length, _message, _user) -> None:
        """On a thread of OpenAL's own: hand the change to the main thread, where the device is used."""
        if event_type != oal.ALC_EVENT_TYPE_DEFAULT_DEVICE_CHANGED_SOFT or device_type != oal.ALC_PLAYBACK_DEVICE_SOFT:
            return
        from ..platform.runloop import RunLoop
        RunLoop.main().call_soon_threadsafe(self._default_changed)

    def _default_changed(self) -> None:
        if self._follow_pending or not self.device:
            return
        self._follow_pending = True
        from ..platform.runloop import RunLoop
        RunLoop.main().call_later(FOLLOW_AFTER, self.move_to_default)

    def move_to_default(self, force: bool = False) -> bool:
        """Move the sound to the default output, if it is not there already.  True if it moved."""
        self._follow_pending = False
        if not self.device:
            return False
        default = self.al.alcGetString(None, oal.ALC_DEFAULT_ALL_DEVICES_SPECIFIER)
        default = default.decode('utf-8', 'replace') if default else ''
        here = self.output_name()
        if default == here and not force:
            return False
        if not self.al.reopen_device(self.device, None, self.attrs):
            log.warning('the default output is now %s, but the sound could not move there from %s', default, here)
            return False
        self.hrtf_status = self.al.get_int(self.device, oal.ALC_HRTF_STATUS_SOFT)
        log.info('the default output changed: sound moved from %s to %s (HRTF status %s)',
                 here, self.output_name(), self.hrtf_status)
        return True

    def close(self) -> None:
        if self._events is not None:
            try:
                self.al.event_control([oal.ALC_EVENT_TYPE_DEFAULT_DEVICE_CHANGED_SOFT], False)
                self.al.event_callback(None)
            except (oal.OpenALError, OSError):
                pass
            self._events = None
        self.al.make_current(None)
        if self.context:
            self.al.alcDestroyContext(self.context)
        if self.device:
            self.al.alcCloseDevice(self.device)
        self.context = self.device = None
