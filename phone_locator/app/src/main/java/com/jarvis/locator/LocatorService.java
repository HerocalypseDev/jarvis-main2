package com.jarvis.locator;

import android.Manifest;
import android.app.AlarmManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.location.Location;
import android.location.LocationListener;
import android.location.LocationManager;
import android.os.BatteryManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.IBinder;
import android.os.PowerManager;
import android.os.SystemClock;

import org.json.JSONObject;

import java.security.SecureRandom;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * Runs in the foreground (Android needs the notification for background location). Every few minutes, and
 * whenever Jarvis asks, it takes one GPS fix and sends it, sealed, through the relay. It listens on the relay
 * for Jarvis's sealed "ask" messages; anything it can't open is ignored.
 */
public class LocatorService extends Service {
    static final String ACTION_START = "start";
    static final String ACTION_TICK = "tick";
    static final String ACTION_NOW = "now";
    static final String ACTION_STOP = "stop";
    static final String CHANNEL = "locator";
    static final long FIX_TIMEOUT_MS = 60000;
    static final long ASK_MAX_AGE_MS = 10 * 60 * 1000;
    static final long OLD_FIX_MAX_MS = 24 * 60 * 60 * 1000L;
    static final long SEND_WAKE_MS = 90000;

    private final AtomicBoolean running = new AtomicBoolean(false);
    private final ExecutorService net = Executors.newSingleThreadExecutor();
    private final Set<String> seenAsks = new HashSet<>();
    private final Set<String> pendingReasons = new LinkedHashSet<>();
    private HandlerThread fixThread;
    private Handler fixHandler;
    private Thread listenThread;
    private boolean fixing;
    private volatile long lastFixAt;

    /** A second clock inside the service: some phones drop the alarm, and then no check-in would ever come again. */
    private final Runnable backupTick = new Runnable() {
        @Override
        public void run() {
            if (!running.get()) return;
            long every = Config.interval(LocatorService.this) * 60000L;
            if (SystemClock.elapsedRealtime() - lastFixAt > every + 60000) {
                requestFix("interval");
                scheduleAlarm();
            }
            fixHandler.postDelayed(this, 60000);
        }
    };

