package com.audiodefence.audio;

import java.util.HashMap;
import java.util.Map;

/**
 * The small part of OpenAL that the game's S3D engine uses, rendered on the phone.
 *
 * The desktop port mixes with OpenAL Soft; Android has no OpenAL Soft to hand, so this class does the same
 * job with the same calls (the Python side, audiodefence/s3d/openal.py, exposes them under their OpenAL names):
 *
 *   two contexts   0 = the output, 1 = the reverb bus (its render plus the Stereoverb reaches the output)
 *   sources        buffer, looping, gain, pitch, position, direct channels, spatialise, low-pass HF gain
 *   spatial        a mono buffer on a source that is not direct: the game's HRTF (horizontal ring, nearest
 *                  direction, as the original) convolved per ear
 *   direct         stereo buffers straight to the two channels; "centre" buffers are mono at 0.5 in both
 *
 * Everything is rendered at 44.1 kHz in blocks of 256 frames, like the original's CSL buffers.
 */
public final class MiniAl {
    /**
     * The rate everything is mixed at.  It is the phone's own output rate (set by Bridge before the mixer is
     * made, usually 48000): at any other rate Android resamples the game's sound and refuses it the low
     * latency path, which is heard as sounds coming late.
     */
    public static int SAMPLE_RATE = 44100;
    public static final int BLOCK = 256;
    private static final int HIST = 192;

    public static final int KIND_MONO = 0;
    public static final int KIND_STEREO = 1;
    public static final int KIND_CENTER = 2;

    // the OpenAL enums the Python side sends
    public static final int AL_SOURCE_RELATIVE = 0x0202;
    public static final int AL_PITCH = 0x1003;
    public static final int AL_POSITION = 0x1004;
    public static final int AL_LOOPING = 0x1007;
    public static final int AL_BUFFER = 0x1009;
    public static final int AL_GAIN = 0x100A;
    public static final int AL_MAX_GAIN = 0x100E;
    public static final int AL_SOURCE_STATE = 0x1010;
    public static final int AL_INITIAL = 0x1011;
    public static final int AL_PLAYING = 0x1012;
    public static final int AL_PAUSED = 0x1013;
    public static final int AL_STOPPED = 0x1014;
    public static final int AL_SEC_OFFSET = 0x1024;
    public static final int AL_SAMPLE_OFFSET = 0x1025;
    public static final int AL_DIRECT_CHANNELS_SOFT = 0x1033;
    public static final int AL_SOURCE_SPATIALIZE_SOFT = 0x1214;
    /** Not an OpenAL enum: the direct filter's HF gain, which the Python side resolves from its filter table. */
    public static final int PARAM_DIRECT_HF = 0x30000;

    public static final class Decoded {
        public final short[] pcm;      // interleaved
        public final int channels;
        public final int rate;
        public final int frames;

        public Decoded(short[] pcm, int channels, int rate) {
            this.pcm = pcm;
            this.channels = channels;
            this.rate = rate;
            this.frames = channels > 0 ? pcm.length / channels : 0;
        }
    }

    private static final class Buf {
        short[] pcm;
        int kind;
        int rate;
        int frames;
    }

    private static final class Source {
        final int id;
        Buf buf;
        int state = AL_INITIAL;
        double pos;
        boolean looping;
        boolean relative;
        boolean direct;
        boolean spatialize;
        float gain = 1f;
        float maxGain = 1f;
        float pitch = 1f;
        float hf = 1f;
        float px, py, pz;
        float gainPrev = -1f;
        final float[] hist = new float[HIST];
        float lowState;
        float lowCoef;
        float lowFor = 1f;
        int lastIdx = -1;

        Source(int id) {
            this.id = id;
        }
    }

    private static final class Context {
        final Map<Integer, Source> sources = new HashMap<>();
        float listenerGain = 1f;
    }

    private final Object lock = new Object();
    /** The HRTF the sound is heard with, taken under the lock: Settings > Sound > 3D sound changes it (setHrtf). */
    private Hrtf hrtf;
    private final Freeverb reverb = new Freeverb();
    private final Context[] contexts = {new Context(), new Context()};
    private final Map<Integer, Buf> buffers = new HashMap<>();
    private int nextId = 1;
    private float limiterGain = 1f;

