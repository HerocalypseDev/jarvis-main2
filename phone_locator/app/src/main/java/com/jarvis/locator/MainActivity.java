package com.jarvis.locator;

import android.Manifest;
import android.app.Activity;
import android.content.ClipboardManager;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.PowerManager;
import android.provider.Settings;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.util.ArrayList;
import java.util.List;

/** One screen: paste the setup code from Jarvis, name the phone, pick how often, switch on. Jarvis's dark/cyan look. */
public class MainActivity extends Activity {
    private static final int BG = Color.parseColor("#0B1220");
    private static final int CARD = Color.parseColor("#111A2E");
    private static final int CYAN = Color.parseColor("#22D3EE");
    private static final int TEXT = Color.parseColor("#E2E8F0");
    private static final int MUTED = Color.parseColor("#94A3B8");
    private static final int REQ_FG = 1;
    private static final int REQ_BG = 2;

    private EditText code;
    private EditText name;
    private EditText interval;
    private TextView status;
    private TextView pairing;

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        SharedPreferences p = Config.prefs(this);

        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(20);
        col.setPadding(pad, dp(28), pad, pad);
        col.setBackgroundColor(BG);

        TextView title = text("JARVIS LOCATOR", 22, CYAN);
        title.setTypeface(Typeface.MONOSPACE, Typeface.BOLD);
        title.setShadowLayer(12, 0, 0, CYAN);
        col.addView(title);
        col.addView(text("Shares where this phone is with your Jarvis, sealed so only Jarvis can read it.", 14, MUTED));

        status = text("", 15, TEXT);
        col.addView(card(status));

        col.addView(label("Setup code from Jarvis"));
        code = field("Paste the JLOC1... code", InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_NO_SUGGESTIONS);
        col.addView(code);
        Button paste = button("Paste from clipboard", false);
        paste.setOnClickListener(v -> {
            ClipboardManager cm = (ClipboardManager) getSystemService(CLIPBOARD_SERVICE);
            if (cm.hasPrimaryClip() && cm.getPrimaryClip().getItemCount() > 0) {
                CharSequence t = cm.getPrimaryClip().getItemAt(0).coerceToText(this);
                code.setText(t == null ? "" : t.toString().trim());
            }
        });
        col.addView(paste);
        pairing = text(Config.load(this) != null ? "Paired with Jarvis." : "Not paired yet.", 13, MUTED);
        col.addView(pairing);

        col.addView(label("Name for this phone"));
        name = field(Build.MODEL, InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_CAP_WORDS);
        name.setText(p.getString("name", ""));
        col.addView(name);

        col.addView(label("Check in every (minutes, 5-120)"));
        interval = field("10", InputType.TYPE_CLASS_NUMBER);
        interval.setText(String.valueOf(Config.interval(this)));
        col.addView(interval);

        Button start = button("Save and start sharing", true);
        start.setOnClickListener(v -> saveAndStart());
        col.addView(start);
        Button now = button("Send my location now", false);
        now.setOnClickListener(v -> {
            if (Config.enabled(this)) LocatorService.start(this, LocatorService.ACTION_NOW);
            refresh();
        });
        col.addView(now);
        Button battery = button("Keep running in the background", false);
        battery.setOnClickListener(v -> askBatteryExemption());
        col.addView(battery);
        Button stop = button("Stop sharing", false);
        stop.setOnClickListener(v -> {
            p.edit().putBoolean("enabled", false).apply();
            startService(new Intent(this, LocatorService.class).setAction(LocatorService.ACTION_STOP));
            refresh();
        });
        col.addView(stop);
        col.addView(text("Uses the internet only to send a few hundred bytes per check-in. Location (GPS) must be on. " +
                "Some phones (Tecno, Infinix, Xiaomi...) also need this app allowed to auto-start / run in the background in their own settings.", 12, MUTED));

