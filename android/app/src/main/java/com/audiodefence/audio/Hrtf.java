package com.audiodefence.audio;

/**
 * Reader for an OpenAL Soft "MinPHR03" HRTF file: the game's own (assets/hrtf/audiodefence_ircam1050.mhr, built
 * from the impulse responses embedded in the original iOS binary), or one of the player's, made with OpenAL Soft's
 * makemhr (Settings > Sound > 3D sound, user request, 2026-10-05).
 *
 * The original picks the nearest of 24 horizontal IRCAM directions for a source; the game's .mhr repeats each of
 * those directions over its +-7.5 degree sector on the horizontal ring, so choosing the nearest entry of that
 * ring reproduces the original's choice exactly.  Every entry becomes an effective FIR per ear: the stored taps
 * placed after the entry's interaural delay (a quarter-sample resolution, kept by linear interpolation between
 * two neighbouring taps).
 *
 * A file of makemhr's may differ from the game's in three ways, all taken: fewer taps (32 unless asked for more;
 * padded to LEN with silence) or more (cut at LEN, where a minimum-phase response has long since spent itself);
 * one ear stored rather than two (channel type 0: the right ear is the left ear's mirror image, as OpenAL Soft
 * reads it); and more than one field, a set measured at several distances, of which the farthest is used, the
 * one most like the game's.  Only the horizontal ring is heard, as with the game's own: the game's sounds are
 * all on the ground around the player.
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
        if (d.length < 16) {
            throw new IllegalArgumentException("too short to be an HRTF");
        }
        String magic = new String(d, 0, 8, java.nio.charset.StandardCharsets.US_ASCII);
        if (!"MinPHR03".equals(magic)) {
            throw new IllegalArgumentException("not a MinPHR03 HRTF: " + magic.trim());
        }
        rate = le32(d, 8);
        int channelType = d[12] & 255;
        int irSize = d[13] & 255;
        int fdCount = d[14] & 255;
        if (channelType > 1 || irSize == 0 || fdCount == 0) {
            throw new IllegalArgumentException("unsupported HRTF layout");
        }
        int channels = channelType == 1 ? 2 : 1;
        int pos = 15;
        int[][] azCounts = new int[fdCount][];
        int[] distance = new int[fdCount];
        for (int f = 0; f < fdCount; f++) {
            need(d, pos, 3);
            distance[f] = (d[pos] & 255) | (d[pos + 1] & 255) << 8;
            pos += 2;
            int evCount = d[pos++] & 255;
            if (evCount == 0) {
                throw new IllegalArgumentException("a field with no elevations");
            }
            azCounts[f] = new int[evCount];
            need(d, pos, evCount);
            for (int e = 0; e < evCount; e++) {
                azCounts[f][e] = d[pos++] & 255;
            }
        }
        // the farthest field, and where its responses and delays begin among all the fields'
        int field = 0;
        for (int f = 1; f < fdCount; f++) {
            if (distance[f] > distance[field]) {
                field = f;
            }
        }
        int irTotal = 0;
        int irBefore = 0;
        for (int f = 0; f < fdCount; f++) {
            for (int count : azCounts[f]) {
                if (f < field) {
                    irBefore += count;
                }
                irTotal += count;
            }
        }
        int irBytes = irSize * channels * 3;
        int delayStart = pos + irTotal * irBytes;
        need(d, delayStart, irTotal * channels);
        // its horizontal ring: the elevations run from straight down to straight up
        int[] az = azCounts[field];
        int ev = (az.length - 1) / 2;
        int start = irBefore;
        for (int e = 0; e < ev; e++) {
            start += az[e];
        }
        ringCount = az[ev];
        if (ringCount == 0) {
            throw new IllegalArgumentException("no horizontal directions");
        }
        tapsL = new float[ringCount][];
        tapsR = new float[ringCount][];
        offL = new int[ringCount];
        offR = new int[ringCount];
        for (int k = 0; k < ringCount; k++) {
            int left = start + k;
            // one ear stored: the right ear at a direction is the left ear at its mirror image
            int right = channels == 2 ? left : start + (ringCount - k) % ringCount;
            int rightChannel = channels == 2 ? 1 : 0;
            build(d, pos + left * irBytes, irSize, channels, 0, d[delayStart + left * channels] & 255,
                    tapsL, offL, k);
            build(d, pos + right * irBytes, irSize, channels, rightChannel,
                    d[delayStart + right * channels + rightChannel] & 255, tapsR, offR, k);
        }
    }

    private static void need(byte[] d, int pos, int count) {
        if (pos < 0 || count < 0 || (long) pos + count > d.length) {
            throw new IllegalArgumentException("the HRTF file ends too soon");
        }
    }

    private static void build(byte[] d, int at, int irSize, int channels, int channel, int quarter,
                              float[][] taps, int[] off, int k) {
        float[] h = new float[LEN];
        for (int t = 0; t < Math.min(irSize, LEN); t++) {
            h[t] = s24(d, at + (t * channels + channel) * 3) / 8388608f;
        }
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
