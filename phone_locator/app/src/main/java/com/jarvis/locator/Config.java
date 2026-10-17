package com.jarvis.locator;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Base64;

import org.json.JSONObject;

import java.nio.charset.StandardCharsets;
import java.util.UUID;

/** Settings kept on the phone: the pairing from Jarvis's setup code, this phone's name and how often it checks in. */
final class Config {
    static final String PREFIX = "JLOC1.";
    static final int MIN_INTERVAL = 5;
    static final int MAX_INTERVAL = 120;

    final String server;
    final String topic;
    final byte[] key;

    private Config(String server, String topic, byte[] key) {
        this.server = server;
        this.topic = topic;
        this.key = key;
    }

    /** Reads a setup code ("JLOC1." + base64url JSON {s, t, k}). Returns null when it isn't one. */
    static Config parse(String code) {
        if (code == null) return null;
        String c = code.replaceAll("\\s+", "");
        int at = c.indexOf(PREFIX);
        if (at < 0) return null;
        try {
            byte[] raw = Base64.decode(c.substring(at + PREFIX.length()), Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING);
            JSONObject o = new JSONObject(new String(raw, StandardCharsets.UTF_8));
            String server = o.getString("s").replaceAll("/+$", "");
            String topic = o.getString("t");
            byte[] key = Base64.decode(o.getString("k"), Base64.URL_SAFE | Base64.NO_WRAP | Base64.NO_PADDING);
            if (!server.startsWith("https://") || !topic.matches("[A-Za-z0-9_-]{16,64}") || key.length != 32) return null;
            return new Config(server, topic, key);
        } catch (Exception e) {
            return null;
        }
    }

    static SharedPreferences prefs(Context ctx) {
        return ctx.getSharedPreferences("locator", Context.MODE_PRIVATE);
    }

    static Config load(Context ctx) {
        return parse(prefs(ctx).getString("setup", null));
    }

    static String name(Context ctx) {
        String n = prefs(ctx).getString("name", "");
        return n == null || n.trim().isEmpty() ? android.os.Build.MODEL : n.trim();
    }

    static int interval(Context ctx) {
        int m = prefs(ctx).getInt("interval", 10);
        return Math.max(MIN_INTERVAL, Math.min(MAX_INTERVAL, m));
    }

    static String deviceId(Context ctx) {
        SharedPreferences p = prefs(ctx);
        String id = p.getString("device_id", null);
        if (id == null) {
            id = UUID.randomUUID().toString().replace("-", "").substring(0, 16);
            p.edit().putString("device_id", id).apply();
        }
        return id;
    }

    static boolean enabled(Context ctx) {
        return prefs(ctx).getBoolean("enabled", false);
    }
}
