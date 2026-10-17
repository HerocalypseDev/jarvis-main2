package com.jarvis.locator;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

/** The check-in alarm. The service is already in the foreground, so a plain start reaches it. */
public class TickReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context ctx, Intent intent) {
        if (!Config.enabled(ctx)) return;
        try {
            ctx.startService(new Intent(ctx, LocatorService.class).setAction(LocatorService.ACTION_TICK));
        } catch (Exception e) {
            try {
                LocatorService.start(ctx, LocatorService.ACTION_TICK);
            } catch (Exception ignored) {
            }
        }
    }
}