    // scratch, reused every block
    private final float[] outL = new float[BLOCK];
    private final float[] outR = new float[BLOCK];
    private final float[] busL = new float[BLOCK];
    private final float[] busR = new float[BLOCK];
    private final float[] xl = new float[BLOCK];
    private final float[] xr = new float[BLOCK];
    private final float[] convX = new float[HIST + BLOCK];
    private final float[] yl = new float[BLOCK];
    private final float[] yr = new float[BLOCK];
    private final float[] yl2 = new float[BLOCK];
    private final float[] yr2 = new float[BLOCK];

    public MiniAl(byte[] hrtfFile) {
        this.hrtf = new Hrtf(hrtfFile);
    }

    /**
     * PORT ADDITION (Settings > Sound > 3D sound, user request, 2026-10-05): the sound heard with another HRTF from
     * the next block on, nothing stopped.  A source moving from one direction to the next fades between them; one
     * that was heard with the other HRTF starts afresh, there being nothing of the new one to fade from.  An
     * IllegalArgumentException, and the HRTF in use kept, when the file is not one this mixer can read.
     */
    public void setHrtf(byte[] hrtfFile) {
        Hrtf next = new Hrtf(hrtfFile);
        synchronized (lock) {
            hrtf = next;
            for (Context c : contexts) {
                for (Source s : c.sources.values()) {
                    s.lastIdx = -1;
                }
            }
        }
    }

    /** What is wrong with this file as an HRTF for the mixer, or "" when nothing is. */
    public static String hrtfProblem(byte[] hrtfFile) {
        try {
            new Hrtf(hrtfFile);
            return "";
        } catch (RuntimeException e) {
            return e.getMessage() == null ? "it cannot be read" : e.getMessage();
        }
    }

    // ------------------------------------------------------------------------------------ decoded sounds
    private final Map<Integer, Decoded> sounds = new HashMap<>();
    private int nextSound = 1;

    /** Keeps a decoded sound and gives it a handle that Python can hold. */
    public int register(Decoded d) {
        synchronized (lock) {
            int h = nextSound++;
            sounds.put(h, d);
            return h;
        }
    }

    public Decoded sound(int handle) {
        synchronized (lock) {
            return sounds.get(handle);
        }
    }

    /** Builds the buffer the engine asks for (kind 0 mono for spatial, 1 stereo, 2 centred mono) from a sound. */
    public void bufferFromSound(int bufId, int handle, int kind) {
        Decoded d = sound(handle);
        if (d != null) {
            bufferData(bufId, d, kind);
        }
    }

    /** Seconds of near-silence at the start of a sound (louder than floor, at most `most`). */
    public float leadIn(int handle, float floor, float most) {
        Decoded d = sound(handle);
        if (d == null || d.frames == 0 || d.rate == 0) {
            return 0f;
        }
        int limit = (int) (floor * 32768f);
        for (int i = 0; i < d.frames; i++) {
            int sum = 0;
            for (int c = 0; c < d.channels; c++) {
                sum += d.pcm[i * d.channels + c];
            }
            if (Math.abs(sum / d.channels) > limit) {
                return Math.min((float) i / d.rate, most);
            }
        }
        return 0f;
    }

    /** Every source's context, id, state and play position in seconds: one call instead of two per sound. */
    public float[] snapshot() {
        synchronized (lock) {
            int n = 0;
            for (Context c : contexts) {
                n += c.sources.size();
            }
            float[] out = new float[n * 4];
            int k = 0;
            for (int ci = 0; ci < contexts.length; ci++) {
                for (Source s : contexts[ci].sources.values()) {
                    out[k++] = ci;
                    out[k++] = s.id;
                    out[k++] = s.state;
                    out[k++] = s.buf == null || s.buf.rate == 0 ? 0f : (float) (s.pos / s.buf.rate);
                }
            }
            return out;
        }
    }

    // ------------------------------------------------------------------------------------ buffers
    public int genBuffer() {
        synchronized (lock) {
            int id = nextId++;
            buffers.put(id, new Buf());
            return id;
        }
    }

