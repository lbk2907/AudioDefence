package com.audiodefence.audio;

import android.media.MediaCodec;
import android.media.MediaExtractor;
import android.media.MediaFormat;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.ShortBuffer;

/**
 * Decodes one of the game's .m4a / .mp3 files to 16-bit PCM with the phone's own decoder (MediaCodec).
 * The encoder delay and padding the file declares are trimmed off, as CoreAudio's ExtAudioFile does in
 * the original, so a sound starts exactly where it should.
 */
public final class SoundDecoder {
    private SoundDecoder() {
    }

    /**
     * Making a MediaCodec is the slowest part of decoding a short sound - often longer than the decoding
     * itself - so each thread keeps the decoders it has made, one per kind of file, and sets them up again
     * for the next file instead of making new ones.  That is most of what stood between a zombie being hit
     * and its hit or death sound the first time that sound was needed.
     */
    private static final ThreadLocal<java.util.HashMap<String, MediaCodec>> CODECS =
            ThreadLocal.withInitial(java.util.HashMap::new);

    public static MiniAl.Decoded decode(String path) throws IOException {
        MediaExtractor ex = new MediaExtractor();
        MediaCodec codec = null;
        String mimeKey = null;
        boolean reusable = false;
        try {
            ex.setDataSource(path);
            int track = -1;
            MediaFormat fmt = null;
            for (int i = 0; i < ex.getTrackCount(); i++) {
                MediaFormat f = ex.getTrackFormat(i);
                String mime = f.getString(MediaFormat.KEY_MIME);
                if (mime != null && mime.startsWith("audio/")) {
                    track = i;
                    fmt = f;
                    break;
                }
            }
            if (track < 0) {
                throw new IOException("no audio track in " + path);
            }
            ex.selectTrack(track);
            int rate = fmt.getInteger(MediaFormat.KEY_SAMPLE_RATE);
            int channels = fmt.getInteger(MediaFormat.KEY_CHANNEL_COUNT);
            int delay = fmt.containsKey("encoder-delay") ? fmt.getInteger("encoder-delay") : 0;
            int padding = fmt.containsKey("encoder-padding") ? fmt.getInteger("encoder-padding") : 0;
            // Newer phones' decoders trim the encoder delay and padding themselves when the format names
            // them - and this trims them again below, which cut a little off the start and the end of every
            // sound (heard on the Micro SMG's reload).  The decoder is told there is none, so the trimming
            // happens exactly once, here, whatever the phone's decoder would have done.
            if (delay > 0) {
                fmt.setInteger("encoder-delay", 0);
            }
            if (padding > 0) {
                fmt.setInteger("encoder-padding", 0);
            }

            mimeKey = fmt.getString(MediaFormat.KEY_MIME);
            codec = CODECS.get().remove(mimeKey);         // taken out while in use; put back when done
            if (codec != null) {
                try {
                    codec.configure(fmt, null, null, 0);
                } catch (Exception e) {
                    codec.release();                      // a used decoder that will not take this file
                    codec = null;
                }
            }
            if (codec == null) {
                codec = MediaCodec.createDecoderByType(mimeKey);
                codec.configure(fmt, null, null, 0);
            }
            codec.start();

            short[] out = new short[Math.max(rate * channels, 1 << 16)];
            int used = 0;
            boolean inputDone = false;
            boolean outputDone = false;
            boolean floatOut = false;
            MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
            while (!outputDone) {
                if (!inputDone) {
                    int ii = codec.dequeueInputBuffer(10000);
                    if (ii >= 0) {
                        ByteBuffer ib = codec.getInputBuffer(ii);
                        int n = ib == null ? -1 : ex.readSampleData(ib, 0);
                        if (n < 0) {
                            codec.queueInputBuffer(ii, 0, 0, 0, MediaCodec.BUFFER_FLAG_END_OF_STREAM);
                            inputDone = true;
                        } else {
                            codec.queueInputBuffer(ii, 0, n, ex.getSampleTime(), 0);
                            ex.advance();
                        }
                    }
                }
                int oi = codec.dequeueOutputBuffer(info, 10000);
                if (oi >= 0) {
                    ByteBuffer ob = codec.getOutputBuffer(oi);
                    if (ob != null && info.size > 0) {
                        ob.position(info.offset);
                        ob.limit(info.offset + info.size);
                        ob.order(ByteOrder.nativeOrder());
                        if (floatOut) {
                            java.nio.FloatBuffer fb = ob.asFloatBuffer();
                            int cnt = fb.remaining();
                            if (used + cnt > out.length) {
                                out = grow(out, used + cnt);
                            }
                            for (int k = 0; k < cnt; k++) {
                                float v = Math.max(-1f, Math.min(1f, fb.get()));
                                out[used++] = (short) (v * 32767f);
                            }
                        } else {
                            ShortBuffer sb = ob.asShortBuffer();
                            int cnt = sb.remaining();
                            if (used + cnt > out.length) {
                                out = grow(out, used + cnt);
                            }
                            sb.get(out, used, cnt);
                            used += cnt;
                        }
                    }
                    if ((info.flags & MediaCodec.BUFFER_FLAG_END_OF_STREAM) != 0) {
                        outputDone = true;
                    }
                    codec.releaseOutputBuffer(oi, false);
                } else if (oi == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                    MediaFormat nf = codec.getOutputFormat();
                    if (nf.containsKey(MediaFormat.KEY_SAMPLE_RATE)) {
                        rate = nf.getInteger(MediaFormat.KEY_SAMPLE_RATE);
                    }
                    if (nf.containsKey(MediaFormat.KEY_CHANNEL_COUNT)) {
                        channels = nf.getInteger(MediaFormat.KEY_CHANNEL_COUNT);
                    }
                    if (nf.containsKey(MediaFormat.KEY_PCM_ENCODING)
                            && nf.getInteger(MediaFormat.KEY_PCM_ENCODING) == android.media.AudioFormat.ENCODING_PCM_FLOAT) {
                        floatOut = true;
                    }
                }
            }
            int frames = used / channels;
            int skip = Math.min(Math.max(delay, 0), frames);
            int keep = Math.max(0, frames - skip - Math.max(padding, 0));
            short[] pcm = new short[keep * channels];
            System.arraycopy(out, skip * channels, pcm, 0, keep * channels);
            reusable = true;
            return new MiniAl.Decoded(pcm, channels, rate);
        } finally {
            if (codec != null) {
                boolean stopped = false;
                try {
                    codec.stop();
                    stopped = true;
                } catch (Exception ignored) {
                    // already stopped, or broken
                }
                if (reusable && stopped && mimeKey != null && !CODECS.get().containsKey(mimeKey)) {
                    CODECS.get().put(mimeKey, codec);     // kept for the next file of this kind
                } else {
                    codec.release();
                }
            }
            ex.release();
        }
    }

    private static short[] grow(short[] a, int need) {
        int n = a.length;
        while (n < need) {
            n = n + (n >> 1) + 1024;
        }
        short[] b = new short[n];
        System.arraycopy(a, 0, b, 0, a.length);
        return b;
    }
}
