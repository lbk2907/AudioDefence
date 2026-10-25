"""PORT ADDITION: Prism's own library, vendor/prism/prism.dll, called directly through ctypes (user request,
2026-10-25).  Windows only: the Mac speaks through VoiceOver and its system voice, and the phone through its
own text-to-speech, and neither loads this.

The game used to reach Prism through the prismatoid package.  This is the same library without the package:
the handful of functions speech.py calls, declared as Prism's own header declares them (include/prism.h of
Prism 0.18.3, the version vendored), behind the names speech.py already used - Context, Backend and a
backend's features - so that speech.py did not have to change its ways.  Three reasons, measured or seen:
importing the package held the interpreter for about 130 ms with the game loaded, most of it asyncio, which
only the package's dispatcher wants, against 4 ms to load the DLL; the DLL now sits in vendor/ beside OpenAL
Soft, where the build and the player can see it, instead of in the package's own folder; and it is the same
prism.dll as the maintainer's AccessDBT, so the two programs share one Prism.

Updating Prism: put the new prism.dll and its LICENSES folder in vendor/prism, and read the new prism.h
against the declarations in `_declare` - PrismConfig above all, which prism_init reads by its layout.
Nothing reports a function whose shape has changed: it is simply called the old way.  The config's own
version is checked at load (PRISM_CONFIG_VERSION, which prism_config_init fills in), so a new config layout
stops Prism from loading - the game then speaks with SAPI 5 and says so in the log - rather than being read
wrongly.
"""
from __future__ import annotations

import ctypes
import logging
import sys

from .. import paths

log = logging.getLogger('speech')

CONFIG_VERSION = 4                                        # PRISM_CONFIG_VERSION in prism.h

# the PrismError codes used here, as prism.h numbers them; ALREADY_INITIALIZED is not a failure when a backend
# is initialised, and the rest are said in Prism's own words (prism_error_string)
OK = 0
ERROR_INVALID_PARAM = 2
ERROR_INTERNAL = 9
ERROR_ALREADY_INITIALIZED = 15
ERROR_INCOMPATIBLE_ABI = 23


class PrismError(Exception):
    """A PrismError code other than PRISM_OK, with Prism's own words for it."""

    def __init__(self, code: int, message: str | None = None):
        self.code = code
        if message is None:
            message = _error_string(code)
        super().__init__(message)


class _Config(ctypes.Structure):
    """PrismConfig, version 4.

    `_room` is not Prism's.  prism_config_init returns the config by value, which on Windows means Prism
    writes it into memory the caller hands over, as large as the caller thinks it is: a later Prism with a
    larger config would write past the end of this one.  The room takes that, and the version is checked
    before the config is used."""
    _fields_ = [('version', ctypes.c_uint8),
                ('registry', ctypes.c_void_p),
                ('availability_callback', ctypes.c_void_p),
                ('availability_userdata', ctypes.c_void_p),
                ('availability_poll_interval_ms', ctypes.c_uint32),
                ('availability_debounce_samples', ctypes.c_uint32),
                ('availability_backoff_max_ms', ctypes.c_uint32),
                ('availability_auto_power_manage', ctypes.c_bool),
                ('availability_baseline_callback', ctypes.c_void_p),
                ('_room', ctypes.c_ubyte * 64)]


_lib = None


def _declare(lib) -> None:
    """The functions used, as prism.h has them."""
    c = ctypes
    for name, restype, argtypes in (
            ('prism_config_init', _Config, []),
            ('prism_init', c.c_void_p, [c.POINTER(_Config)]),
            ('prism_registry_count', c.c_size_t, [c.c_void_p]),
            ('prism_registry_id_at', c.c_uint64, [c.c_void_p, c.c_size_t]),
            ('prism_registry_id', c.c_uint64, [c.c_void_p, c.c_char_p]),
            ('prism_registry_name', c.c_char_p, [c.c_void_p, c.c_uint64]),
            ('prism_registry_create', c.c_void_p, [c.c_void_p, c.c_uint64]),
            ('prism_backend_free', None, [c.c_void_p]),
            ('prism_backend_name', c.c_char_p, [c.c_void_p]),
            ('prism_backend_get_features', c.c_uint64, [c.c_void_p]),
            ('prism_backend_initialize', c.c_int, [c.c_void_p]),
            ('prism_backend_speak', c.c_int, [c.c_void_p, c.c_char_p, c.c_bool]),
            ('prism_backend_braille', c.c_int, [c.c_void_p, c.c_char_p]),
            ('prism_backend_output', c.c_int, [c.c_void_p, c.c_char_p, c.c_bool]),
            ('prism_backend_stop', c.c_int, [c.c_void_p]),
            ('prism_error_string', c.c_char_p, [c.c_int]),
            ('prism_version_string', c.c_char_p, [])):
        function = getattr(lib, name)
        function.restype = restype
        function.argtypes = argtypes


