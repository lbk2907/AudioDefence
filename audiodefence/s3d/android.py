"""PORT ADDITION (Android build): the OpenAL the engine talks to, answered by the Java mixer.

engine.py was written against OpenAL Soft through ctypes.  Android has no OpenAL Soft to hand, so the same
calls go to ``com.audiodefence.audio.MiniAl`` instead - a small mixer with the game's own HRTF, the same
Freeverb and the same per-ear filters - through the names OpenAL gives them.  Two contexts, as on the
desktop: 0 is the output, 1 is the reverb bus (its render plus the Stereoverb reaches the output).
"""
from __future__ import annotations

import logging
import time

from ..platform.jbridge import bridge
from . import openal as oal

log = logging.getLogger('s3d.android')

PARAM_DIRECT_HF = 0x30000
KIND = {'mono': 0, 'stereo': 1, 'center': 2}


class _Snapshot:
    """One call to Java tells the state and play position of every source; the engine asks for them per
    sound, ten times a second each, and a call per question was most of the cost."""
    t = 0.0
    data: dict = {}
    MAX_AGE = 0.004


class Device:
    """Stands where the OpenAL device stood: the mixer lives in the Java Bridge and runs from the app's start."""

    def __init__(self):
        self.br = bridge()
        self.al = self.br.al
        self.device = True
        self.context = 0
        self.hrtf_found = True
        self.hrtf_status = 1

    def close(self) -> None:
        pass


class _Reverb:
    def __init__(self, al):
        self._al = al
        self.active = True

    def set_room_size(self, v) -> None:
        self._al.reverbRoomSize(float(v))

    def set_dampening(self, v) -> None:
        self._al.reverbDampening(float(v))

    def set_wet_level(self, v) -> None:
        self._al.reverbWet(float(v))

    def set_dry_level(self, v) -> None:
        self._al.reverbDry(float(v))

    def set_active(self, on) -> None:
        self.active = bool(on)
        self._al.reverbActive(bool(on))


class ReverbBus:
    def __init__(self, device):
        self.device = device
        self.context = 1
        self.available = True
        self.reverb = _Reverb(device.al)
        # -[S3DEngine init]: roomSize 2.2, dampening 2, wet 0, dry 0, active
        self.reverb.set_room_size(2.2)
        self.reverb.set_dampening(2.0)
        self.reverb.set_wet_level(0.0)
        self.reverb.set_dry_level(0.0)
        self.reverb.set_active(True)

    def close(self) -> None:
        pass


class ContextAL:
    """The calls engine.py makes, for one context (0 output, 1 reverb bus)."""

    _filters: dict = {}
    _filter_src: dict = {}
    _next_filter = 1

    def __init__(self, al, context):
        self.al = al
        self.ctx = int(context)

    # --- errors / models: nothing to report --------------------------------------------------------
    def alDistanceModel(self, model) -> None:
        pass

    def alGetError(self) -> int:
        return 0

    def check(self, where) -> None:
        pass

    # --- generate / delete -------------------------------------------------------------------------
    def gen(self, name: str) -> int:
        if name == 'alGenBuffers':
            return int(self.al.genBuffer())
        if name == 'alGenSources':
            return int(self.al.genSource(self.ctx))
        if name == 'alGenFilters':
            fid = ContextAL._next_filter
            ContextAL._next_filter += 1
            ContextAL._filters[fid] = {}
            return fid
        raise ValueError(name)

    def delete(self, name: str, ident: int) -> None:
        _Snapshot.data.pop((self.ctx, ident), None)
        if name == 'alDeleteBuffers':
            self.al.deleteBuffer(int(ident))
        elif name == 'alDeleteSources':
            self.al.deleteSource(self.ctx, int(ident))
        elif name == 'alDeleteFilters':
            ContextAL._filters.pop(ident, None)
            ContextAL._filter_src.pop(ident, None)

    def buffer_from_sound(self, buf: int, sound, kind: str) -> None:
        self.al.bufferFromSound(int(buf), int(sound.handle), KIND[kind])

    # --- filters (the direct low-pass: air absorption) ---------------------------------------------
    def filteri(self, f, p, v) -> None:
        pass

    def filterf(self, f, p, v) -> None:
        ContextAL._filters.setdefault(f, {})[p] = float(v)
        src = ContextAL._filter_src.get(f)
        if src is not None and p == oal.AL_LOWPASS_GAINHF:
            self.al.sourceF(self.ctx, src, PARAM_DIRECT_HF, float(v))

    # --- sources -----------------------------------------------------------------------------------
    def alSourcei(self, src, param, v) -> None:
        if param == oal.AL_DIRECT_FILTER:
            if v:
                ContextAL._filter_src[v] = src
                hf = ContextAL._filters.get(v, {}).get(oal.AL_LOWPASS_GAINHF, 1.0)
            else:
                hf = 1.0
            self.al.sourceF(self.ctx, src, PARAM_DIRECT_HF, float(hf))
            return
        if param == oal.AL_BUFFER:
            _Snapshot.data.pop((self.ctx, src), None)
        self.al.sourceI(self.ctx, src, param, int(v))

    def alSourcef(self, src, param, v) -> None:
        if param == oal.AL_SEC_OFFSET:
            _Snapshot.data.pop((self.ctx, src), None)
        self.al.sourceF(self.ctx, src, param, float(v))

    def alSource3f(self, src, param, x, y, z) -> None:
        self.al.source3F(self.ctx, src, param, float(x), float(y), float(z))

    def alSourcePlay(self, src) -> None:
        _Snapshot.data.pop((self.ctx, src), None)
        self.al.play(self.ctx, src)

    def alSourceStop(self, src) -> None:
        _Snapshot.data.pop((self.ctx, src), None)
        self.al.stop(self.ctx, src)

    def alSourcePause(self, src) -> None:
        _Snapshot.data.pop((self.ctx, src), None)
        self.al.pause(self.ctx, src)

    def alSourceRewind(self, src) -> None:
        _Snapshot.data.pop((self.ctx, src), None)
        self.al.rewind(self.ctx, src)

    def _lookup(self, src):
        now = time.perf_counter()
        if now - _Snapshot.t > _Snapshot.MAX_AGE:
            arr = list(self.al.snapshot())
            _Snapshot.data = {(int(arr[i]), int(arr[i + 1])): (int(arr[i + 2]), float(arr[i + 3]))
                              for i in range(0, len(arr) - 3, 4)}
            _Snapshot.t = now
        return _Snapshot.data.get((self.ctx, src))

    # engine.py passes these an OpenAL out-parameter as `ctypes.byref(value)`, as OpenAL Soft wants; the
    # value itself is what is filled in here (`_obj` is what a byref points at).
    def alGetSourcei(self, src, param, out) -> None:
        out = getattr(out, '_obj', out)
        if param == oal.AL_SOURCE_STATE:
            hit = self._lookup(src)
            out.value = hit[0] if hit is not None else int(self.al.getSourceI(self.ctx, src, param))
        else:
            out.value = int(self.al.getSourceI(self.ctx, src, param))

    def alGetSourcef(self, src, param, out) -> None:
        out = getattr(out, '_obj', out)
        if param == oal.AL_SEC_OFFSET:
            hit = self._lookup(src)
            out.value = hit[1] if hit is not None else float(self.al.getSourceF(self.ctx, src, param))
        else:
            out.value = float(self.al.getSourceF(self.ctx, src, param))

    def alListenerf(self, param, v) -> None:
        if param == oal.AL_GAIN:
            self.al.setListenerGain(self.ctx, float(v))