    static void start(Context ctx, String action) {
        Intent i = new Intent(ctx, LocatorService.class).setAction(action);
        if (Build.VERSION.SDK_INT >= 26) ctx.startForegroundService(i);
        else ctx.startService(i);
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public void onCreate() {
        super.onCreate();
        fixThread = new HandlerThread("fix");
        fixThread.start();
        fixHandler = new Handler(fixThread.getLooper());
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        String action = intent == null || intent.getAction() == null ? ACTION_START : intent.getAction();
        goForeground();
        if (ACTION_STOP.equals(action)) {
            Config.prefs(this).edit().putBoolean("enabled", false).apply();
            cancelAlarm();
            running.set(false);
            stopForeground(true);
            stopSelf();
            return START_NOT_STICKY;
        }
        Config cfg = Config.load(this);
        if (cfg == null || !Config.enabled(this)) {
            stopForeground(true);
            stopSelf();
            return START_NOT_STICKY;
        }
        if (running.compareAndSet(false, true)) {
            startListening();
            requestFix("start");
            fixHandler.postDelayed(backupTick, 60000);
        } else if (ACTION_NOW.equals(action)) {
            requestFix("manual");
        } else if (ACTION_TICK.equals(action)) {
            requestFix("interval");
        } else if (ACTION_START.equals(action)) {
            requestFix("start");
        }
        scheduleAlarm();
        return START_STICKY;
    }

    @Override
    public void onDestroy() {
        running.set(false);
        if (listenThread != null) listenThread.interrupt();
        fixThread.quitSafely();
        net.shutdown();
        super.onDestroy();
    }

    // --- notification --------------------------------------------------------------------------
    private void goForeground() {
        NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= 26 && nm.getNotificationChannel(CHANNEL) == null) {
            NotificationChannel ch = new NotificationChannel(CHANNEL, "Location sharing with Jarvis", NotificationManager.IMPORTANCE_LOW);
            ch.setShowBadge(false);
            nm.createNotificationChannel(ch);
        }
        PendingIntent open = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class), PendingIntent.FLAG_IMMUTABLE);
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this, CHANNEL) : new Notification.Builder(this);
        String last = Config.prefs(this).getString("last_status", "Starting...");
        Notification n = b.setSmallIcon(R.drawable.ic_stat)
                .setContentTitle("Jarvis can see where this phone is")
                .setContentText(last)
                .setContentIntent(open)
                .setOngoing(true)
                .build();
        if (Build.VERSION.SDK_INT >= 29) startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION);
        else startForeground(1, n);
    }

    private void setStatus(String text) {
        Config.prefs(this).edit().putString("last_status", text).apply();
        try {
            goForeground();
        } catch (Exception ignored) {
        }
    }

    // --- schedule ------------------------------------------------------------------------------
    private PendingIntent tickIntent() {
        Intent i = new Intent(this, TickReceiver.class);
        return PendingIntent.getBroadcast(this, 1, i, PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
    }

    private void scheduleAlarm() {
        AlarmManager am = (AlarmManager) getSystemService(ALARM_SERVICE);
        long at = SystemClock.elapsedRealtime() + Config.interval(this) * 60000L;
        if (Build.VERSION.SDK_INT >= 23) am.setAndAllowWhileIdle(AlarmManager.ELAPSED_REALTIME_WAKEUP, at, tickIntent());
        else am.set(AlarmManager.ELAPSED_REALTIME_WAKEUP, at, tickIntent());
    }

    private void cancelAlarm() {
        ((AlarmManager) getSystemService(ALARM_SERVICE)).cancel(tickIntent());
    }

    // --- listening for Jarvis's asks -----------------------------------------------------------
    private void startListening() {
        listenThread = new Thread(() -> {
            long backoff = 5000;
            while (running.get()) {
                Config cfg = Config.load(this);
                if (cfg == null) return;
                String since = Config.prefs(this).getString("last_msg_id", "2m");
                try {
                    Relay.stream(cfg, since, (id, text) -> {
                        if (id != null && !id.isEmpty()) Config.prefs(this).edit().putString("last_msg_id", id).apply();
                        handleRelayMessage(cfg, text);
                    }, running);
                    backoff = 5000;
                } catch (Exception e) {
                    // offline, relay down, or the phone dozing: wait and reconnect
                }
                try {
                    Thread.sleep(backoff);
                } catch (InterruptedException e) {
                    return;
                }
                backoff = Math.min(backoff * 2, 5 * 60 * 1000);
            }
        }, "relay-listen");
        listenThread.setDaemon(true);
        listenThread.start();
    }

    private void handleRelayMessage(Config cfg, String text) {
        String plain = Crypto.open(cfg, text);
        if (plain == null) return; // not from Jarvis (or from the other phone's location reports, which are still ours but not asks)
        try {
            JSONObject o = new JSONObject(plain);
            if (!"ask".equals(o.optString("type"))) return;
            String nonce = o.optString("nonce");
            long ts = o.optLong("ts");
            if (Math.abs(System.currentTimeMillis() - ts) > ASK_MAX_AGE_MS) return;
            synchronized (seenAsks) {
                if (!seenAsks.add(nonce)) return;
                if (seenAsks.size() > 200) seenAsks.clear();
            }
            String target = o.optString("phone", "");
            if (!target.isEmpty() && !target.equals(Config.deviceId(this))) return;
            requestFix("ask");
        } catch (Exception ignored) {
        }
    }

    // --- taking a fix --------------------------------------------------------------------------
    private void requestFix(String reason) {
        lastFixAt = SystemClock.elapsedRealtime();
        fixHandler.post(() -> {
            synchronized (pendingReasons) {
                pendingReasons.add(reason);
                if (fixing) return;
                fixing = true;
            }
            takeFix();
        });
    }

    private boolean hasLocationPermission() {
        return checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
                || checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED;
    }

    @SuppressWarnings("MissingPermission")
    private void takeFix() {
        LocationManager lm = (LocationManager) getSystemService(LOCATION_SERVICE);
        if (!hasLocationPermission()) {
            finishFix(null, "no_permission");
            return;
        }
        boolean gps = lm.isProviderEnabled(LocationManager.GPS_PROVIDER);
        boolean netw = lm.isProviderEnabled(LocationManager.NETWORK_PROVIDER);
        // Android 12+: the fused provider gives a fix indoors from Wi-Fi/cell when GPS has no sky view.
        boolean fused = Build.VERSION.SDK_INT >= 31 && lm.getAllProviders().contains(LocationManager.FUSED_PROVIDER)
                && lm.isProviderEnabled(LocationManager.FUSED_PROVIDER);
        if (!gps && !netw && !fused && !(Build.VERSION.SDK_INT >= 28 && lm.isLocationEnabled())) {
            finishFix(null, "location_off");
            return;
        }
        PowerManager.WakeLock wl = ((PowerManager) getSystemService(POWER_SERVICE))
                .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "jarvislocator:fix");
        wl.acquire(FIX_TIMEOUT_MS + 15000);
        final Location[] best = {null};
        final boolean[] done = {false};
        final LocationListener[] holder = new LocationListener[1];
        Runnable finish = () -> {
            if (done[0]) return;
            done[0] = true;
            lm.removeUpdates(holder[0]);
            Location b = best[0];
            if (b == null) b = lastKnown(lm);
            finishFix(b, b == null ? "no_fix" : null);
            if (wl.isHeld()) wl.release();
        };
        holder[0] = new LocationListener() {
            @Override
            public void onLocationChanged(Location loc) {
                if (best[0] == null || loc.getAccuracy() < best[0].getAccuracy()) best[0] = loc;
                if (loc.hasAccuracy() && loc.getAccuracy() <= 25) finish.run();
            }

            @Override
            public void onStatusChanged(String p, int s, Bundle b) {
            }

            @Override
            public void onProviderEnabled(String p) {
            }

            @Override
            public void onProviderDisabled(String p) {
            }
        };
        if (gps) lm.requestLocationUpdates(LocationManager.GPS_PROVIDER, 1000, 0, holder[0], fixThread.getLooper());
        if (netw) lm.requestLocationUpdates(LocationManager.NETWORK_PROVIDER, 1000, 0, holder[0], fixThread.getLooper());
        if (fused) lm.requestLocationUpdates(LocationManager.FUSED_PROVIDER, 1000, 0, holder[0], fixThread.getLooper());
        fixHandler.postDelayed(finish, FIX_TIMEOUT_MS);
    }

    @SuppressWarnings("MissingPermission")
    private Location lastKnown(LocationManager lm) {
        // No fresh fix (indoors, GPS only): send the phone's newest known position with its real time, so Jarvis
        // still hears from the phone. Jarvis never moves the pin back to an older position than it already has.
        Location best = null;
        for (String p : lm.getAllProviders()) {
            Location l;
            try {
                l = lm.getLastKnownLocation(p);
            } catch (Exception e) {
                continue;
            }
            if (l == null) continue;
            if (System.currentTimeMillis() - l.getTime() > OLD_FIX_MAX_MS) continue;
            if (best == null || l.getTime() > best.getTime()) best = l;
        }
        return best;
    }

    private void finishFix(Location loc, String problem) {
        String reasons;
        synchronized (pendingReasons) {
            reasons = String.join(",", pendingReasons);
            pendingReasons.clear();
            fixing = false;
        }
        Config cfg = Config.load(this);
        if (cfg == null) return;
        try {
            JSONObject o = new JSONObject();
            o.put("v", 1);
            o.put("type", loc == null ? "nofix" : "loc");
            o.put("id", Config.deviceId(this));
            o.put("phone", Config.name(this));
            o.put("reason", reasons);
            o.put("sent_ts", System.currentTimeMillis());
            o.put("nonce", Long.toHexString(new SecureRandom().nextLong()));
            if (loc != null) {
                o.put("lat", loc.getLatitude());
                o.put("lon", loc.getLongitude());
                if (loc.hasAccuracy()) o.put("acc", (double) loc.getAccuracy());
                if (loc.hasAltitude()) o.put("alt", loc.getAltitude());
                if (loc.hasSpeed()) o.put("speed", (double) loc.getSpeed());
                o.put("provider", loc.getProvider());
                o.put("fix_ts", loc.getTime());
            } else {
                o.put("problem", problem);
            }
            Intent bat = registerReceiver(null, new IntentFilter(Intent.ACTION_BATTERY_CHANGED));
            if (bat != null) {
                int level = bat.getIntExtra(BatteryManager.EXTRA_LEVEL, -1);
                int scale = bat.getIntExtra(BatteryManager.EXTRA_SCALE, 100);
                if (level >= 0 && scale > 0) o.put("battery", Math.round(level * 100f / scale));
                int plugged = bat.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0);
                o.put("charging", plugged != 0);
            }
            String sealed = Crypto.seal(cfg, o.toString());
            net.execute(() -> sendWithRetry(cfg, sealed, loc != null));
        } catch (Exception e) {
            setStatus("Couldn't prepare the location: " + e.getMessage());
        }
    }

    private void sendWithRetry(Config cfg, String sealed, boolean hadFix) {
        // Keep the CPU awake until the send is done: with the screen off the phone used to fall asleep between
        // taking the fix and sending it, so nothing reached Jarvis.
        PowerManager.WakeLock wl = ((PowerManager) getSystemService(POWER_SERVICE))
                .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "jarvislocator:send");
        wl.acquire(SEND_WAKE_MS);
        String why = "";
        try {
            for (int attempt = 0; attempt < 3; attempt++) {
                try {
                    Relay.publish(cfg, sealed);
                    String when = now();
                    setStatus(hadFix ? "Last sent at " + when : "Sent at " + when + ", but no location fix (Jarvis was told)");
                    return;
                } catch (Exception e) {
                    why = e.getMessage() == null ? e.getClass().getSimpleName() : e.getMessage();
                    try {
                        Thread.sleep(5000L * (attempt + 1));
                    } catch (InterruptedException ie) {
                        return;
                    }
                }
            }
            setStatus("Couldn't reach Jarvis's relay at " + now() + " (" + why + "), will try again at the next check-in");
        } finally {
            if (wl.isHeld()) wl.release();
        }
    }

    private static String now() {
        return java.text.DateFormat.getTimeInstance(java.text.DateFormat.SHORT).format(new java.util.Date());
    }
}