def _load():
    """The library, loaded and declared the first time it is wanted.  OSError when it is not there."""
    global _lib
    if _lib is None:
        lib = ctypes.CDLL(paths.PRISM_DLL)
        _declare(lib)
        _lib = lib
    return _lib


def _error_string(code: int) -> str:
    try:
        text = _lib.prism_error_string(code) if _lib is not None else None
    except Exception:
        text = None
    return text.decode('utf-8', 'replace') if text else 'Prism error %d' % code


def _check(code: int) -> None:
    if code != OK:
        raise PrismError(code)


def _utf8(text: str) -> bytes:
    """A line as Prism takes it.  Empty, or with a NUL in it, it is refused here, as prismatoid refused it:
    C would end the string at the NUL and speak half of it."""
    if not text or '\x00' in text:
        raise PrismError(ERROR_INVALID_PARAM, 'a line for Prism must not be empty or hold a NUL')
    return text.encode('utf-8', 'replace')


class Features:
    """The feature bits speech.py asks about (PrismBackendFeature in prism.h)."""
    __slots__ = ('bits',)

    def __init__(self, bits: int):
        self.bits = bits

    def _has(self, bit: int) -> bool:
        return bool(self.bits & (1 << bit))

    is_supported_at_runtime = property(lambda self: self._has(0))
    supports_speak = property(lambda self: self._has(2))
    supports_braille = property(lambda self: self._has(4))
    supports_output = property(lambda self: self._has(5))
    supports_is_speaking = property(lambda self: self._has(6))
    supports_stop = property(lambda self: self._has(7))


class Backend:
    """One of Prism's backends - a screen reader, here - made and initialised, and freed when let go of."""

    def __init__(self, raw):
        self._raw = raw
        code = _lib.prism_backend_initialize(raw)
        if code not in (OK, ERROR_ALREADY_INITIALIZED):
            _lib.prism_backend_free(raw)
            self._raw = None
            raise PrismError(code)

    def __del__(self):
        if self._raw and not sys.is_finalizing():
            _lib.prism_backend_free(self._raw)
        self._raw = None

    @property
    def name(self) -> str:
        return _lib.prism_backend_name(self._raw).decode('utf-8', 'replace')

    @property
    def features(self) -> Features:
        return Features(_lib.prism_backend_get_features(self._raw))

    def speak(self, text: str, interrupt: bool = False) -> None:
        _check(_lib.prism_backend_speak(self._raw, _utf8(text), bool(interrupt)))

    def braille(self, text: str) -> None:
        _check(_lib.prism_backend_braille(self._raw, _utf8(text)))

    def output(self, text: str, interrupt: bool = False) -> None:
        """Spoken, and shown on a braille display where the screen reader has one."""
        _check(_lib.prism_backend_output(self._raw, _utf8(text), bool(interrupt)))

    def stop(self) -> None:
        _check(_lib.prism_backend_stop(self._raw))


class Context:
    """Prism, started.  One is made for the game (speech._prism) and kept to the end."""

    def __init__(self):
        lib = _load()
        config = lib.prism_config_init()
        if config.version != CONFIG_VERSION:
            raise PrismError(ERROR_INCOMPATIBLE_ABI,
                             'prism.dll has config version %d, and this game was written for %d: read its '
                             'prism.h against platform/prismdll.py' % (config.version, CONFIG_VERSION))
        self._ctx = lib.prism_init(ctypes.byref(config))
        if not self._ctx:
            raise PrismError(ERROR_INTERNAL, 'Prism could not be started')
        log.info('Prism %s, from %s', self.version, paths.PRISM_DLL)

    @property
    def version(self) -> str:
        return _lib.prism_version_string().decode('ascii', 'replace')

    @property
    def backends_count(self) -> int:
        return _lib.prism_registry_count(self._ctx)

    def id_of(self, index_or_name) -> int:
        """A backend's id, from its place in Prism's list or from its name ('NVDA')."""
        if isinstance(index_or_name, str):
            bid = _lib.prism_registry_id(self._ctx, index_or_name.encode('utf-8'))
        else:
            bid = _lib.prism_registry_id_at(self._ctx, index_or_name)
        if not bid:
            raise KeyError('no Prism backend %r' % (index_or_name,))
        return bid

    def name_of(self, bid: int) -> str:
        name = _lib.prism_registry_name(self._ctx, bid)
        if name is None:
            raise KeyError('no Prism backend with id %#x' % bid)
        return name.decode('utf-8', 'replace')

    def create(self, bid: int) -> Backend:
        raw = _lib.prism_registry_create(self._ctx, bid)
        if not raw:
            raise ValueError('Prism could not make backend %#x' % bid)
        return Backend(raw)
