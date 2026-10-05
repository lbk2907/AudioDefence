package com.audiodefence;

import android.app.Activity;
import android.content.Intent;
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

/**
 * Audio Defence for Android.  Opens the touch surface, unpacks the game's data the first time and what changed of
 * it after an update (DataSync), then runs the game (Python: audiodefence/android_main.py) on a thread of its own.
 */
public final class MainActivity extends Activity {
    private static final String TAG = "AudioDefence";
    // raise it when the layout of the unpacked data changes: the next start unpacks all of it again
    private static final int DATA_VERSION = 2;

    private Bridge bridge;
    private boolean started;

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

    /** Android's file picker closed: the backup chosen for Import backup, or where Export backup goes on
     *  Android 8 and 9 (Bridge.pickFileToOpen, pickFileToCreate). */
    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (bridge != null) {
            bridge.documentPicked(requestCode, resultCode, data);
        }
    }

    /** A keyboard plugged into the phone: its keys go to the game (Bridge.keyEvent); the phone's own go on. */
    @Override
    public boolean dispatchKeyEvent(KeyEvent event) {
        if (bridge != null && started && bridge.keyEvent(event)) {
            return true;
        }
        return super.dispatchKeyEvent(event);
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
            boolean warned = am != null && am.isTouchExplorationEnabled();
            if (warned) {
                bridge.speak("TalkBack is on. The game speaks for itself and needs TalkBack turned off. "
                        + "Turn TalkBack off, then open the game again.", true);
            }
            File home = new File(getFilesDir(), "adhome");
            // The game's data is built into each APK from the repository it is made in.  DataSync compares the
            // APK's list of it with the list of what was unpacked last time and unpacks only what changed, so a
            // start after an update that left the data alone goes straight to the game.  A line said here is
            // queued behind the TalkBack warning rather than cutting it off.
            DataSync.sync(home, DATA_VERSION, getAssets()::open, new DataSync.Listener() {
                @Override
                public void starting(DataSync.Plan plan) {
                    if (plan.full) {
                        bridge.speak("Setting up the game. This only happens the first time and takes a minute "
                                + "or two.", !warned);
                    } else if (plan.announce()) {
                        bridge.speak("Unpacking the update.", !warned);
                    }
                }

                @Override
                public void progress(int percent) {
                    bridge.speak(percent + " percent", false);
                }

                @Override
                public void finished(DataSync.Plan plan) {
                    if (plan.announce()) {
                        bridge.speak("The game is ready.", false);
                    }
                }
            });
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
}
