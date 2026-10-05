"""The original reverb: csl::Stereoverb (two csl::Freeverb) and the port's reverb bus that feeds it.

Original graph (-[S3DEngine init] 0x1000faa60 and -[S3DSound setupSpatialized] 0x100103b64):

    sound with sendToReverb: spatializer -> gainControl -> FanOut -+-> dryMixer  (x dryGain) --> masterMixer
                                                                  +-> wetMixer  (x wetGain) -> Stereoverb --^
    other sounds:            ... -> gainControl -----------------------------------------------> masterMixer

csl::Mixer::nextBuffer (0x1000ee104) only sums its inputs times their scales.  The Stereoverb
(ctor sub_1000ed088) splits its stereo input, runs one Freeverb per channel and joins them again
(csl::Splitter 0x1000ea728 hands out channel 0 then 1, csl::Joiner 0x1000eab98 pulls left then right).

csl::Freeverb (init sub_1000ec864, nextBuffer 0x1000ece8c), per channel and per sample:

    in = x * 0.015; out = 0
    6 combs (1116 1188 1277 1356 1422 1491 samples):
        y = buf[i]; store = y * (1 - damp) + store * damp; buf[i] = in + store * room; out += y
    3 allpasses (556 441 341 samples):
        b = buf[i]; buf[i] = out + b * 0.5; out = b - out
    output = out * wet + x * dry

Setters: room = size * 0.28 + 0.3 (sub_1000ed4e8), damp = d * 0.01 * 0.4 (sub_1000ed574), wet = volume
(sub_1000ed600), dry (sub_1000ed674), active flag (sub_1000ed444).  -[S3DEngine init] sets size 2.2,
dampening 2, wet 0, dry 0, active YES; the ObjC setters then apply 1.5 / 1 / 50.

PORT: OpenAL Soft cannot run this effect, so sounds that send to the reverb play on a second OpenAL Soft
device (a loopback device with the same HRTF - the one Settings -> Sound -> 3D sound chose, `use_hrtf`): its
stereo render is the FanOut signal.  A callback buffer
source on the output device pulls that render, adds the Stereoverb output and plays the sum with direct
channels - exactly dryMixer + Stereoverb.  Every sound the game sends to the reverb uses dryGain 1 and
wetGain 1 (-[ADEnemy setReverbAndWetBalanceOnSound:] 0x100063a48); other values are not supported.

The Freeverb here is block-vectorised (blocks of at most 256 samples, shorter than every delay line) and
runs in double precision.  The comb's one-pole damping filter is evaluated as its impulse response
truncated after 40 taps (damp <= 0.4, so the dropped part is below 1e-15).
"""
from __future__ import annotations

import ctypes
import logging
import threading

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from ..platform.cfloat import f32
from . import openal as oal

log = logging.getLogger('s3d.reverb')

COMB_TUNINGS = (1116, 1188, 1277, 1356, 1422, 1491)     # first 6 entries of the table at 0x100182010
ALLPASS_TUNINGS = (556, 441, 341)                        # first 3 entries of the table at 0x100182030
FIXED_GAIN = 0.015                                       # Freeverb +0xcc
ALLPASS_FEEDBACK = 0.5
BLOCK = 256                                              # CSL's buffer size; below the shortest delay (341)
TAPS = 40
CHANNELS = 2


class _Delay:
    __slots__ = ('buf', 'size', 'index', 'history')

    def __init__(self, size: int, history: int = 0):
        self.size = size
        self.buf = np.zeros((CHANNELS, size))
        self.index = 0
        self.history = np.zeros((CHANNELS, history)) if history else None


