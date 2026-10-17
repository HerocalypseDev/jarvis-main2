package com.jarvis.locator;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** Starts sharing again after the phone restarts or the app is updated, if it was on. */
public class BootReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context ctx, Intent intent) {
        if (!Config.enabled(ctx) || Config.load(ctx) == null) return;
        try {
            LocatorService.start(ctx, LocatorService.ACTION_START);
        } catch (Exception ignored) {
            // Android 14 refuses a background location start without "Allow all the time": the app shows why when opened.
        }
    }
}
