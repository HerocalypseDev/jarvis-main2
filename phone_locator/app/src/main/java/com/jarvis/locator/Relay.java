package com.jarvis.locator;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/** Talks to the ntfy relay: publish a sealed message, or stream the topic and hand each message on. */
final class Relay {
    interface Listener {
        void onMessage(String id, String text);
    }

    static void publish(Config cfg, String sealed) throws Exception {
        HttpURLConnection c = (HttpURLConnection) new URL(cfg.server + "/" + cfg.topic).openConnection();
        try {
            c.setConnectTimeout(20000);
            c.setReadTimeout(20000);
            c.setRequestMethod("POST");
            c.setDoOutput(true);
            c.setRequestProperty("Content-Type", "text/plain");
            try (OutputStream os = c.getOutputStream()) {
                os.write(sealed.getBytes(StandardCharsets.UTF_8));
            }
            int code = c.getResponseCode();
            if (code / 100 != 2) throw new Exception("relay answered " + code);
        } finally {
            c.disconnect();
        }
    }

    /** Blocks while the stream is open. ntfy sends a keepalive every ~45 s, so a 100 s read timeout means a dead line. */
    static void stream(Config cfg, String since, Listener listener, java.util.concurrent.atomic.AtomicBoolean running) throws Exception {
        String url = cfg.server + "/" + cfg.topic + "/json?since=" + since;
        HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
        try {
            c.setConnectTimeout(20000);
            c.setReadTimeout(100000);
            BufferedReader r = new BufferedReader(new InputStreamReader(c.getInputStream(), StandardCharsets.UTF_8));
            String line;
            while (running.get() && (line = r.readLine()) != null) {
                if (line.isEmpty()) continue;
                JSONObject o = new JSONObject(line);
                if (!"message".equals(o.optString("event"))) continue;
                listener.onMessage(o.optString("id"), o.optString("message"));
            }
        } finally {
            c.disconnect();
        }
    }
}