        ScrollView sv = new ScrollView(this);
        sv.setBackgroundColor(BG);
        sv.addView(col);
        setContentView(sv);
    }

    @Override
    protected void onResume() {
        super.onResume();
        refresh();
    }

    private void refresh() {
        SharedPreferences p = Config.prefs(this);
        StringBuilder s = new StringBuilder();
        boolean paired = Config.load(this) != null;
        if (!paired) s.append("Not paired: paste the setup code from Jarvis's Phones page.");
        else if (!Config.enabled(this)) s.append("Paired, sharing is off.");
        else s.append("Sharing is on. ").append(p.getString("last_status", ""));
        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED)
            s.append("\nLocation permission: not given.");
        else if (Build.VERSION.SDK_INT >= 29 && checkSelfPermission(Manifest.permission.ACCESS_BACKGROUND_LOCATION) != PackageManager.PERMISSION_GRANTED)
            s.append("\nTip: allow location \"all the time\" so sharing restarts by itself after the phone reboots.");
        PowerManager pm = (PowerManager) getSystemService(POWER_SERVICE);
        if (Build.VERSION.SDK_INT >= 23 && !pm.isIgnoringBatteryOptimizations(getPackageName()))
            s.append("\nBattery saver may pause it: tap \"Keep running in the background\".");
        status.setText(s.toString());
        pairing.setText(paired ? "Paired with Jarvis." : "Not paired yet.");
    }

    private void saveAndStart() {
        SharedPreferences.Editor e = Config.prefs(this).edit();
        String c = code.getText().toString().trim();
        if (!c.isEmpty()) {
            if (Config.parse(c) == null) {
                status.setText("That isn't a Jarvis setup code. Copy the whole JLOC1... line from the Phones page.");
                return;
            }
            e.putString("setup", c.replaceAll("\\s+", "")).remove("last_msg_id");
            code.setText("");
        } else if (Config.load(this) == null) {
            status.setText("Paste the setup code from Jarvis first.");
            return;
        }
        e.putString("name", name.getText().toString().trim());
        int m = 10;
        try {
            m = Integer.parseInt(interval.getText().toString().trim());
        } catch (NumberFormatException ignored) {
        }
        e.putInt("interval", Math.max(Config.MIN_INTERVAL, Math.min(Config.MAX_INTERVAL, m)));
        e.putBoolean("enabled", true).apply();
        if (askPermissions()) LocatorService.start(this, LocatorService.ACTION_START);
        refresh();
    }

    /** Returns true when foreground location (and notifications) are already allowed. */
    private boolean askPermissions() {
        List<String> need = new ArrayList<>();
        if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) != PackageManager.PERMISSION_GRANTED) {
            need.add(Manifest.permission.ACCESS_FINE_LOCATION);
            need.add(Manifest.permission.ACCESS_COARSE_LOCATION);
        }
        if (Build.VERSION.SDK_INT >= 33 && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED)
            need.add(Manifest.permission.POST_NOTIFICATIONS);
        if (need.isEmpty()) {
            askBackground();
            return true;
        }
        requestPermissions(need.toArray(new String[0]), REQ_FG);
        return false;
    }

    private void askBackground() {
        if (Build.VERSION.SDK_INT >= 29
                && checkSelfPermission(Manifest.permission.ACCESS_BACKGROUND_LOCATION) != PackageManager.PERMISSION_GRANTED
                && !Config.prefs(this).getBoolean("asked_bg", false)) {
            Config.prefs(this).edit().putBoolean("asked_bg", true).apply();
            requestPermissions(new String[]{Manifest.permission.ACCESS_BACKGROUND_LOCATION}, REQ_BG);
        }
    }

    @Override
    public void onRequestPermissionsResult(int req, String[] perms, int[] results) {
        if (req == REQ_FG) {
            if (checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) == PackageManager.PERMISSION_GRANTED
                    || checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) == PackageManager.PERMISSION_GRANTED) {
                if (Config.enabled(this)) LocatorService.start(this, LocatorService.ACTION_START);
                askBackground();
            } else {
                status.setText("Without location permission there is nothing to share.");
            }
        }
        refresh();
    }

    private void askBatteryExemption() {
        if (Build.VERSION.SDK_INT < 23) return;
        try {
            Intent i = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:" + getPackageName()));
            startActivity(i);
        } catch (Exception e) {
            startActivity(new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS));
        }
    }

    // --- small view helpers --------------------------------------------------------------------
    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }

    private TextView text(String s, int sp, int color) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(sp);
        t.setTextColor(color);
        t.setPadding(0, dp(6), 0, dp(6));
        return t;
    }

    private TextView label(String s) {
        TextView t = text(s.toUpperCase(), 12, CYAN);
        t.setPadding(0, dp(14), 0, dp(2));
        t.setLetterSpacing(0.08f);
        return t;
    }

    private View card(View inner) {
        LinearLayout c = new LinearLayout(this);
        c.setPadding(dp(14), dp(10), dp(14), dp(10));
        GradientDrawable g = new GradientDrawable();
        g.setColor(CARD);
        g.setCornerRadius(dp(12));
        g.setStroke(dp(1), Color.argb(90, 34, 211, 238));
        c.setBackground(g);
        c.addView(inner);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2);
        lp.setMargins(0, dp(12), 0, dp(4));
        c.setLayoutParams(lp);
        return c;
    }

    private EditText field(String hint, int type) {
        EditText e = new EditText(this);
        e.setHint(hint);
        e.setInputType(type);
        e.setTextColor(TEXT);
        e.setHintTextColor(MUTED);
        e.setSingleLine(true);
        GradientDrawable g = new GradientDrawable();
        g.setColor(CARD);
        g.setCornerRadius(dp(10));
        g.setStroke(dp(1), Color.argb(120, 148, 163, 184));
        e.setBackground(g);
        e.setPadding(dp(12), dp(10), dp(12), dp(10));
        return e;
    }

    private Button button(String s, boolean primary) {
        Button b = new Button(this);
        b.setText(s);
        b.setAllCaps(false);
        b.setTextColor(primary ? BG : CYAN);
        GradientDrawable g = new GradientDrawable();
        g.setColor(primary ? CYAN : CARD);
        g.setCornerRadius(dp(10));
        g.setStroke(dp(1), CYAN);
        b.setBackground(g);
        b.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, dp(48));
        lp.setMargins(0, dp(10), 0, 0);
        b.setLayoutParams(lp);
        return b;
    }
}