class Stereoverb:
    """csl::Stereoverb with its two csl::Freeverb (identical tunings, one per channel)."""

    def __init__(self):
        # csl::Freeverb init sub_1000ec864
        self.room = f32(0.37)
        self.wet = 0.5
        self.dry = 0.5
        self._set_damp(f32(0.04))
        self.active = False
        self._combs = [_Delay(n, TAPS - 1) for n in COMB_TUNINGS]
        self._allpasses = [_Delay(n) for n in ALLPASS_TUNINGS]

    # --- setters ---------------------------------------------------------------------------------
    def set_room_size(self, size: float) -> None:          # sub_1000ed4e8
        self.room = f32(f32(f32(size) * f32(0.28)) + f32(0.3))

    def set_dampening(self, dampening: float) -> None:     # sub_1000ed574
        self._set_damp(f32(f32(f32(dampening) * f32(0.01)) * f32(0.4)))

    def set_wet_level(self, level: float) -> None:         # sub_1000ed600
        self.wet = f32(level)

    def set_dry_level(self, level: float) -> None:         # sub_1000ed674
        self.dry = f32(level)

    def set_active(self, flag: bool) -> None:              # sub_1000ed444
        self.active = bool(flag)

    def _set_damp(self, damp: float) -> None:
        damp2 = f32(1.0 - damp)
        powers = np.array([damp ** k for k in range(TAPS - 1, -1, -1)])   # oldest sample first
        self._damp = (damp, damp2, powers * damp2)          # swapped in one assignment for the audio thread

    # --- processing ------------------------------------------------------------------------------
    def process(self, x: np.ndarray) -> np.ndarray:
        """x: (2, frames) float64 input.  Returns the Stereoverb output (wet * reverb + dry * x)."""
        out = np.empty_like(x)
        for start in range(0, x.shape[1], BLOCK):
            block = x[:, start:start + BLOCK]
            out[:, start:start + block.shape[1]] = self._block(block)
        return out

    def _block(self, x: np.ndarray) -> np.ndarray:
        n = x.shape[1]
        room = self.room
        _damp, _damp2, kernel = self._damp
        wet, dry = self.wet, self.dry
        inp = x * FIXED_GAIN
        acc = np.zeros_like(x)
        for c in self._combs:
            y = _read(c, n)
            ext = np.concatenate((c.history, y), axis=1)
            store = sliding_window_view(ext, TAPS, axis=1) @ kernel
            _write(c, n, inp + store * room)
            c.history = ext[:, n:]
            acc += y
        for a in self._allpasses:
            b = _read(a, n)
            _write(a, n, acc + b * ALLPASS_FEEDBACK)
            acc = b - acc
        return acc * wet + x * dry


def _read(d: _Delay, n: int) -> np.ndarray:
    """The n samples written d.size samples ago (n <= d.size)."""
    i, end = d.index, d.index + n
    if end <= d.size:
        return d.buf[:, i:end].copy()
    return np.concatenate((d.buf[:, i:], d.buf[:, :end - d.size]), axis=1)


def _write(d: _Delay, n: int, values: np.ndarray) -> None:
    i, end = d.index, d.index + n
    if end <= d.size:
        d.buf[:, i:end] = values
    else:
        k = d.size - i
        d.buf[:, i:] = values[:, :k]
        d.buf[:, :end - d.size] = values[:, k:]
    d.index = end % d.size


