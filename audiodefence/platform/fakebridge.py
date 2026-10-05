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
        self.speech_config = None
        self.speech_ready = True
        self.starts_at_once = True
        self.broken = set()
        self.engine_asked = ''
        self.engine_starting = ''
        self.engine_in_use = ''
        self.engines_asked = []
        self.spoken_second = []                           # the second speech, as `spoken` is the first's
        self.second_config = None
        self.second_ready = False
        self.second_begun = False
        self.second_engine_asked = ''
        self.second_starting = ''
        self.second_engine_in_use = ''
        self.second_engines_asked = []
        self.events = []
        self.quit_at = None
        self.started = time.perf_counter()
        # updating: what the "network" holds - {url: (status, text)} and {url: bytes} - and Android's answers
        self.pages = {}
        self.files = {}
        self.fetched = []
        self.progress = [0, 0]
        self.cancelled = False
        self.install_allowed = True
        self.foreground = True
        self.settings_opened = 0
        self.handed = []
        self.install_state = ''
        # backups: the AudioDefence folder in Documents (a folder on the PC, set by a test), whether the game
        # can still see its own backup there (False: installed again since), the Android version, and what
        # the file picker answers - a file's path, or None for Cancel
        self.documents = None
        self.own_backup = True
        self.sdk = 36
        self.picker_answer = None
        self.pickers = []
        self.document_state = ''

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
    # Two engines.  An engine starts as soon as it is asked for, unless a test sets `starts_at_once` False and
    # calls finish_start(); one in `broken` falls back to the phone's default, as one that is not installed does.
    ENGINES = {'com.example.fake': 'Fake speech', 'com.example.other': 'Other speech'}

    def speak(self, text, interrupt):
        self.spoken.append(text)
        return True

    def stopSpeech(self):
        pass

    def configureSpeech(self, rate, pitch, volume):
        self.speech_config = (rate, pitch, volume)

    def speechReady(self):
        return self.speech_ready

    def engineList(self):
        return ''.join('%s\t%s\n' % (p, n) for p, n in sorted(self.ENGINES.items(), key=lambda e: e[1]))

    def setSpeechEngine(self, engine):
        self.engines_asked.append(engine)
        if engine == self.engine_asked:
            return
        self.engine_asked = engine
        self.speech_ready = False
        self.engine_starting = engine
        if self.starts_at_once:
            self.finish_start()

    def finish_start(self):
        engine = self.engine_starting
        if engine and (engine not in self.ENGINES or engine in self.broken):
            if self.engine_asked == engine:
                self.engine_asked = ''
            engine = ''
        self.engine_in_use = engine
        self.speech_ready = True

    def speechEngine(self):
        return self.engine_in_use

    # The second speech (Settings > Speech > Use second speech): a TextToSpeech of its own, made by its first
    # line, as the Bridge makes it.  `second_begun` says whether it has been.
    def speakSecond(self, text, interrupt):
        if not self.second_begun:
            self.second_begun = True
            self.second_starting = self.second_engine_asked
            if self.starts_at_once:
                self.finish_second_start()
        self.spoken_second.append(text)
        return True

    def stopSecondSpeech(self):
        pass

    def configureSecondSpeech(self, rate, pitch, volume):
        self.second_config = (rate, pitch, volume)

    def secondSpeechReady(self):
        return self.second_ready

    def setSecondSpeechEngine(self, engine):
        self.second_engines_asked.append(engine)
        if engine == self.second_engine_asked:
            return
        self.second_engine_asked = engine
        if not self.second_begun:
            return
        self.second_ready = False
        self.second_starting = engine
        if self.starts_at_once:
            self.finish_second_start()

    def finish_second_start(self):
        engine = self.second_starting
        if engine and (engine not in self.ENGINES or engine in self.broken):
            if self.second_engine_asked == engine:
                self.second_engine_asked = ''
            engine = ''
        self.second_engine_in_use = engine
        self.second_ready = True

    def secondSpeechEngine(self):
        return self.second_engine_in_use

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

    # --- updating -------------------------------------------------------------------------------------
    def fetchText(self, url, accept, user_agent, timeout_ms):
        self.fetched.append(url)
        status, text = self.pages.get(url, (0, 'no network in the fake bridge'))
        return '%d\n%s' % (status, text)

    def download(self, url, path, user_agent, timeout_ms):
        if url not in self.files:
            return 'http 404'
        data = self.files[url]
        self.progress = [0, len(data)]
        self.cancelled = False
        with open(path, 'wb') as fh:
            for at in range(0, len(data), 4096):
                if self.cancelled:
                    return 'cancelled'
                fh.write(data[at:at + 4096])
                self.progress[0] = min(len(data), at + 4096)
                time.sleep(0.01)
        return ''

    def cancelDownload(self):
        self.cancelled = True

    def downloadProgress(self):
        return list(self.progress)

    def canInstallPackages(self):
        return self.install_allowed

    def openInstallSettings(self):
        self.settings_opened += 1
        self.foreground = False
        return True

    def inForeground(self):
        return self.foreground

    def installApk(self, path):
        self.handed.append(path)
        self.install_state = 'confirm'

    def installState(self):
        return self.install_state

    # --- backups --------------------------------------------------------------------------------------
    def _backup(self):
        import os
        return os.path.join(self.documents, 'AudioDefence backup.zip')

    def exportBackup(self, source):
        import shutil
        if self.sdk < 29:
            return 'picker'
        shutil.copyfile(source, self._backup())
        self.own_backup = True
        return 'ok\nAudioDefence backup.zip'

    def findBackup(self, to):
        import os
        import shutil
        if self.sdk < 29:
            return 'picker'
        if not self.own_backup or not os.path.exists(self._backup()):
            return 'none'
        shutil.copyfile(self._backup(), to)
        return 'ok'

    def pickFileToOpen(self, to):
        import shutil
        self.pickers.append(('open', to))
        if self.picker_answer is None:
            self.document_state = 'cancelled'
        else:
            shutil.copyfile(self.picker_answer, to)
            self.document_state = 'done'
        return True

    def pickFileToCreate(self, name, source):
        import shutil
        self.pickers.append(('create', name))
        if self.picker_answer is None:
            self.document_state = 'cancelled'
        else:
            shutil.copyfile(source, self.picker_answer)
            self.document_state = 'done'
        return True

    def documentState(self):
        return self.document_state
