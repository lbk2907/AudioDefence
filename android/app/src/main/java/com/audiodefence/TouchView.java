package com.audiodefence;

import android.content.Context;
import android.view.MotionEvent;
import android.view.View;

/** The whole screen is one touch surface; the game does the rest.  Coordinates go to Python in dp. */
public final class TouchView extends View {
    private final float density;

    public TouchView(Context context) {
        super(context);
        density = context.getResources().getDisplayMetrics().density;
        setFocusable(true);
        setFocusableInTouchMode(true);
    }

    @Override
    protected void onSizeChanged(int w, int h, int oldw, int oldh) {
        super.onSizeChanged(w, h, oldw, oldh);
        Bridge.get().setScreen(w / density, h / density);
    }

    @Override
    public boolean onTouchEvent(MotionEvent e) {
        Bridge b = Bridge.get();
        int action = e.getActionMasked();
        switch (action) {
            case MotionEvent.ACTION_DOWN:
            case MotionEvent.ACTION_POINTER_DOWN: {
                int i = e.getActionIndex();
                b.postTouch(0, e.getPointerId(i), e.getX(i) / density, e.getY(i) / density);
                break;
            }
            case MotionEvent.ACTION_MOVE:
                for (int i = 0; i < e.getPointerCount(); i++) {
                    b.postTouch(1, e.getPointerId(i), e.getX(i) / density, e.getY(i) / density);
                }
                break;
            case MotionEvent.ACTION_UP:
            case MotionEvent.ACTION_POINTER_UP: {
                int i = e.getActionIndex();
                b.postTouch(2, e.getPointerId(i), e.getX(i) / density, e.getY(i) / density);
                break;
            }
            case MotionEvent.ACTION_CANCEL:
                for (int i = 0; i < e.getPointerCount(); i++) {
                    b.postTouch(3, e.getPointerId(i), e.getX(i) / density, e.getY(i) / density);
                }
                break;
            default:
                break;
        }
        return true;
    }
}