    public void deleteBuffer(int id) {
        synchronized (lock) {
            buffers.remove(id);
            for (Context c : contexts) {
                for (Source s : c.sources.values()) {
                    if (s.buf != null && !buffers.containsValue(s.buf)) {
                        s.buf = null;
                        s.state = AL_STOPPED;
                    }
                }
            }
        }
    }

    /** Fills a buffer from decoded sound, in the shape the engine's variant asks for. */
    public void bufferData(int id, Decoded d, int kind) {
        Buf b = new Buf();
        b.kind = kind;
        b.rate = d.rate;
        b.frames = d.frames;
        if (kind == KIND_STEREO) {
            if (d.channels >= 2) {
                b.pcm = d.channels == 2 ? d.pcm : firstChannels(d, 2);
            } else {
                b.pcm = new short[d.frames * 2];
                for (int i = 0; i < d.frames; i++) {
                    b.pcm[2 * i] = d.pcm[i];
                    b.pcm[2 * i + 1] = d.pcm[i];
                }
            }
        } else if (kind == KIND_CENTER) {
            b.pcm = d.channels == 1 ? d.pcm : firstChannels(d, 1);
        } else {
            if (d.channels == 1) {
                b.pcm = d.pcm;
            } else {
                b.pcm = new short[d.frames];
                for (int i = 0; i < d.frames; i++) {
                    int sum = 0;
                    for (int c = 0; c < d.channels; c++) {
                        sum += d.pcm[i * d.channels + c];
                    }
                    b.pcm[i] = (short) (sum / d.channels);
                }
            }
        }
        synchronized (lock) {
            Buf old = buffers.put(id, b);
            if (old != null) {
                for (Context c : contexts) {
                    for (Source s : c.sources.values()) {
                        if (s.buf == old) {
                            s.buf = b;
                        }
                    }
                }
            }
        }
    }

    private static short[] firstChannels(Decoded d, int keep) {
        short[] out = new short[d.frames * keep];
        for (int i = 0; i < d.frames; i++) {
            for (int c = 0; c < keep; c++) {
                out[i * keep + c] = d.pcm[i * d.channels + c];
            }
        }
        return out;
    }

    // ------------------------------------------------------------------------------------ sources
    public int genSource(int ctx) {
        synchronized (lock) {
            int id = nextId++;
            contexts[ctx].sources.put(id, new Source(id));
            return id;
        }
    }

    public void deleteSource(int ctx, int id) {
        synchronized (lock) {
            contexts[ctx].sources.remove(id);
        }
    }

    private Source src(int ctx, int id) {
        return contexts[ctx].sources.get(id);
    }

    public void sourceI(int ctx, int id, int param, int v) {
        synchronized (lock) {
            Source s = src(ctx, id);
            if (s == null) {
                return;
            }
            switch (param) {
                case AL_BUFFER:
                    s.buf = v == 0 ? null : buffers.get(v);
                    s.state = AL_INITIAL;
                    s.pos = 0;
                    break;
                case AL_LOOPING:
                    s.looping = v != 0;
                    break;
                case AL_SOURCE_RELATIVE:
                    s.relative = v != 0;
                    break;
                case AL_DIRECT_CHANNELS_SOFT:
                    s.direct = v != 0;
                    break;
                case AL_SOURCE_SPATIALIZE_SOFT:
                    s.spatialize = v != 0;
                    break;
                case AL_SAMPLE_OFFSET:
                    s.pos = Math.max(0, v);
                    break;
                default:
                    break;
            }
        }
    }

    public void sourceF(int ctx, int id, int param, float v) {
        synchronized (lock) {
            Source s = src(ctx, id);
            if (s == null) {
                return;
            }
            switch (param) {
                case AL_GAIN:
                    s.gain = v;
                    break;
                case AL_MAX_GAIN:
                    s.maxGain = v;
                    break;
                case AL_PITCH:
                    s.pitch = v > 0 ? v : 1f;
                    break;
                case PARAM_DIRECT_HF:
                    s.hf = v;
                    break;
                case AL_SEC_OFFSET:
                    if (s.buf != null) {
                        s.pos = Math.max(0.0, Math.min(v * (double) s.buf.rate, s.buf.frames));
                    }
                    break;
                default:
                    break;
            }
        }
    }

