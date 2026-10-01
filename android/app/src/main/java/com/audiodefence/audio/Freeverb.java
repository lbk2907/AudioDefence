package com.audiodefence.audio;

/**
 * csl::Stereoverb of the original: two csl::Freeverb, one per channel, with the tunings and formulas read
 * from the binary (see audiodefence/s3d/reverb.py in the desktop port).  Six combs, three allpasses.
 */
final class Freeverb {
    private static final int[] COMB = {1116, 1188, 1277, 1356, 1422, 1491};
    private static final int[] ALLPASS = {556, 441, 341};
    private static final float FIXED_GAIN = 0.015f;
    private static final float ALLPASS_FEEDBACK = 0.5f;

    private static final class Channel {
        final float[][] comb = new float[COMB.length][];
        final int[] combIdx = new int[COMB.length];
        final float[] store = new float[COMB.length];
        final float[][] ap = new float[ALLPASS.length][];
        final int[] apIdx = new int[ALLPASS.length];

        Channel() {
            for (int i = 0; i < COMB.length; i++) {
                comb[i] = new float[COMB[i]];
            }
            for (int i = 0; i < ALLPASS.length; i++) {
                ap[i] = new float[ALLPASS[i]];
            }
        }

        float process(float x, float room, float damp, float damp2, float wet, float dry) {
            float in = x * FIXED_GAIN;
            float out = 0f;
            for (int c = 0; c < COMB.length; c++) {
                float[] buf = comb[c];
                int i = combIdx[c];
                float y = buf[i];
                store[c] = y * damp2 + store[c] * damp;
                buf[i] = in + store[c] * room;
                out += y;
                combIdx[c] = ++i == buf.length ? 0 : i;
            }
            for (int a = 0; a < ALLPASS.length; a++) {
                float[] buf = ap[a];
                int i = apIdx[a];
                float b = buf[i];
                buf[i] = out + b * ALLPASS_FEEDBACK;
                out = b - out;
                apIdx[a] = ++i == buf.length ? 0 : i;
            }
            return out * wet + x * dry;
        }
    }

    private final Channel left = new Channel();
    private final Channel right = new Channel();
    private volatile float room = 0.37f;
    private volatile float damp = 0.04f;
    private volatile float damp2 = 0.96f;
    private volatile float wet = 0.5f;
    private volatile float dry = 0.5f;
    private volatile boolean active;

    void setRoomSize(float size) {
        room = size * 0.28f + 0.3f;
    }

    void setDampening(float d) {
        damp = d * 0.01f * 0.4f;
        damp2 = 1f - damp;
    }

    void setWet(float v) {
        wet = v;
    }

    void setDry(float v) {
        dry = v;
    }

    void setActive(boolean on) {
        active = on;
    }

    boolean isActive() {
        return active;
    }

    /** In place: the input plus the Stereoverb output of it (dryMixer + Stereoverb). */
    void process(float[] l, float[] r, int n) {
        float rm = room, dp = damp, dp2 = damp2, w = wet, dr = dry;
        for (int i = 0; i < n; i++) {
            float xl = l[i];
            float xr = r[i];
            l[i] = xl + left.process(xl, rm, dp, dp2, w, dr);
            r[i] = xr + right.process(xr, rm, dp, dp2, w, dr);
        }
    }
}
