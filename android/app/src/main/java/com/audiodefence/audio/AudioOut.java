package com.audiodefence.audio;

import android.content.Context;
import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioTrack;
import android.os.Process;
import android.util.Log;

/**
 * Pulls the mixer's output on a thread of its own and plays it: stereo float at the phone's own rate, low
 * latency.
 *
 * Lag and crackle are fought three ways:
 *  - the mix runs at the phone's native output rate, so Android can give it its fast (low latency) path;
 *  - the thread runs at Android's audio priority, so the game's own work cannot starve it;
 *  - the part of the buffer in use starts small and grows by one burst each time the phone runs dry
 *    (an underrun is heard as a click or a stutter), so each phone settles at the shortest delay it can keep.
 */
public final class AudioOut implements Runnable {
    private static final String TAG = "AudioOut";
    private final MiniAl al;
    private AudioTrack track;
    private Thread thread;
    private volatile boolean running;
    private volatile boolean paused;
    private final Object pauseLock = new Object();
    private int burst = MiniAl.BLOCK;      // frames the phone's mixer takes at a time

    public AudioOut(MiniAl al) {
        this.al = al;
    }

    /** The phone's output sample rate (44100 if it does not say). */
    public static int nativeRate(Context ctx) {
        try {
            AudioManager am = (AudioManager) ctx.getSystemService(Context.AUDIO_SERVICE);
            String r = am.getProperty(AudioManager.PROPERTY_OUTPUT_SAMPLE_RATE);
            int rate = r != null ? Integer.parseInt(r) : 0;
            if (rate >= 22050 && rate <= 96000) {
                return rate;
            }
        } catch (Exception ignored) {
            // fall through
        }
        return 44100;
    }

    private static int nativeBurst(Context ctx) {
        try {
            AudioManager am = (AudioManager) ctx.getSystemService(Context.AUDIO_SERVICE);
            String f = am.getProperty(AudioManager.PROPERTY_OUTPUT_FRAMES_PER_BUFFER);
            int n = f != null ? Integer.parseInt(f) : 0;
            if (n >= 32 && n <= 4096) {
                return n;
            }
        } catch (Exception ignored) {
            // fall through
        }
        return MiniAl.BLOCK;
    }

    public void start() {
        start(null);
    }

    public void start(Context ctx) {
        if (ctx != null) {
            burst = nativeBurst(ctx);
        }
        int rate = MiniAl.SAMPLE_RATE;
        int minBytes = AudioTrack.getMinBufferSize(rate, AudioFormat.CHANNEL_OUT_STEREO,
                AudioFormat.ENCODING_PCM_FLOAT);
        // room to grow into: a quarter of a second at most, however little is used at first
        int capacityBytes = Math.max(minBytes * 2, rate / 4 * 4 * 2);
        track = new AudioTrack.Builder()
                .setAudioAttributes(new AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_GAME)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
                        .build())
                .setAudioFormat(new AudioFormat.Builder()
                        .setEncoding(AudioFormat.ENCODING_PCM_FLOAT)
                        .setSampleRate(rate)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_STEREO)
                        .build())
                .setBufferSizeInBytes(capacityBytes)
                .setPerformanceMode(AudioTrack.PERFORMANCE_MODE_LOW_LATENCY)
                .setTransferMode(AudioTrack.MODE_STREAM)
                .build();
        // start with two bursts plus one of our blocks in use; underruns add more (see run)
        int minFrames = minBytes / 8;
        int want = Math.max(minFrames, burst * 2 + MiniAl.BLOCK);
        try {
            track.setBufferSizeInFrames(want);
        } catch (Exception e) {
            Log.w(TAG, "cannot set the buffer size", e);
        }
        Log.i(TAG, "rate " + rate + ", burst " + burst + ", buffer " + track.getBufferSizeInFrames()
                + " of " + track.getBufferCapacityInFrames() + " frames, fast path "
                + (track.getPerformanceMode() == AudioTrack.PERFORMANCE_MODE_LOW_LATENCY));
        running = true;
        track.play();
        thread = new Thread(this, "audio-out");
        thread.setPriority(Thread.MAX_PRIORITY);
        thread.start();
    }

    public void setPaused(boolean p) {
        synchronized (pauseLock) {
            paused = p;
            pauseLock.notifyAll();
        }
        if (track != null) {
            if (p) {
                track.pause();
            } else {
                track.play();
            }
        }
    }

    public void stop() {
        running = false;
        synchronized (pauseLock) {
            pauseLock.notifyAll();
        }
        if (track != null) {
            try {
                track.stop();
            } catch (Exception ignored) {
                // not started
            }
            track.release();
            track = null;
        }
    }

    @Override
    public void run() {
        try {
            Process.setThreadPriority(Process.THREAD_PRIORITY_URGENT_AUDIO);
        } catch (Exception e) {
            Log.w(TAG, "cannot raise the audio thread's priority", e);
        }
        // one of our blocks per write: the smaller each write, the sooner a new sound is heard
        float[] buf = new float[MiniAl.BLOCK * 2];
        long lastReport = System.nanoTime();
        long worst = 0;
        int underruns = -1;
        while (running) {
            synchronized (pauseLock) {
                while (paused && running) {
                    try {
                        pauseLock.wait();
                    } catch (InterruptedException e) {
                        return;
                    }
                }
            }
            long t0 = System.nanoTime();
            al.render(buf, MiniAl.BLOCK);
            long took = System.nanoTime() - t0;
            worst = Math.max(worst, took);
            AudioTrack t = track;
            if (t == null) {
                return;
            }
            t.write(buf, 0, buf.length, AudioTrack.WRITE_BLOCKING);
            // the phone ran dry since last time: give it one burst more of cushion (up to the capacity)
            try {
                int u = t.getUnderrunCount();
                if (underruns >= 0 && u > underruns) {
                    int size = t.getBufferSizeInFrames();
                    if (size + burst <= t.getBufferCapacityInFrames()) {
                        t.setBufferSizeInFrames(size + burst);
                        Log.i(TAG, "underrun: buffer now " + t.getBufferSizeInFrames() + " frames");
                    }
                }
                underruns = u;
            } catch (Exception ignored) {
                // an old phone that cannot say
            }
            // a phone that cannot keep up: shorten the HRTF filters a little rather than crackle
            long now = System.nanoTime();
            if (now - lastReport > 1_000_000_000L) {
                double budget = MiniAl.BLOCK * 1e9 / MiniAl.SAMPLE_RATE;    // ns available per render
                if (worst > budget * 0.6 && al.getTapLimit() > 64) {
                    al.setTapLimit(al.getTapLimit() - 16);
                } else if (worst < budget * 0.25 && al.getTapLimit() < Hrtf.TAPS) {
                    al.setTapLimit(al.getTapLimit() + 8);
                }
                worst = 0;
                lastReport = now;
            }
        }
    }
}