    public void source3F(int ctx, int id, int param, float x, float y, float z) {
        synchronized (lock) {
            Source s = src(ctx, id);
            if (s != null && param == AL_POSITION) {
                s.px = x;
                s.py = y;
                s.pz = z;
            }
        }
    }

    public int getSourceI(int ctx, int id, int param) {
        synchronized (lock) {
            Source s = src(ctx, id);
            if (s == null) {
                return param == AL_SOURCE_STATE ? AL_INITIAL : 0;
            }
            switch (param) {
                case AL_SOURCE_STATE:
                    return s.state;
                case AL_LOOPING:
                    return s.looping ? 1 : 0;
                case AL_SAMPLE_OFFSET:
                    return (int) s.pos;
                default:
                    return 0;
            }
        }
    }

    public float getSourceF(int ctx, int id, int param) {
        synchronized (lock) {
            Source s = src(ctx, id);
            if (s == null) {
                return 0f;
            }
            switch (param) {
                case AL_SEC_OFFSET:
                    return s.buf == null || s.buf.rate == 0 ? 0f : (float) (s.pos / s.buf.rate);
                case AL_GAIN:
                    return s.gain;
                default:
                    return 0f;
            }
        }
    }

    public void play(int ctx, int id) {
        synchronized (lock) {
            Source s = src(ctx, id);
            if (s == null || s.buf == null) {
                return;
            }
            if (s.state == AL_PLAYING || s.state == AL_STOPPED) {
                s.pos = 0;
            }
            s.state = AL_PLAYING;
            s.gainPrev = -1f;
            s.lastIdx = -1;
            java.util.Arrays.fill(s.hist, 0f);
            s.lowState = 0f;
        }
    }

    public void pause(int ctx, int id) {
        synchronized (lock) {
            Source s = src(ctx, id);
            if (s != null && s.state == AL_PLAYING) {
                s.state = AL_PAUSED;
            }
        }
    }

    public void stop(int ctx, int id) {
        synchronized (lock) {
            Source s = src(ctx, id);
            if (s != null && (s.state == AL_PLAYING || s.state == AL_PAUSED)) {
                s.state = AL_STOPPED;
                s.pos = 0;
            }
        }
    }

    public void rewind(int ctx, int id) {
        synchronized (lock) {
            Source s = src(ctx, id);
            if (s != null) {
                s.state = AL_INITIAL;
                s.pos = 0;
            }
        }
    }

    public void setListenerGain(int ctx, float g) {
        synchronized (lock) {
            contexts[ctx].listenerGain = Math.max(0f, g);
        }
    }

    public void stopEverything() {
        synchronized (lock) {
            for (Context c : contexts) {
                for (Source s : c.sources.values()) {
                    if (s.state == AL_PLAYING || s.state == AL_PAUSED) {
                        s.state = AL_STOPPED;
                    }
                }
            }
        }
    }

    // ------------------------------------------------------------------------------------ reverb
    public void reverbRoomSize(float v) { reverb.setRoomSize(v); }
    public void reverbDampening(float v) { reverb.setDampening(v); }
    public void reverbWet(float v) { reverb.setWet(v); }
    public void reverbDry(float v) { reverb.setDry(v); }
    public void reverbActive(boolean on) { reverb.setActive(on); }

    public int playingVoices() {
        synchronized (lock) {
            int n = 0;
            for (Context c : contexts) {
                for (Source s : c.sources.values()) {
                    if (s.state == AL_PLAYING) {
                        n++;
                    }
                }
            }
            return n;
        }
    }

    // ------------------------------------------------------------------------------------ render
    /** Renders interleaved stereo float frames. */
    public void render(float[] out, int frames) {
        int done = 0;
        while (done < frames) {
            int n = Math.min(BLOCK, frames - done);
            synchronized (lock) {
                renderBlock(n);
            }
            for (int i = 0; i < n; i++) {
                out[2 * (done + i)] = outL[i];
                out[2 * (done + i) + 1] = outR[i];
            }
            done += n;
        }
    }

