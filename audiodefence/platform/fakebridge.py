"""A stand-in for the Java Bridge, for running the Android build's Python on a PC (testing only).

Nothing is heard: sources 'play' by the clock so the game's timing (end of a sound, its offset) behaves as on
the phone, files are measured with ffprobe, and what the game says is collected in `spoken`.
"""
from __future__ import annotations

import subprocess
import time

AL_PLAYING, AL_PAUSED, AL_STOPPED, AL_INITIAL = 0x1012, 0x1013, 0x1014, 0x1011
AL_SOURCE_STATE, AL_LOOPING, AL_BUFFER, AL_SEC_OFFSET, AL_PITCH = 0x1010, 0x1007, 0x1009, 0x1024, 0x1003


class _Src:
    def __init__(self):
        self.buf = 0
        self.state = AL_INITIAL
        self.start = 0.0
        self.base = 0.0
        self.loop = False
        self.pitch = 1.0
        self.pos = (0.0, 0.0, 0.0)
        self.gain = 1.0


class FakeAl:
    def __init__(self, bridge):
        self.b = bridge
        self.n = 1
        self.buffers = {}
        self.src = {}
        self.calls = 0

    def genBuffer(self):
        self.n += 1
        self.buffers[self.n] = None
        return self.n

    def deleteBuffer(self, i):
        self.buffers.pop(i, None)

    def bufferFromSound(self, buf, handle, kind):
        self.buffers[buf] = self.b.sounds[handle]

    def genSource(self, ctx):
        self.n += 1
        self.src[(ctx, self.n)] = _Src()
        return self.n

    def deleteSource(self, ctx, i):
        self.src.pop((ctx, i), None)

    def _dur(self, s):
        snd = self.buffers.get(s.buf)
        return snd[0] / float(snd[1]) if snd else 0.0

    def _tick(self, s):
        if s.state == AL_PLAYING:
            d = self._dur(s)
            el = s.base + (time.perf_counter() - s.start) * s.pitch
            if d > 0 and el >= d:
                if s.loop:
                    s.base = el % d
                    s.start = time.perf_counter()
                else:
                    s.state = AL_STOPPED
                    s.base = 0.0

    def sourceI(self, ctx, i, p, v):
        s = self.src.get((ctx, i))
        if not s:
            return
        if p == AL_BUFFER:
            s.buf = v
            s.state = AL_INITIAL
            s.base = 0.0
        elif p == AL_LOOPING:
            s.loop = bool(v)

    def sourceF(self, ctx, i, p, v):
        s = self.src.get((ctx, i))
        if not s:
            return
        if p == AL_PITCH:
            s.pitch = v or 1.0
        elif p == AL_SEC_OFFSET:
            s.base = v
            s.start = time.perf_counter()
        elif p == 0x100A:
            s.gain = v

    def source3F(self, ctx, i, p, x, y, z):
        s = self.src.get((ctx, i))
        if s:
            s.pos = (x, y, z)

    def getSourceI(self, ctx, i, p):
        s = self.src.get((ctx, i))
        if not s:
            return AL_INITIAL
        self.calls += 1
        self._tick(s)
        return s.state if p == AL_SOURCE_STATE else (1 if s.loop else 0)

    def getSourceF(self, ctx, i, p):
        s = self.src.get((ctx, i))
        if not s:
            return 0.0
        self._tick(s)
        if s.state == AL_PLAYING:
            return s.base + (time.perf_counter() - s.start) * s.pitch
        return s.base

    def play(self, ctx, i):
        s = self.src.get((ctx, i))
        if s and s.buf in self.buffers and self.buffers[s.buf]:
            if s.state in (AL_PLAYING, AL_STOPPED, AL_INITIAL):
                if s.state != AL_INITIAL or s.base == 0.0:
                    pass
            s.state = AL_PLAYING
            s.start = time.perf_counter()

    def pause(self, ctx, i):
        s = self.src.get((ctx, i))
        if s and s.state == AL_PLAYING:
            s.base = self.getSourceF(ctx, i, AL_SEC_OFFSET)
            s.state = AL_PAUSED

    def stop(self, ctx, i):
        s = self.src.get((ctx, i))
        if s:
            s.state = AL_STOPPED
            s.base = 0.0

    def rewind(self, ctx, i):
        s = self.src.get((ctx, i))
        if s:
            s.state = AL_INITIAL
            s.base = 0.0

    def setListenerGain(self, ctx, g):
        pass

    def reverbRoomSize(self, v): pass
    def reverbDampening(self, v): pass
    def reverbWet(self, v): pass
    def reverbDry(self, v): pass
    def reverbActive(self, v): pass

    def snapshot(self):
        out = []
        for (ctx, i), s in self.src.items():
            self._tick(s)
            off = s.base + ((time.perf_counter() - s.start) * s.pitch if s.state == AL_PLAYING else 0.0)
            out += [float(ctx), float(i), float(s.state), float(off)]
        return out


class FakeBridge:
    def __init__(self):
        self.al = FakeAl(self)
        self.sounds = {}
        self.by_path = {}
        self.spoken = []
        self.events = []
        self.quit_at = None
        self.started = time.perf_counter()

    # --- decoding -------------------------------------------------------------------------------------
    def decode(self, path):
        if path in self.by_path:
            h = self.by_path[path]
            f, r, c = self.sounds[h]
            return [h, f, c, r]
        out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries',
                              'stream=sample_rate,channels,duration', '-of', 'csv=p=0', path],
                             capture_output=True, text=True)
        try:
            rate, ch, dur = out.stdout.strip().split(',')[:3]
            frames = int(float(dur) * int(rate))
            h = len(self.sounds) + 1
            self.sounds[h] = (frames, int(rate), int(ch))
            self.by_path[path] = h
            return [h, frames, int(ch), int(rate)]
        except Exception:
            return [-1, 0, 0, 0]

    def leadIn(self, handle, floor, most):
        return 0.0

    # --- speech ---------------------------------------------------------------------------------------
    def speak(self, text, interrupt):
        self.spoken.append(text)
        return True

    def stopSpeech(self):
        pass

    def voiceList(self):
        return 'v1\tFake voice'

    def configureSpeech(self, voice, rate, pitch, volume):
        pass

    # --- input / lifecycle ----------------------------------------------------------------------------
    def pollEvents(self):
        ev, self.events = self.events, []
        flat = []
        for e in ev:
            flat += [float(v) for v in e]
        return flat

    def shouldQuit(self):
        return self.quit_at is not None and time.perf_counter() - self.started > self.quit_at

    def screenWidthDp(self):
        return 800.0

    def screenHeightDp(self):
        return 360.0

    def takeYaw(self):
        return 0.0

    def tiltAngle(self):
        return 0.0

    def setShakeSensitivity(self, level):
        self.shake_level = level

    def takeShake(self):
        return False

    def gameEnded(self):
        pass