class ReverbBus:
    """The second OpenAL Soft device carrying the reverb-sending sounds, and the output source that mixes
    its render with the Stereoverb into the output device."""

    def __init__(self, device):
        self.device = device
        self.al = device.al
        self.reverb = Stereoverb()
        self.context = None
        self.bus_device = None
        self._source = 0
        self._buffer = 0
        self._callback = None
        self._scratch = np.zeros(BLOCK * 2, dtype=np.float32)
        self._failed = False
        #: held while the bus renders (on OpenAL Soft's mixer thread) and while it is reset with another HRTF
        #: (on the main one), so the two never meet
        self._lock = threading.Lock()
        self.attrs = []
        self._open()

    @property
    def available(self) -> bool:
        return self.context is not None

    def _open(self) -> None:
        al = self.al
        if not al.alIsExtensionPresent(b'AL_SOFT_callback_buffer'):
            log.error('AL_SOFT_callback_buffer missing: sounds play without the reverb')
            return
        from . import sound3d
        from .device import SAMPLE_RATE
        # PORT ADDITION (2026-10-05): the HRTF the output device was opened with, the game's own by default
        hrtf = sound3d.openal_name(getattr(self.device, 'sound_3d', sound3d.GAME))
        dev = al.loopback_open()
        if not dev:
            log.error('cannot open the reverb bus device: sounds play without the reverb')
            return
        attrs = [oal.ALC_FORMAT_CHANNELS_SOFT, oal.ALC_STEREO_SOFT, oal.ALC_FORMAT_TYPE_SOFT, oal.ALC_FLOAT_SOFT,
                 oal.ALC_FREQUENCY, SAMPLE_RATE, oal.ALC_HRTF_SOFT, oal.ALC_TRUE,
                 oal.ALC_OUTPUT_LIMITER_SOFT, oal.ALC_FALSE, oal.ALC_MONO_SOURCES, 255, oal.ALC_STEREO_SOURCES, 64]
        ctx = al.alcCreateContext(dev, oal.attr_list(dict(zip(attrs[::2], attrs[1::2]))))
        if not ctx:
            al.alcCloseDevice(dev)
            log.error('cannot create the reverb bus context: sounds play without the reverb')
            return
        names = al.hrtf_names(dev)
        if hrtf in names:
            al.reset_device(dev, attrs + [oal.ALC_HRTF_ID_SOFT, names.index(hrtf)])
        status = al.get_int(dev, oal.ALC_HRTF_STATUS_SOFT)
        if hrtf not in names or status != 1:
            log.error('reverb bus: HRTF %s not in use (status %s)', hrtf, status)
        self.bus_device, self.context, self.attrs = dev, ctx, attrs
        al.make_current(ctx)
        al.alDistanceModel(0)
        # the output source lives on the output device
        al.make_current(self.device.context)
        self._callback = oal.BUFFER_CALLBACK(self._render)
        self._buffer = al.gen('alGenBuffers')
        al.buffer_callback(self._buffer, oal.AL_FORMAT_STEREO_FLOAT32, SAMPLE_RATE, self._callback)
        self._source = al.gen('alGenSources')
        al.alSourcei(self._source, oal.AL_BUFFER, self._buffer)
        al.alSourcei(self._source, oal.AL_SOURCE_RELATIVE, 1)
        al.alSourcef(self._source, oal.AL_ROLLOFF_FACTOR, 0.0)
        al.alSourcei(self._source, oal.AL_DIRECT_CHANNELS_SOFT, 1)
        al.check('reverb bus source')
        # -[S3DEngine init]: roomSize 2.2, dampening 2, wet 0, dry 0, active
        self.reverb.set_room_size(2.2)
        self.reverb.set_dampening(2.0)
        self.reverb.set_wet_level(0.0)
        self.reverb.set_dry_level(0.0)
        self.reverb.set_active(True)
        al.alSourcePlay(self._source)
        al.check('reverb bus play')

    def use_hrtf(self, name: str) -> bool:
        """PORT ADDITION (user report, 2026-10-05): the bus hears with the HRTF OpenAL Soft lists as `name`, as
        the output device does (S3DEngine.use_3d_sound); reset while it is not rendering.  False where it is
        not listed or does not load, the one before kept."""
        if self.bus_device is None:
            return False
        al = self.al
        names = al.hrtf_names(self.bus_device)
        if name not in names:
            return False
        with self._lock:
            ok = (al.reset_device(self.bus_device, self.attrs + [oal.ALC_HRTF_ID_SOFT, names.index(name)])
                  and al.get_int(self.bus_device, oal.ALC_HRTF_STATUS_SOFT) == 1)
            current = al.alcGetString(self.bus_device, oal.ALC_HRTF_SPECIFIER_SOFT)
            if not ok or (current or b'').decode('utf-8', 'replace') != name:
                log.warning('reverb bus: %s did not load', name)
                return False
        return True

    def _render(self, _userptr, sampledata, numbytes) -> int:
        """ALBUFFERCALLBACKTYPESOFT, on OpenAL Soft's mixer thread: dryMixer + Stereoverb."""
        frames = numbytes // 8
        with self._lock:
            return self._render_locked(sampledata, frames)

    def _render_locked(self, sampledata, frames) -> int:
        try:
            out = np.ctypeslib.as_array((ctypes.c_float * (frames * 2)).from_address(sampledata))
            scratch = self._scratch
            for start in range(0, frames, BLOCK):
                n = min(BLOCK, frames - start)
                self.al.render_into(self.bus_device, scratch.ctypes.data, n)
                dry = scratch[:n * 2].reshape(n, 2).T.astype(np.float64)
                mix = dry + self.reverb.process(dry) if self.reverb.active else dry
                out[start * 2:(start + n) * 2] = mix.T.reshape(-1)
        except Exception:                                   # never let an exception reach the mixer thread
            if not self._failed:
                self._failed = True
                log.exception('reverb bus render failed')
            ctypes.memset(sampledata, 0, frames * 8)
        return frames * 8

    def close(self) -> None:
        al = self.al
        if self._source:
            al.make_current(self.device.context)
            al.alSourceStop(self._source)
            al.alSourcei(self._source, oal.AL_BUFFER, 0)
            al.delete('alDeleteSources', self._source)
            al.delete('alDeleteBuffers', self._buffer)
            self._source = self._buffer = 0
        if self.context:
            al.make_current(None)
            al.alcDestroyContext(self.context)
            al.alcCloseDevice(self.bus_device)
            self.context = self.bus_device = None