    private void renderBlock(int n) {
        java.util.Arrays.fill(outL, 0, n, 0f);
        java.util.Arrays.fill(outR, 0, n, 0f);
        java.util.Arrays.fill(busL, 0, n, 0f);
        java.util.Arrays.fill(busR, 0, n, 0f);
        mixContext(contexts[0], n, outL, outR);
        mixContext(contexts[1], n, busL, busR);
        float bg = contexts[1].listenerGain;
        if (bg != 1f) {
            for (int i = 0; i < n; i++) {
                busL[i] *= bg;
                busR[i] *= bg;
            }
        }
        if (reverb.isActive()) {
            reverb.process(busL, busR, n);
        }
        float master = contexts[0].listenerGain;
        float lg = limiterGain;
        final float release = 1f / (0.05f * SAMPLE_RATE);
        for (int i = 0; i < n; i++) {
            float l = (outL[i] + busL[i]) * master;
            float r = (outR[i] + busR[i]) * master;
            float peak = Math.max(Math.abs(l), Math.abs(r));
            if (peak * lg > 1f) {
                lg = 1f / peak;
            } else if (lg < 1f) {
                lg = Math.min(1f, lg + release);
            }
            outL[i] = l * lg;
            outR[i] = r * lg;
        }
        limiterGain = lg;
    }

    private void mixContext(Context c, int n, float[] dl, float[] dr) {
        for (Source s : c.sources.values()) {
            if (s.state == AL_PLAYING && s.buf != null) {
                mixSource(s, n, dl, dr);
            }
        }
    }

    private void mixSource(Source s, int n, float[] dl, float[] dr) {
        Buf b = s.buf;
        if (b.frames == 0 || b.pcm == null) {
            s.state = AL_STOPPED;
            return;
        }
        float g1 = Math.min(Math.max(s.gain, 0f), s.maxGain);
        float g0 = s.gainPrev < 0f ? g1 : s.gainPrev;
        s.gainPrev = g1;
        double step = (double) b.rate / SAMPLE_RATE * s.pitch;
        boolean spatial = !s.direct && b.kind == KIND_MONO;
        int produced = fill(s, b, n, step, spatial ? null : xl, spatial ? null : xr, spatial ? convX : null,
                g0, g1);
        if (produced < 0) {
            return;
        }
        if (!spatial) {
            for (int i = 0; i < n; i++) {
                dl[i] += xl[i];
                dr[i] += xr[i];
            }
            return;
        }
        // low-pass (the air absorption) then the HRTF
        float hf = s.hf;
        if (hf < 0.9999f) {
            if (s.lowFor != hf) {
                s.lowCoef = lowpassCoefficient(hf);
                s.lowFor = hf;
            }
            float p = s.lowCoef;
            float st = s.lowState;
            for (int i = 0; i < n; i++) {
                st = (1f - p) * convX[HIST + i] + p * st;
                convX[HIST + i] = st;
            }
            s.lowState = st;
        } else {
            s.lowState = n > 0 ? convX[HIST + n - 1] : s.lowState;
        }
        float ax = s.px;
        float az = s.pz;
        int idx = hrtf.indexFor(ax, az);
        convolve(convX, n, hrtf.tapsL[idx], hrtf.offL[idx], yl);
        convolve(convX, n, hrtf.tapsR[idx], hrtf.offR[idx], yr);
        int last = s.lastIdx;
        if (last >= 0 && last != idx) {
            convolve(convX, n, hrtf.tapsL[last], hrtf.offL[last], yl2);
            convolve(convX, n, hrtf.tapsR[last], hrtf.offR[last], yr2);
            for (int i = 0; i < n; i++) {
                float w = (i + 1f) / n;
                dl[i] += yl2[i] + (yl[i] - yl2[i]) * w;
                dr[i] += yr2[i] + (yr[i] - yr2[i]) * w;
            }
        } else {
            for (int i = 0; i < n; i++) {
                dl[i] += yl[i];
                dr[i] += yr[i];
            }
        }
        s.lastIdx = idx;
        System.arraycopy(convX, n, s.hist, 0, HIST);
    }

