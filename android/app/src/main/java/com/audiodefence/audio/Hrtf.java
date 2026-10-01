package com.audiodefence.audio;

/**
 * Reader for the game's own HRTF (assets/hrtf/audiodefence_ircam1050.mhr, an OpenAL Soft "MinPHR03" file
 * built from the impulse responses embedded in the original iOS binary).
 *
 * The original picks the nearest of 24 horizontal IRCAM directions for a source; the .mhr repeats each of
 * those directions over its +-7.5 degree sector on the horizontal ring, so choosing the nearest entry of
 * that ring reproduces the original's choice exactly.  Every entry becomes an effective FIR per ear: the
 * 128 stored taps placed after the entry's interaural delay (a quarter-sample resolution, kept by linear
 * interpolation between two neighbouring taps).
 */
final class Hrtf {
    static final int LEN = 128;
    static final int TAPS = LEN + 1;

    final int rate;
    final int ringCount;
    final float[][] tapsL;
    final float[][] tapsR;
    final int[] offL;
    final int[] offR;

    Hrtf(byte[] d) {
        String magic = new String(d, 0, 8, java.nio.charset.StandardCharsets.US_ASCII);
        if (!"MinPHR03".equals(magic)) {
            throw new IllegalArgumentException("not a MinPHR03 HRTF: " + magic);
        }
        rate = le32(d, 8);
        int channelType = d[12] & 255;
        int hrirSize = d[13] & 255;
        int fdCount = d[14] & 255;
        if (channelType != 1 || hrirSize != LEN || fdCount != 1) {
            throw new IllegalArgumentException("unsupported HRTF layout");
        }
        int pos = 15;
        pos += 2;                                   // distance
        int evCount = d[pos++] & 255;
        int[] az = new int[evCount];
        int irCount = 0;
        for (int e = 0; e < evCount; e++) {
            az[e] = d[pos++] & 255;
            irCount += az[e];
        }
        float[][] hl = new float[irCount][LEN];
        float[][] hr = new float[irCount][LEN];
        for (int i = 0; i < irCount; i++) {
            for (int t = 0; t < LEN; t++) {
                hl[i][t] = s24(d, pos) / 8388608f;
                pos += 3;
                hr[i][t] = s24(d, pos) / 8388608f;
                pos += 3;
            }
        }
        int[] dl = new int[irCount];
        int[] dr = new int[irCount];
        for (int i = 0; i < irCount; i++) {
            dl[i] = d[pos++] & 255;
            dr[i] = d[pos++] & 255;
        }
        int ev = (evCount - 1) / 2;                 // the horizontal ring
        int start = 0;
        for (int e = 0; e < ev; e++) {
            start += az[e];
        }
        ringCount = az[ev];
        tapsL = new float[ringCount][];
        tapsR = new float[ringCount][];
        offL = new int[ringCount];
        offR = new int[ringCount];
        for (int k = 0; k < ringCount; k++) {
            build(hl[start + k], dl[start + k], tapsL, offL, k);
            build(hr[start + k], dr[start + k], tapsR, offR, k);
        }
    }

    private static void build(float[] h, int quarter, float[][] taps, int[] off, int k) {
        int whole = quarter >> 2;
        float frac = (quarter & 3) / 4f;
        float[] t = new float[TAPS];
        for (int j = 0; j < TAPS; j++) {
            float a = j < LEN ? h[j] : 0f;
            float b = j >= 1 ? h[j - 1] : 0f;
            t[j] = (1f - frac) * a + frac * b;
        }
        taps[k] = t;
        off[k] = whole;
    }

    /** Ring entry for a direction: x to the right, z backwards (OpenAL), the way the engine passes it. */
    int indexFor(float x, float z) {
        double clockwise = Math.atan2(x, -z);       // 0 = ahead, increasing towards the right
        if (clockwise < 0) {
            clockwise += 2 * Math.PI;
        }
        int k = (int) Math.round(clockwise / (2 * Math.PI) * ringCount);
        return k % ringCount;
    }

    static int maxOffset() {
        return 64;
    }

    private static int le32(byte[] d, int p) {
        return (d[p] & 255) | (d[p + 1] & 255) << 8 | (d[p + 2] & 255) << 16 | (d[p + 3] & 255) << 24;
    }

    private static int s24(byte[] d, int p) {
        int v = (d[p] & 255) | (d[p + 1] & 255) << 8 | (d[p + 2] & 255) << 16;
        return (v << 8) >> 8;
    }
}
