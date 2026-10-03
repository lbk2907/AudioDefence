package com.audiodefence;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.PendingIntent;
import android.content.ActivityNotFoundException;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageInstaller;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.hardware.display.DisplayManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.speech.tts.TextToSpeech;
import android.util.Log;
import android.view.Display;
import android.view.Surface;

import com.audiodefence.audio.AudioOut;
import com.audiodefence.audio.MiniAl;
import com.audiodefence.audio.SoundDecoder;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.Collator;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

/**
 * Everything the Python half of the game asks the phone for: the mixer, decoding, speech, the touch events,
 * the motion sensors, and the network and Android's installer for updating.  Python reaches it as
 * com.audiodefence.Bridge.get().
 */
public final class Bridge implements SensorEventListener {
    private static final String TAG = "AudioDefence";
    private static Bridge instance;

    public final MiniAl al;
    private final Context context;
    private final AudioOut audio;
    private final Map<String, int[]> decoded = new HashMap<>();
    private final ConcurrentLinkedQueue<float[]> events = new ConcurrentLinkedQueue<>();
    private volatile boolean quit;
    private volatile Runnable onEnded;

    // speech: the first speech, which says everything unless the second is used, and the second (PORT ADDITION,
    // Settings > Speech > Use second speech, user request, 2026-10-03), which then reads the story, the tutorial
    // and what is said during a game.  Each is a TextToSpeech of its own, with its own engine, rate, pitch and
    // volume.  The second is only its settings until it is first asked to speak: its TextToSpeech is made then.
    private final Voice first = new Voice("ad");
    private final Voice second = new Voice("ad2-");
    private final Handler main = new Handler(Looper.getMainLooper());
    /** How long a chosen engine has to start before the phone's default takes its place. */
    private static final long ENGINE_START_LIMIT_MS = 10000;

    // screen and sensors
    private volatile float widthDp = 800f;
    private volatile float heightDp = 360f;
    private final float[] up = {0f, 0f, 1f};
    private double yawAccum;
    private long lastGyroNs;
    private final Object sensorLock = new Object();
    private SensorManager sensors;
    private boolean hasGravitySensor;
    // shake: two hard jolts within 0.6 s, like the shake the iPhone reports
    private long firstJoltNs;
    private long lastShakeNs;
    private boolean shaken;
    // PORT ADDITION (Settings > Controls > Shake sensitivity): 0 off, 1 needs a hard shake, 10 a light one
    private volatile double shakeThreshold = 11.2;
    private volatile boolean shakeTwoJolts = false;
    private volatile boolean shakeOff = false;

    // updating (platform/updater_android.py)
    private static final String INSTALL_STATUS = "com.audiodefence.INSTALL_STATUS";
    private volatile Activity activity;
    private volatile boolean foreground = true;
    private volatile long downloadDone;
    private volatile long downloadTotal;
    private volatile boolean downloadCancelled;
    private volatile String installState = "";
    private volatile int installSession = -1;
    private BroadcastReceiver installReceiver;

    public static synchronized Bridge get() {
        if (instance == null) {
            throw new IllegalStateException("Bridge.init has not been called");
        }
        return instance;
    }

    public static synchronized Bridge init(Context appContext) {
        if (instance == null) {
            instance = new Bridge(appContext.getApplicationContext());
        }
        return instance;
    }

    private Bridge(Context ctx) {
        this.context = ctx;
        MiniAl.SAMPLE_RATE = AudioOut.nativeRate(ctx);
        MiniAl mixer;
        try {
            mixer = new MiniAl(readAsset("hrtf/audiodefence_ircam1050.mhr"));
        } catch (Exception e) {
            throw new RuntimeException("cannot load the game's HRTF", e);
        }
        this.al = mixer;
        this.audio = new AudioOut(mixer);
        audio.start(ctx);
        first.start("");
        startSensors();
    }