    /**
     * Reads n output frames from the buffer with linear interpolation.  Direct sources fill l and r; a
     * spatial source fills convX after its history.  Returns -1 when nothing was produced.
     */
    private int fill(Source s, Buf b, int n, double step, float[] l, float[] r, float[] mono,
                     float g0, float g1) {
        short[] pcm = b.pcm;
        int frames = b.frames;
        double pos = s.pos;
        boolean loop = s.looping;
        int kind = b.kind;
        if (mono != null) {
            System.arraycopy(s.hist, 0, mono, 0, HIST);
        }
        final float scale = 1f / 32768f;
        int i = 0;
        for (; i < n; i++) {
            if (pos >= frames) {
                if (loop) {
                    pos -= frames * Math.floor(pos / frames);
                } else {
                    s.state = AL_STOPPED;
                    break;
                }
            }
            int i0 = (int) pos;
            float fr = (float) (pos - i0);
            int i1 = i0 + 1;
            if (i1 >= frames) {
                i1 = loop ? 0 : i0;
            }
            float g = g0 + (g1 - g0) * ((i + 1f) / n);
            if (kind == KIND_STEREO) {
                float a0 = pcm[2 * i0], b0 = pcm[2 * i0 + 1];
                float a1 = pcm[2 * i1], b1 = pcm[2 * i1 + 1];
                l[i] = (a0 + (a1 - a0) * fr) * scale * g;
                r[i] = (b0 + (b1 - b0) * fr) * scale * g;
            } else {
                float v0 = pcm[i0], v1 = pcm[i1];
                float v = (v0 + (v1 - v0) * fr) * scale * g;
                if (kind == KIND_CENTER) {
                    l[i] = v * 0.5f;
                    r[i] = v * 0.5f;
                } else if (mono != null) {
                    mono[HIST + i] = v;
                } else {
                    l[i] = v;
                    r[i] = v;
                }
            }
            pos += step;
        }
        for (; i < n; i++) {                       // ran out: silence
            if (mono != null) {
                mono[HIST + i] = 0f;
            } else {
                l[i] = 0f;
                r[i] = 0f;
            }
        }
        if (s.state == AL_PLAYING && !loop && pos >= frames) {
            s.state = AL_STOPPED;                  // the last frame has been read
        }
        s.pos = s.state == AL_STOPPED && !loop ? frames : pos;
        return n;
    }

    private volatile int tapLimit = Hrtf.TAPS;

    /** Shortens the HRTF filters when the phone cannot keep up (the tail of a minimum-phase response is tiny). */
    public void setTapLimit(int taps) {
        tapLimit = Math.max(48, Math.min(Hrtf.TAPS, taps));
    }

    public int getTapLimit() {
        return tapLimit;
    }

    private void convolve(float[] x, int n, float[] taps, int off, float[] out) {
        final int t = Math.min(taps.length, tapLimit) & ~3;
        for (int i = 0; i < n; i++) {
            int base = HIST + i - off;
            float a0 = 0f, a1 = 0f, a2 = 0f, a3 = 0f;
            for (int j = 0; j < t; j += 4) {
                a0 += taps[j] * x[base - j];
                a1 += taps[j + 1] * x[base - j - 1];
                a2 += taps[j + 2] * x[base - j - 2];
                a3 += taps[j + 3] * x[base - j - 3];
            }
            out[i] = (a0 + a1) + (a2 + a3) + (t < taps.length ? taps[t] * x[base - t] : 0f);
        }
    }

    /** One-pole low-pass y = (1-p) x + p y whose magnitude at 5 kHz is hf (the EFX low-pass reference). */
    private static float lowpassCoefficient(float hf) {
        double w = 2.0 * Math.PI * 5000.0 / SAMPLE_RATE;
        double lo = 0.0;
        double hi = 0.999;
        for (int k = 0; k < 40; k++) {
            double p = (lo + hi) / 2.0;
            double re = 1.0 - p * Math.cos(w);
            double im = p * Math.sin(w);
            double mag = (1.0 - p) / Math.sqrt(re * re + im * im);
            if (mag > hf) {
                lo = p;
            } else {
                hi = p;
            }
        }
        return (float) ((lo + hi) / 2.0);
    }
}
