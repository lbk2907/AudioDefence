"""PORT ADDITION (Android build): speech on the phone - Android's own text-to-speech, through the Java
Bridge.  On the phone this module is `platform.speech` (see platform/__init__.py); the desktop's is not loaded.

Where the desktop port speaks through NVDA, Prism or SAPI 5, the phone has one voice - the text-to-speech
engine of the device - and it takes the place of SAPI 5 (and of the Mac's system voice): the Speech tab's
voice, rate, pitch and volume rows drive it, in the same units (rate and pitch -10 to 10, volume 0 to 100).
TalkBack is not used: the game speaks for itself, so TalkBack has to be off while it is played.
"""
from __future__ import annotations

import logging
import re

from .. import localization
from . import host
from .jbridge import bridge

log = logging.getLogger('speech')

OUTPUTS = (('auto', 'Automatic'), ('sapi', 'Android speech'))
SCREEN_READER = 'none'
VOICE_NAME = dict(OUTPUTS)['sapi']
PRISM_NAMES: dict = {}
SAPI_DEFAULTS = {'voice': None, 'rate': None, 'boost': False, 'pitch': 0, 'volume': None}


#: PORT ADDITION: the hints and announcements were written for a keyboard - "Press Enter to play this
#: challenge", "Shift plus Enter for the previous", "Escape to cancel".  On the phone they name the touches
#: that do those things instead, VoiceOver's: a double tap is Enter, a double tap and hold is Shift + Enter,
#: a two-finger scrub is Escape, and swipes are the arrow keys.  Order matters: the longer phrases go first.
PHONE_WORDS = (
    (re.compile(r'\bShift (?:plus |\+ ?)?Enter\b'), 'double tap and hold'),
    (re.compile(r'\bPress Enter\b'), 'Double tap'),
    (re.compile(r'\bpress Enter\b'), 'double tap'),
    (re.compile(r'\bEscape on the keyboard\b'), 'a two-finger scrub'),
    (re.compile(r'(^|[.!?] )Escape\b'), r'\1A two-finger scrub'),
    (re.compile(r'\bEscape\b'), 'a two-finger scrub'),
    (re.compile(r'\b(?:the )?arrow keys\b'), 'swipes'),
)


def phone_words(text: str) -> str:
    for pattern, words in PHONE_WORDS:
        text = pattern.sub(words, text)
    return text


class _NoReaders:
    ctx = None
    reader = None

    def current(self, only=None):
        return None

    def speak(self, text, interrupt, only=None) -> bool:
        return False

    def stop(self) -> None:
        pass


class AndroidVoice:
    """TextToSpeech with the player's voice, rate, pitch and volume: the phone's SAPI 5."""

    def __init__(self):
        self.voice = True                                 # settings asks: is there a voice at all?
        self.thread = None
        self.config = dict(SAPI_DEFAULTS)
        self._voices = None

    def voices(self) -> list:
        if self._voices is None:
            try:
                self._voices = [(str(i), str(n)) for i, n in
                                (line.split('\t', 1) for line in str(bridge().voiceList()).split('\n') if '\t' in line)]
            except Exception:
                log.exception('could not list the voices')
                self._voices = []
        return self._voices

    def configure(self, voice=None, rate=None, boost=False, pitch=0, volume=None) -> None:
        self.config = {'voice': voice, 'rate': rate, 'boost': bool(boost), 'pitch': int(pitch or 0),
                       'volume': volume}
        try:
            bridge().configureSpeech(voice or '', self.rate(), int(pitch or 0), self.volume())
        except Exception:
            log.exception('speech settings not applied')

    def rate(self) -> int:
        r = self.config['rate']
        return 0 if r is None else max(-10, min(10, int(r)))

    def volume(self) -> int:
        v = self.config['volume']
        return 100 if v is None else max(0, min(100, int(v)))

    def boost_supported(self, voice_id=None) -> bool:
        return False

    def speak(self, text: str, interrupt: bool) -> bool:
        try:
            return bool(bridge().speak(str(text), bool(interrupt)))
        except Exception:
            log.exception('speech failed')
            return False

    def stop(self) -> None:
        try:
            bridge().stopSpeech()
        except Exception:
            pass

    def shutdown(self) -> None:
        self.stop()

    def modern_audio_changed(self) -> None:
        pass


class Speech:
    _shared: 'Speech | None' = None

    @classmethod
    def shared(cls) -> 'Speech':
        if cls._shared is None:
            cls._shared = Speech()
        return cls._shared

    def __init__(self):
        self._readers = _NoReaders()
        self._sapi = AndroidVoice()
        self.choice = 'auto'
        self.sapi_config = dict(SAPI_DEFAULTS)
        self.nvda = None

    @property
    def readers(self):
        return self._readers

    @property
    def sapi(self) -> AndroidVoice:
        return self._sapi

    def configure_sapi(self, **config) -> None:
        self.sapi_config = dict(SAPI_DEFAULTS, **config)
        self._sapi.configure(**self.sapi_config)

    def screen_reader_running(self) -> bool:
        return True                                       # the accessible screens are the only ones there are

    def speak(self, text, interrupt: bool = True) -> None:
        if not text:
            return
        text = phone_words(localization.translate(str(text)))
        log.debug('speak: %s', text)
        self._sapi.speak(text, interrupt)

    def speak_automatic(self, text, interrupt: bool = True) -> None:
        self.speak(text, interrupt)

    def automatic_output(self) -> str:
        return 'sapi'

    def can_speak(self, choice: str) -> bool:
        return choice in ('auto', 'sapi')

    def shutdown(self) -> None:
        self._sapi.shutdown()

    def modern_audio_changed(self) -> None:
        pass

    def interrupt_sapi(self) -> None:
        pass                                              # a key press does not cut the phone's voice

    def stop(self) -> None:
        self._sapi.stop()
