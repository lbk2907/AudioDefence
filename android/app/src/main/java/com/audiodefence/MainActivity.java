package com.audiodefence;

import android.app.Activity;
import android.content.res.AssetManager;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import android.view.KeyEvent;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.WindowManager;
import android.view.accessibility.AccessibilityManager;

import com.chaquo.python.Python;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

/**
 * Audio Defence for Android.  Opens the touch surface, unpacks the game's data the first time, then runs the
 * game (Python: audiodefence/android_main.py) on a thread of its own.
 */
public final class MainActivity extends Activity {
    private static final String TAG = "AudioDefence";
    private static final int DATA_VERSION = 2;           // raise it when the layout of the unpacked data changes

    private Bridge bridge;
    private boolean started;
    private int filesDone;
    private int filesTotal;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        setContentView(new TouchView(this));
        hideSystemBars();
        bridge = Bridge.init(this);
        bridge.setActivity(this);                        // Android's settings and installer open over it
        bridge.setOnEnded(() -> runOnUiThread(() -> {
            bridge.shutdown();
            finishAndRemoveTask();
            new Thread(() -> {
                try {
                    Thread.sleep(400);
                } catch (InterruptedException ignored) {
                    // leaving anyway
                }
                System.exit(0);
            }).start();
        }));
        if (!started) {
            started = true;
            new Thread(this::boot, "boot").start();
        }
    }

    /** The whole screen is the game's: the status and navigation bars hidden, a swipe from an edge showing them
     *  for a moment.  Android 11 and later have a controller for it; the flags before that were deprecated
     *  with its arrival, and are only used where there is no controller. */
    @SuppressWarnings("deprecation")
    private void hideSystemBars() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            getWindow().setDecorFitsSystemWindows(false);
            WindowInsetsController bars = getWindow().getInsetsController();
            if (bars != null) {
                bars.hide(WindowInsets.Type.statusBars() | WindowInsets.Type.navigationBars());
                bars.setSystemBarsBehavior(WindowInsetsController.BEHAVIOR_SHOW_TRANSIENT_BARS_BY_SWIPE);
            }
            return;
        }
        getWindow().getDecorView().setSystemUiVisibility(
                View.SYSTEM_UI_FLAG_LAYOUT_STABLE | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
                        | View.SYSTEM_UI_FLAG_FULLSCREEN | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY);
    }

    @Override
    public void onWindowFocusChanged(boolean hasFocus) {
        super.onWindowFocusChanged(hasFocus);
        if (hasFocus) {
            hideSystemBars();
        }
    }

    @Override
    protected void onDestroy() {
        if (bridge != null) {
            bridge.setActivity(null);
        }
        super.onDestroy();
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (bridge != null) {
            bridge.appPaused();
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (bridge != null && started) {
            bridge.appResumed();
        }
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        if (keyCode == KeyEvent.KEYCODE_BACK) {
            bridge.postBack();
            return true;
        }
        return super.onKeyDown(keyCode, event);
    }

    // ------------------------------------------------------------------------------------ start-up
    private void boot() {
        try {
            AccessibilityManager am = (AccessibilityManager) getSystemService(ACCESSIBILITY_SERVICE);
            if (am != null && am.isTouchExplorationEnabled()) {
                bridge.speak("TalkBack is on. The game speaks for itself and needs TalkBack turned off. "
                        + "Turn TalkBack off, then open the game again.", true);
            }
            File home = new File(getFilesDir(), "adhome");
            // The game's data is built into each APK from the repository it is made in, so it is unpacked
            // again whenever the app has been installed or updated since it was last unpacked.
            long installed = getPackageManager().getPackageInfo(getPackageName(), 0).lastUpdateTime;
            File marker = new File(home, ".data-" + DATA_VERSION + "-" + installed);
            if (!marker.exists()) {
                bridge.speak("Setting up the game. This only happens the first time and takes a minute or two.", true);
                deleteRecursive(new File(home, "game"));
                filesTotal = countFiles("game") + countFiles("localization") + 1;
                filesDone = 0;
                copyTree("game", new File(home, "game"));
                // the language files and the version number: the ones the app ships are put back, and a
                // language file of the player's own is left alone
                copyTree("localization", new File(home, "localization"));
                copyFile("VERSION", new File(home, "VERSION"));
                File[] old = home.listFiles((dir, name) -> name.startsWith(".data-"));
                if (old != null) {
                    for (File f : old) {
                        //noinspection ResultOfMethodCallIgnored
                        f.delete();
                    }
                }
                if (!marker.createNewFile()) {
                    Log.w(TAG, "could not write the marker");
                }
                bridge.speak("The game is ready.", false);
            }
            Python.getInstance().getModule("audiodefence.android_main")
                    .callAttr("run", home.getAbsolutePath());
        } catch (Throwable t) {
            Log.e(TAG, "the game could not start", t);
            bridge.speak("Sorry, the game could not start. " + t.getClass().getSimpleName(), true);
            try {
                Thread.sleep(6000);
            } catch (InterruptedException ignored) {
                // leaving anyway
            }
        } finally {
            bridge.gameEnded();
        }
    }

    private int countFiles(String dir) throws IOException {
        AssetManager am = getAssets();
        String[] names = am.list(dir);
        if (names == null || names.length == 0) {
            return 1;
        }
        int n = 0;
        for (String name : names) {
            n += countFiles(dir + "/" + name);
        }
        return n;
    }

    private void copyTree(String assetDir, File target) throws IOException {
        AssetManager am = getAssets();
        String[] names = am.list(assetDir);
        if (names == null || names.length == 0) {
            copyFile(assetDir, target);
            return;
        }
        if (!target.exists() && !target.mkdirs()) {
            throw new IOException("cannot create " + target);
        }
        for (String name : names) {
            copyTree(assetDir + "/" + name, new File(target, name));
        }
    }

    private void copyFile(String asset, File target) throws IOException {
        File parent = target.getParentFile();
        if (parent != null && !parent.exists() && !parent.mkdirs()) {
            throw new IOException("cannot create " + parent);
        }
        try (InputStream in = getAssets().open(asset); OutputStream out = new FileOutputStream(target)) {
            byte[] buf = new byte[65536];
            int n;
            while ((n = in.read(buf)) > 0) {
                out.write(buf, 0, n);
            }
        } catch (java.io.FileNotFoundException e) {
            Log.w(TAG, "skipping " + asset + " (an empty folder)");   // list() cannot tell one from a file
        }
        filesDone++;
        if (filesTotal > 0 && filesDone % Math.max(1, filesTotal / 5) == 0 && filesDone < filesTotal) {
            bridge.speak((100 * filesDone / filesTotal) + " percent", false);
        }
    }

    private static void deleteRecursive(File f) {
        File[] kids = f.listFiles();
        if (kids != null) {
            for (File k : kids) {
                deleteRecursive(k);
            }
        }
        //noinspection ResultOfMethodCallIgnored
        f.delete();
    }
}