    private byte[] readAsset(String name) throws java.io.IOException {
        try (InputStream in = context.getAssets().open(name)) {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[16384];
            int n;
            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
            }
            return out.toByteArray();
        }
    }

    // ------------------------------------------------------------------------------------ lifecycle
    public void setOnEnded(Runnable r) {
        onEnded = r;
    }

    /** Python: the game has ended (Quit, or the loop stopped). */
    public void gameEnded() {
        Runnable r = onEnded;
        if (r != null) {
            r.run();
        }
    }

    public boolean shouldQuit() {
        return quit;
    }

    public void requestQuit() {
        quit = true;
    }

    /** MainActivity: the activity Android's settings and install screens are opened from, or null. */
    public void setActivity(Activity a) {
        activity = a;
    }

    public void appPaused() {
        foreground = false;
        events.add(new float[]{10, 0, 0, 0, 0});
        audio.setPaused(true);
        if (sensors != null) {
            sensors.unregisterListener(this);
        }
    }

    public void appResumed() {
        foreground = true;
        events.add(new float[]{11, 0, 0, 0, 0});
        audio.setPaused(false);
        startSensors();
        first.applySettings();                          // the phone's own speed may have changed meanwhile
        second.applySettings();
    }

    public void shutdown() {
        quit = true;
        audio.stop();
        main.removeCallbacksAndMessages(null);          // no engine start or time limit left to run
        first.shutdown();
        second.shutdown();
        if (sensors != null) {
            sensors.unregisterListener(this);
        }
    }

    // ------------------------------------------------------------------------------------ input
    public void postTouch(int type, int pointerId, float xDp, float yDp) {
        events.add(new float[]{type, pointerId, xDp, yDp, 0});
    }

    public void postBack() {
        events.add(new float[]{20, 0, 0, 0, 0});
    }

    public void setScreen(float wDp, float hDp) {
        widthDp = wDp;
        heightDp = hDp;
    }

    public float screenWidthDp() {
        return widthDp;
    }

    public float screenHeightDp() {
        return heightDp;
    }

    /** Python: all the events since the last call, as groups of five numbers. */
    public float[] pollEvents() {
        int n = events.size();
        if (n == 0) {
            return new float[0];
        }
        float[] out = new float[n * 5];
        int k = 0;
        float[] e;
        while (k < out.length && (e = events.poll()) != null) {
            System.arraycopy(e, 0, out, k, 5);
            k += 5;
        }
        if (k < out.length) {
            float[] cut = new float[k];
            System.arraycopy(out, 0, cut, 0, k);
            return cut;
        }
        return out;
    }

    // ------------------------------------------------------------------------------------ decoding
    /** Python: {handle, frames, channels, rate}, or {-1, 0, 0, 0} when the file cannot be decoded. */
    public int[] decode(String path) {
        synchronized (decoded) {
            int[] hit = decoded.get(path);
            if (hit != null) {
                return hit;
            }
        }
        try {
            MiniAl.Decoded d = SoundDecoder.decode(path);
            int handle = al.register(d);
            int[] info = {handle, d.frames, d.channels, d.rate};
            synchronized (decoded) {
                decoded.put(path, info);
            }
            return info;
        } catch (Throwable t) {
            Log.e(TAG, "cannot decode " + path, t);
            return new int[]{-1, 0, 0, 0};
        }
    }

    public float leadIn(int handle, float floor, float most) {
        return al.leadIn(handle, floor, most);
    }

    // ------------------------------------------------------------------------------------ speech
    /**
     * One text-to-speech voice: a TextToSpeech with its own engine, rate, pitch and volume.  The game has two,
     * `first` and `second` (see their declaration); the second is made only once it is first asked to speak.
     * spokenBeforeReady is also the lock for tts, ready and the engine fields.
     */
    private final class Voice {
        private final String prefix;                    // of its utterance ids, and of its lines in the log
        private TextToSpeech tts;
        private volatile boolean ready;
        private boolean begun;                          // whether a TextToSpeech has been asked for yet
        private final List<Object[]> spokenBeforeReady = new ArrayList<>();
        private volatile int rateSetting = 0;
        private volatile int pitchSetting = 0;
        private volatile int volumeSetting = 100;
        private int utterance;
        // PORT ADDITION (Settings > Speech > Android speech engine, user request): the engine Python asked for,
        // by package ("" is the one set in the phone's settings), and the one started for it - "" too when the
        // one asked for is not installed or would not start.  Each start of the speech is numbered, so that a
        // late answer from an engine already replaced is ignored.  The starts are made on the main thread.
        private String engineAsked = "";
        private volatile String engineInUse = "";
        private int speechStart;
        private int readyStart;

        Voice(String prefix) {
            this.prefix = prefix;
        }

        /**
         * Start the text-to-speech engine with this package, or the phone's default for "" - on the main
         * thread.  Until it has started, what the game says waits in spokenBeforeReady, as it always did at
         * start-up.
         */
        void start(String engine) {
            if (!engine.isEmpty() && !engineInstalled(engine)) {
                Log.w(TAG, "speech engine " + engine + " is not installed; the phone's default speaks instead");
                forgetEngine(engine);
                engine = "";
            }
            TextToSpeech old;
            final int start;
            synchronized (spokenBeforeReady) {
                begun = true;
                ready = false;
                old = tts;
                tts = null;
                start = ++speechStart;
            }
            if (old != null) {
                try {
                    old.stop();
                    old.shutdown();
                } catch (RuntimeException e) {
                    Log.w(TAG, "the last speech engine would not shut down", e);
                }
            }
            engineInUse = engine;
            final String using = engine;
            // Its answer is handled on the next pass of the main thread, after the constructor has returned: a
            // TextToSpeech that cannot bind to anything answers from inside its constructor.
            TextToSpeech.OnInitListener listener = status -> main.post(() -> started(start, using, status));
            TextToSpeech made = null;
            try {
                // With a package, Android itself falls back to the default engine when that one cannot be bound.
                made = engine.isEmpty() ? new TextToSpeech(context, listener)
                        : new TextToSpeech(context, listener, engine);
            } catch (RuntimeException e) {
                Log.e(TAG, "text-to-speech could not be made for " + (engine.isEmpty() ? "the default" : engine), e);
            }
            synchronized (spokenBeforeReady) {
                if (start == speechStart) {
                    tts = made;
                } else if (made != null) {
                    made.shutdown();                    // replaced while it was being made
                }
            }
            if (!using.isEmpty()) {
                main.postDelayed(() -> {
                    boolean waiting;
                    synchronized (spokenBeforeReady) {
                        waiting = start == speechStart && readyStart != start;
                    }
                    if (waiting) {
                        Log.w(TAG, "speech engine " + using + " did not start in time");
                        engineFailed(using);
                    }
                }, ENGINE_START_LIMIT_MS);
            } else if (made == null) {
                Log.e(TAG, "text-to-speech could not start");
            }
        }

        /** The answer of the engine of one start, on the main thread. */
        private void started(int start, String engine, int status) {
            TextToSpeech t;
            synchronized (spokenBeforeReady) {
                if (start != speechStart) {
                    return;                             // a later start has replaced this engine
                }
                t = tts;
            }
            if (status != TextToSpeech.SUCCESS || t == null) {
                Log.e(TAG, "text-to-speech could not start: " + status + (engine.isEmpty() ? "" : " (" + engine + ")"));
                if (!engine.isEmpty()) {
                    engineFailed(engine);
                }
                return;
            }
            speakTheLanguage(t);                        // and with it the engine's own voice for that language
            List<Object[]> waiting;
            synchronized (spokenBeforeReady) {
                if (start != speechStart) {
                    return;
                }
                readyStart = start;
                ready = true;
                waiting = new ArrayList<>(spokenBeforeReady);
                spokenBeforeReady.clear();
            }
            applySettings();
            for (Object[] w : waiting) {
                speak((String) w[0], (Boolean) w[1]);
            }
        }

        /** A chosen engine that would not start: the phone's default takes its place, so the game keeps speaking. */
        private void engineFailed(String engine) {
            forgetEngine(engine);
            start("");
        }

        /** The engine asked for could not be had: what is asked for is now what speaks, the phone's default. */
        private void forgetEngine(String engine) {
            synchronized (spokenBeforeReady) {
                if (engine.equals(engineAsked)) {
                    engineAsked = "";
                }
            }
        }

        /** The rate and pitch, on the engine speaking; the volume goes with each line (speak). */
        void applySettings() {
            TextToSpeech t;
            synchronized (spokenBeforeReady) {
                if (!ready || tts == null) {
                    return;
                }
                t = tts;
            }
            try {
                t.setSpeechRate(phoneSpeechRate() * (float) Math.pow(RATE_STEP, rateSetting));
                t.setPitch((float) Math.pow(1.05, pitchSetting));
            } catch (RuntimeException e) {
                Log.w(TAG, "could not apply the speech settings", e);
            }
        }

        boolean speak(String text, boolean interrupt) {
            if (text == null || text.isEmpty()) {
                return false;
            }
            TextToSpeech t;
            final String engine;
            boolean beginNow = false;
            synchronized (spokenBeforeReady) {
                if (!ready || tts == null) {
                    spokenBeforeReady.add(new Object[]{text, interrupt});
                    if (!begun) {                       // the second speech's first line: it is made now
                        begun = true;
                        beginNow = true;
                    }
                    engine = engineAsked;
                    t = null;
                } else {
                    t = tts;
                    engine = null;
                }
            }
            if (t == null) {
                if (beginNow) {
                    main.post(() -> start(engine));
                }
                return true;
            }
            Bundle params = new Bundle();
            params.putFloat(TextToSpeech.Engine.KEY_PARAM_VOLUME, Math.max(0f, Math.min(1f, volumeSetting / 100f)));
            int mode = interrupt ? TextToSpeech.QUEUE_FLUSH : TextToSpeech.QUEUE_ADD;
            return t.speak(text, mode, params, prefix + (utterance++)) == TextToSpeech.SUCCESS;
        }

        void stop() {
            TextToSpeech t;
            synchronized (spokenBeforeReady) {
                spokenBeforeReady.clear();
                t = ready ? tts : null;
            }
            if (t != null) {
                t.stop();
            }
        }

        void configure(int rate, int pitch, int volume) {
            rateSetting = rate;
            pitchSetting = pitch;
            volumeSetting = volume;
            if (ready) {
                applySettings();
            }
        }

        boolean isReady() {
            return ready;
        }

        /**
         * Speak with the engine of this package from now on, or with the one set in the phone's settings for "".
         * The engine in use is shut down and the new one started; until it has, what is said waits for it.  A
         * voice not made yet only remembers it, for when it is.
         */
        void setEngine(String engine) {
            final String want = engine == null ? "" : engine;
            synchronized (spokenBeforeReady) {
                if (want.equals(engineAsked)) {
                    return;
                }
                engineAsked = want;
                if (!begun) {
                    return;
                }
                ready = false;                          // from now on what is said waits for the new engine
            }
            main.post(() -> start(want));
        }

        String engine() {
            return engineInUse;
        }

        /** The TextToSpeech speaking now, or null between two engines or before one is made. */
        TextToSpeech current() {
            synchronized (spokenBeforeReady) {
                return tts;
            }
        }

        void shutdown() {
            TextToSpeech t;
            synchronized (spokenBeforeReady) {
                t = tts;
                tts = null;
                ready = false;
                speechStart++;
            }
            if (t != null) {
                t.stop();
                t.shutdown();
            }
        }
    }

    /**
     * The phone's language, or US English when the engine has not got it - and with it the engine's own voice:
     * setLanguage puts the voice the engine's settings give that language (getDefaultVoiceNameFor).  Every
     * start of an engine does this, and nothing here chooses another voice (user request, 2026-10-02: the
     * player chooses the engine, and each engine speaks with the voice set in its own settings on the phone).
     */
    private static void speakTheLanguage(TextToSpeech t) {
        int r = t.setLanguage(Locale.getDefault());
        if (r == TextToSpeech.LANG_MISSING_DATA || r == TextToSpeech.LANG_NOT_SUPPORTED) {
            t.setLanguage(Locale.US);
        }
    }

    /** How much one step of the Speech tab's rate changes the speed: ten steps up from the phone's own speed
     *  is six times as fast, the most Android's own speech-rate setting offers (and ten down, a sixth). */
    private static final double RATE_STEP = Math.pow(6.0, 1.0 / 10.0);

    /** The speed set in the phone's text-to-speech settings, 1 being normal.  An app that sets a rate
     *  replaces that speed rather than adding to it, so the Speech tab's rate starts from it: 0 is the
     *  speed the player already listens at.  Read again whenever the rate is applied, the game coming back
     *  to the front among them, so a change made there is taken up. */
    private float phoneSpeechRate() {
        try {
            int percent = Settings.Secure.getInt(context.getContentResolver(), Settings.Secure.TTS_DEFAULT_RATE, 100);
            return percent > 0 ? percent / 100f : 1f;
        } catch (RuntimeException e) {
            return 1f;
        }
    }

    // --- the first speech: what Python and MainActivity have always called
    public boolean speak(String text, boolean interrupt) {
        return first.speak(text, interrupt);
    }

    public void stopSpeech() {
        first.stop();
    }

    /** Python: the Speech tab's rate and pitch (-10 to 10) and volume (0 to 100), for whichever engine speaks. */
    public void configureSpeech(int rate, int pitch, int volume) {
        first.configure(rate, pitch, volume);
    }

    public boolean speechReady() {
        return first.isReady();
    }

    /**
     * Python: speak with the engine of this package from now on, or with the one set in the phone's settings
     * for "".  The engine in use is shut down and the new one started; until it has, what is said waits for
     * it.  One that is not installed, does not start or takes too long gives way to the phone's default.
     */
    public void setSpeechEngine(String engine) {
        first.setEngine(engine);
    }

    /** Python: the package of the engine started for what was asked, or "" for the phone's default. */
    public String speechEngine() {
        return first.engine();
    }

    // --- the second speech (PORT ADDITION, user request, 2026-10-03): the same, for its own TextToSpeech
    public boolean speakSecond(String text, boolean interrupt) {
        return second.speak(text, interrupt);
    }

    public void stopSecondSpeech() {
        second.stop();
    }

    public void configureSecondSpeech(int rate, int pitch, int volume) {
        second.configure(rate, pitch, volume);
    }

    /** False until the second speech has been made, which its first line does. */
    public boolean secondSpeechReady() {
        return second.isReady();
    }

    public void setSecondSpeechEngine(String engine) {
        second.setEngine(engine);
    }

    public String secondSpeechEngine() {
        return second.engine();
    }

    /**
     * Python: "package\tname" per line, for the phone's text-to-speech engines (TextToSpeech.getEngines),
     * by name.
     */
    public String engineList() {
        StringBuilder sb = new StringBuilder();
        try {
            List<String[]> list = installedEngines();
            final Collator collator = Collator.getInstance();
            Collections.sort(list, (a, b) -> collator.compare(a[1], b[1]));
            for (String[] e : list) {
                sb.append(e[0]).append('\t').append(e[1]).append('\n');
            }
        } catch (RuntimeException e) {
            Log.w(TAG, "engine list failed", e);
        }
        return sb.toString();
    }

    /** {package, name} of each text-to-speech engine on the phone. */
    private List<String[]> installedEngines() {
        List<String[]> out = new ArrayList<>();
        TextToSpeech t = first.current();
        if (t == null) {
            t = second.current();
        }
        if (t != null) {
            for (TextToSpeech.EngineInfo e : t.getEngines()) {
                out.add(new String[]{e.name, oneLine(e.label == null || e.label.isEmpty() ? e.name : e.label)});
            }
            return out;
        }
        // between two engines, or when none could be made: ask Android as getEngines does
        PackageManager pm = context.getPackageManager();
        Intent intent = new Intent(TextToSpeech.Engine.INTENT_ACTION_TTS_SERVICE);
        for (ResolveInfo ri : pm.queryIntentServices(intent, PackageManager.MATCH_DEFAULT_ONLY)) {
            if (ri.serviceInfo != null) {
                CharSequence label = ri.loadLabel(pm);
                String name = ri.serviceInfo.packageName;
                out.add(new String[]{name, oneLine(label == null || label.length() == 0 ? name : label.toString())});
            }
        }
        return out;
    }

    private boolean engineInstalled(String engine) {
        try {
            for (String[] e : installedEngines()) {
                if (e[0].equals(engine)) {
                    return true;
                }
            }
        } catch (RuntimeException e) {
            Log.w(TAG, "could not list the speech engines", e);
            return true;                                // let TextToSpeech find out
        }
        return false;
    }

    /** A name as one field of a line: no tab or line break in it. */
    private static String oneLine(String s) {
        return s == null ? "" : s.replace('\t', ' ').replace('\n', ' ').replace('\r', ' ').trim();
    }

    // ------------------------------------------------------------------------------------ updating
    // The network is done here rather than in Python because HttpURLConnection trusts the phone's own
    // certificates, and the Python inside the app may have none to check GitHub's against.  Each call is made
    // from a Python worker thread and blocks it; none of them is ever made on the UI thread.

    /** Python: "status\ntext" for a GET of the address, or "0\nwhat went wrong" when nothing answered. */
    public String fetchText(String address, String accept, String userAgent, int timeoutMs) {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(address).openConnection();
            c.setConnectTimeout(timeoutMs);
            c.setReadTimeout(timeoutMs);
            c.setRequestProperty("Accept", accept);
            c.setRequestProperty("User-Agent", userAgent);
            int code = c.getResponseCode();
            if (code != HttpURLConnection.HTTP_OK) {
                return code + "\n";
            }
            try (InputStream in = c.getInputStream()) {
                ByteArrayOutputStream out = new ByteArrayOutputStream();
                byte[] buf = new byte[16384];
                int n;
                while ((n = in.read(buf)) > 0) {
                    out.write(buf, 0, n);
                }
                return code + "\n" + new String(out.toByteArray(), StandardCharsets.UTF_8);
            }
        } catch (Exception e) {
            Log.w(TAG, "could not fetch " + address, e);
            return "0\n" + e;
        } finally {
            if (c != null) {
                c.disconnect();
            }
        }
    }

    /**
     * Python: fetch the address into the file at path, following GitHub's redirect to where the file is kept.
     * "" when it is all there, "cancelled", "http " and the status, or "error " and what went wrong.  How far
     * it has got is downloadProgress(), read from another thread while this one works.
     */
    public String download(String address, String path, String userAgent, int timeoutMs) {
        downloadDone = 0;
        downloadTotal = 0;
        downloadCancelled = false;
        HttpURLConnection c = null;
        try {
            File target = new File(path);
            File parent = target.getParentFile();
            if (parent != null && !parent.isDirectory() && !parent.mkdirs()) {
                return "error cannot create " + parent;
            }
            c = (HttpURLConnection) new URL(address).openConnection();
            c.setConnectTimeout(timeoutMs);
            c.setReadTimeout(timeoutMs);
            c.setRequestProperty("User-Agent", userAgent);
            int code = c.getResponseCode();
            if (code != HttpURLConnection.HTTP_OK) {
                return "http " + code;
            }
            downloadTotal = Math.max(0L, c.getContentLengthLong());
            try (InputStream in = c.getInputStream(); OutputStream out = new FileOutputStream(target)) {
                byte[] buf = new byte[65536];
                int n;
                while ((n = in.read(buf)) > 0) {
                    if (downloadCancelled) {
                        return "cancelled";
                    }
                    out.write(buf, 0, n);
                    downloadDone += n;
                }
            }
            return downloadCancelled ? "cancelled" : "";
        } catch (Exception e) {
            Log.w(TAG, "could not download " + address, e);
            return "error " + e;
        } finally {
            if (c != null) {
                c.disconnect();
            }
        }
    }

    public void cancelDownload() {
        downloadCancelled = true;
    }

    /** Python: {bytes so far, bytes in all (0 when the server did not say)}. */
    public long[] downloadProgress() {
        return new long[]{downloadDone, downloadTotal};
    }

    /** Python: whether the player has let this app install apps (Install unknown apps, Android 8 and later). */
    public boolean canInstallPackages() {
        return context.getPackageManager().canRequestPackageInstalls();
    }

    /** Python: open Install unknown apps for this app.  False when the phone has no such screen. */
    public boolean openInstallSettings() {
        return launch(new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES,
                Uri.parse("package:" + context.getPackageName())));
    }

    /** Python: whether the game is on the screen, rather than Android's settings or installer over it. */
    public boolean inForeground() {
        return foreground;
    }

    /** Python: where installApk has got to: "", "preparing", "confirm", "done", "aborted" or "failed\nstatus\nwhy". */
    public String installState() {
        return installState;
    }

    /**
     * Python: hand the APK at path to Android's PackageInstaller, which asks the player to confirm on a screen
     * of its own and then replaces the app, closing it.  A session rather than a file handed to the installer by
     * URI: it needs no FileProvider, and so no AndroidX library and no provider in the manifest, and its result
     * comes back to installReceiver - "aborted" when the player says no - so the game can say so.
     */
    public void installApk(String path) {
        installState = "preparing";
        new Thread(() -> {
            try {
                commitInstall(new File(path));
            } catch (Exception e) {
                Log.e(TAG, "could not hand the update to Android", e);
                installState = "failed\n-1\n" + e.getMessage();
            }
        }, "install").start();
    }

    @SuppressLint("UnspecifiedImmutableFlag")         // mutable from Android 12 on; before it there is no flag
    private void commitInstall(File apk) throws IOException {
        listenForInstall();
        PackageInstaller installer = context.getPackageManager().getPackageInstaller();
        PackageInstaller.SessionParams params =
                new PackageInstaller.SessionParams(PackageInstaller.SessionParams.MODE_FULL_INSTALL);
        params.setAppPackageName(context.getPackageName());
        params.setSize(apk.length());
        int id = installer.createSession(params);
        installSession = id;
        boolean committed = false;
        try (PackageInstaller.Session session = installer.openSession(id)) {
            try (InputStream in = new FileInputStream(apk);
                 OutputStream out = session.openWrite("base.apk", 0, apk.length())) {
                byte[] buf = new byte[65536];
                int n;
                while ((n = in.read(buf)) > 0) {
                    out.write(buf, 0, n);
                }
                session.fsync(out);
            }
            // The status comes back by broadcast, to this app alone.  It has to be mutable from Android 12 on,
            // so that the installer can fill in the status, and so explicit (setPackage) from Android 14 on.
            Intent status = new Intent(INSTALL_STATUS).setPackage(context.getPackageName());
            int flags = PendingIntent.FLAG_UPDATE_CURRENT;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                flags |= PendingIntent.FLAG_MUTABLE;
            }
            session.commit(PendingIntent.getBroadcast(context, id, status, flags).getIntentSender());
            committed = true;
        } finally {
            if (!committed) {
                try {
                    installer.abandonSession(id);
                } catch (RuntimeException ignored) {
                    // already gone
                }
            }
        }
    }

    @SuppressLint("UnspecifiedRegisterReceiverFlag")  // the flag is Android 13's, and is given from then on
    private synchronized void listenForInstall() {
        if (installReceiver != null) {
            return;
        }
        installReceiver = new BroadcastReceiver() {
            @Override
            public void onReceive(Context c, Intent intent) {
                installStatus(intent);
            }
        };
        IntentFilter filter = new IntentFilter(INSTALL_STATUS);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            context.registerReceiver(installReceiver, filter, Context.RECEIVER_NOT_EXPORTED);
        } else {
            context.registerReceiver(installReceiver, filter);
        }
    }

    @SuppressWarnings("deprecation")                 // getParcelableExtra(String): the typed one is Android 13's
    private void installStatus(Intent intent) {
        // Before Android 13 the receiver cannot be closed to other apps, so only the session handed over is
        // listened to, and only a status that names it can open a screen.
        int session = intent.getIntExtra(PackageInstaller.EXTRA_SESSION_ID, -2);
        if (session != installSession && session != -2) {
            return;
        }
        int status = intent.getIntExtra(PackageInstaller.EXTRA_STATUS, PackageInstaller.STATUS_FAILURE);
        if (status == PackageInstaller.STATUS_PENDING_USER_ACTION) {
            if (session != installSession) {
                return;
            }
            Intent confirm = intent.getParcelableExtra(Intent.EXTRA_INTENT);
            installState = "confirm";
            if (confirm == null || !launch(confirm)) {
                installState = "failed\n" + status + "\nAndroid's install screen could not be opened";
            }
        } else if (status == PackageInstaller.STATUS_SUCCESS) {
            installState = "done";
        } else if (status == PackageInstaller.STATUS_FAILURE_ABORTED) {
            installState = "aborted";
        } else {
            String why = intent.getStringExtra(PackageInstaller.EXTRA_STATUS_MESSAGE);
            installState = "failed\n" + status + "\n" + (why == null ? "" : why);
        }
    }

    /** Open one of Android's screens over the game, from the game's activity, on the UI thread. */
    private boolean launch(Intent intent) {
        Activity a = activity;
        if (a == null) {
            try {
                context.startActivity(intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
                return true;
            } catch (ActivityNotFoundException | SecurityException e) {
                Log.w(TAG, "could not open " + intent, e);
                return false;
            }
        }
        final boolean[] opened = {false};
        CountDownLatch done = new CountDownLatch(1);
        a.runOnUiThread(() -> {
            try {
                a.startActivity(intent);
                opened[0] = true;
            } catch (ActivityNotFoundException | SecurityException e) {
                Log.w(TAG, "could not open " + intent, e);
            } finally {
                done.countDown();
            }
        });
        try {
            if (!done.await(5, TimeUnit.SECONDS)) {
                return true;                             // the UI thread is busy; it was asked to
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        return opened[0];
    }

    // ------------------------------------------------------------------------------------ sensors
    private void startSensors() {
        if (sensors == null) {
            sensors = (SensorManager) context.getSystemService(Context.SENSOR_SERVICE);
        }
        if (sensors == null) {
            return;
        }
        Sensor gyro = sensors.getDefaultSensor(Sensor.TYPE_GYROSCOPE);
        Sensor grav = sensors.getDefaultSensor(Sensor.TYPE_GRAVITY);
        Sensor accel = sensors.getDefaultSensor(Sensor.TYPE_ACCELEROMETER);
        hasGravitySensor = grav != null;
        lastGyroNs = 0;
        firstJoltNs = 0;
        if (gyro != null) {
            sensors.registerListener(this, gyro, SensorManager.SENSOR_DELAY_GAME);
        }
        if (grav != null) {
            sensors.registerListener(this, grav, SensorManager.SENSOR_DELAY_GAME);
        }
        if (accel != null) {                           // for the shake, and for "up" when there is no gravity sensor
            sensors.registerListener(this, accel, SensorManager.SENSOR_DELAY_GAME);
        }
    }

    @Override
    public void onSensorChanged(SensorEvent e) {
        int type = e.sensor.getType();
        synchronized (sensorLock) {
            if (type == Sensor.TYPE_ACCELEROMETER) {
                detectShake(e);
            }
            if (type == Sensor.TYPE_GRAVITY || (type == Sensor.TYPE_ACCELEROMETER && !hasGravitySensor)) {
                float x = e.values[0], y = e.values[1], z = e.values[2];
                float n = (float) Math.sqrt(x * x + y * y + z * z);
                if (n > 0.1f) {
                    // (a plain accelerometer is smoothed; the gravity sensor already is)
                    float a = type == Sensor.TYPE_GRAVITY ? 1f : 0.1f;
                    up[0] += a * (x / n - up[0]);
                    up[1] += a * (y / n - up[1]);
                    up[2] += a * (z / n - up[2]);
                }
            } else if (type == Sensor.TYPE_GYROSCOPE) {
                if (lastGyroNs != 0) {
                    double dt = (e.timestamp - lastGyroNs) * 1e-9;
                    float un = (float) Math.sqrt(up[0] * up[0] + up[1] * up[1] + up[2] * up[2]);
                    if (un > 0.1f && dt > 0 && dt < 0.5) {
                        // spin about the direction of "up" is a turn of the head, whichever way the phone is held
                        double rate = (e.values[0] * up[0] + e.values[1] * up[1] + e.values[2] * up[2]) / un;
                        yawAccum += rate * dt;
                    }
                }
                lastGyroNs = e.timestamp;
            }
        }
    }

    /** Python: Settings > Controls > Shake sensitivity, 0 (off) to 10 (the lightest shake). */
    public void setShakeSensitivity(int level) {
        level = Math.max(0, Math.min(10, level));
        shakeOff = level == 0;
        // 1 -> 20.2 m/s2 beyond gravity, 5 -> 13 (the first builds), 10 -> 4; taps on the screen stay under 4
        shakeThreshold = 22.0 - 1.8 * level;
        // the harder settings want two jolts, as the iPhone's shake does; from 6 up one quick jolt is enough
        shakeTwoJolts = level <= 5;
    }

    private void detectShake(SensorEvent e) {
        if (shakeOff) {
            return;
        }
        float x = e.values[0], y = e.values[1], z = e.values[2];
        double jolt = Math.abs(Math.sqrt(x * x + y * y + z * z) - 9.81);
        if (jolt < shakeThreshold) {
            return;
        }
        long t = e.timestamp;
        if (t - lastShakeNs < 600_000_000L) {           // one swing per shake
            return;
        }
        if (!shakeTwoJolts) {
            shaken = true;
            lastShakeNs = t;
            firstJoltNs = 0;
            return;
        }
        if (firstJoltNs != 0 && t - firstJoltNs < 600_000_000L && t - firstJoltNs > 60_000_000L) {
            shaken = true;
            lastShakeNs = t;
            firstJoltNs = 0;
        } else if (firstJoltNs == 0 || t - firstJoltNs >= 600_000_000L) {
            firstJoltNs = t;
        }
    }

    /** Python: whether the phone was shaken since the last call. */
    public boolean takeShake() {
        synchronized (sensorLock) {
            boolean s = shaken;
            shaken = false;
            return s;
        }
    }

    @Override
    public void onAccuracyChanged(Sensor sensor, int accuracy) {
    }

    /** Python: radians turned since the last call (negative to the right, as the original's yaw). */
    public double takeYaw() {
        synchronized (sensorLock) {
            double v = yawAccum;
            yawAccum = 0;
            return v;
        }
    }

    /** Which way up the screen is, from the display manager's default display - which, unlike the window
     *  manager's (deprecated in Android 11) or a Context's own display (a screen's Context only, and this is
     *  the application's), answers on every Android the app runs on.  Sideways with the top to the left if it
     *  will not say. */
    private int screenRotation() {
        try {
            DisplayManager displays = (DisplayManager) context.getSystemService(Context.DISPLAY_SERVICE);
            Display display = displays != null ? displays.getDisplay(Display.DEFAULT_DISPLAY) : null;
            if (display != null) {
                return display.getRotation();
            }
        } catch (RuntimeException ignored) {
            // keep the default
        }
        return Surface.ROTATION_90;
    }

    /** Python: how far the phone is rolled like a steering wheel, in radians (positive to the right). */
    public double tiltAngle() {
        float ux, uy;
        synchronized (sensorLock) {
            ux = up[0];
            uy = up[1];
        }
        int rotation = screenRotation();
        // the screen's own "up" and "right" in the device's axes
        float sUp = rotation == Surface.ROTATION_270 ? -ux : ux;
        float sRight = rotation == Surface.ROTATION_270 ? uy : -uy;
        return -Math.atan2(sRight, sUp);
    }
}
