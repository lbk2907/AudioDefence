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
import android.hardware.Sensor;
import android.hardware.SensorEvent;
import android.hardware.SensorEventListener;
import android.hardware.SensorManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.Settings;
import android.speech.tts.TextToSpeech;
import android.speech.tts.Voice;
import android.util.Log;
import android.view.Surface;
import android.view.WindowManager;

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
import java.util.ArrayList;
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

    // speech
    private TextToSpeech tts;
    private volatile boolean ttsReady;
    private final List<Object[]> spokenBeforeReady = new ArrayList<>();
    private String wantedVoice = "";
    private int rateSetting = 0;
    private int pitchSetting = 0;
    private int volumeSetting = 100;
    private int utterance;

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
        startSpeech();
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
    }

    public void shutdown() {
        quit = true;
        audio.stop();
        if (tts != null) {
            tts.stop();
            tts.shutdown();
        }
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
    private void startSpeech() {
        tts = new TextToSpeech(context, status -> {
            if (status != TextToSpeech.SUCCESS) {
                Log.e(TAG, "text-to-speech could not start: " + status);
                return;
            }
            int r = tts.setLanguage(Locale.getDefault());
            if (r == TextToSpeech.LANG_MISSING_DATA || r == TextToSpeech.LANG_NOT_SUPPORTED) {
                tts.setLanguage(Locale.US);
            }
            applySpeechSettings();
            List<Object[]> waiting;
            synchronized (spokenBeforeReady) {
                ttsReady = true;
                waiting = new ArrayList<>(spokenBeforeReady);
                spokenBeforeReady.clear();
            }
            for (Object[] w : waiting) {
                speak((String) w[0], (Boolean) w[1]);
            }
        });
    }

    private void applySpeechSettings() {
        if (tts == null) {
            return;
        }
        tts.setSpeechRate((float) Math.pow(1.12, rateSetting));
        tts.setPitch((float) Math.pow(1.05, pitchSetting));
        if (wantedVoice != null && !wantedVoice.isEmpty()) {
            try {
                for (Voice v : tts.getVoices()) {
                    if (v.getName().equals(wantedVoice)) {
                        tts.setVoice(v);
                        break;
                    }
                }
            } catch (Exception e) {
                Log.w(TAG, "could not choose voice " + wantedVoice, e);
            }
        }
    }

    public boolean speak(String text, boolean interrupt) {
        if (text == null || text.isEmpty()) {
            return false;
        }
        synchronized (spokenBeforeReady) {
            if (!ttsReady) {
                spokenBeforeReady.add(new Object[]{text, interrupt});
                return true;
            }
        }
        Bundle params = new Bundle();
        params.putFloat(TextToSpeech.Engine.KEY_PARAM_VOLUME, Math.max(0f, Math.min(1f, volumeSetting / 100f)));
        int mode = interrupt ? TextToSpeech.QUEUE_FLUSH : TextToSpeech.QUEUE_ADD;
        return tts.speak(text, mode, params, "ad" + (utterance++)) == TextToSpeech.SUCCESS;
    }

    public void stopSpeech() {
        synchronized (spokenBeforeReady) {
            spokenBeforeReady.clear();
        }
        if (tts != null && ttsReady) {
            tts.stop();
        }
    }

    /** Python: "id\tname" per line, for the voices in the phone's language. */
    public String voiceList() {
        StringBuilder sb = new StringBuilder();
        if (tts == null || !ttsReady) {
            return "";
        }
        try {
            String lang = Locale.getDefault().getLanguage();
            List<Voice> list = new ArrayList<>(tts.getVoices());
            java.util.Collections.sort(list, (a, b) -> a.getName().compareTo(b.getName()));
            for (Voice v : list) {
                if (v.getLocale().getLanguage().equals(lang) && !v.isNetworkConnectionRequired()) {
                    sb.append(v.getName()).append('\t').append(v.getName()).append(" (")
                            .append(v.getLocale().getDisplayName()).append(")\n");
                }
            }
        } catch (Exception e) {
            Log.w(TAG, "voice list failed", e);
        }
        return sb.toString();
    }

    public void configureSpeech(String voice, int rate, int pitch, int volume) {
        wantedVoice = voice;
        rateSetting = rate;
        pitchSetting = pitch;
        volumeSetting = volume;
        if (ttsReady) {
            applySpeechSettings();
        }
    }

    public boolean speechReady() {
        return ttsReady;
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

    /** Python: how far the phone is rolled like a steering wheel, in radians (positive to the right). */
    public double tiltAngle() {
        float ux, uy;
        synchronized (sensorLock) {
            ux = up[0];
            uy = up[1];
        }
        int rotation = Surface.ROTATION_90;
        try {
            WindowManager wm = (WindowManager) context.getSystemService(Context.WINDOW_SERVICE);
            rotation = wm.getDefaultDisplay().getRotation();
        } catch (Exception ignored) {
            // keep the default
        }
        // the screen's own "up" and "right" in the device's axes
        float sUp = rotation == Surface.ROTATION_270 ? -ux : ux;
        float sRight = rotation == Surface.ROTATION_270 ? uy : -uy;
        return -Math.atan2(sRight, sUp);
    }
}
