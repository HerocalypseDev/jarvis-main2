# Jarvis Locator (Android)

A small Android app that lets Jarvis say where your phone is ("where's my phone?", "show me on the map").

- Every few minutes (5-120, default 10), and whenever Jarvis asks, it takes one GPS fix and sends it to Jarvis
  through an ntfy topic. Every message is sealed with AES-256-GCM under the key in the setup code, so the relay
  server only sees random text; a stranger who finds the topic can't read, fake or trigger anything.
- Needs: location on, the internet (a few hundred bytes per check-in), Android 7+.
- Runs as a foreground service (the small "Jarvis can see where this phone is" notification is required by Android).

## Set up
1. Install the APK (allow "install unknown apps"; Play Protect may warn because it isn't from the Play Store).
2. On the PC, open the dashboard's **Phones** page, tap **Show setup code** (or **Send it to my Telegram**).
3. In the app: paste the code, name the phone, tap **Save and start sharing**, allow location ("all the time" if
   offered, so it restarts after a reboot), and tap **Keep running in the background**.
4. Tecno/Infinix/Xiaomi/Samsung battery savers can still stop it: allow auto-start / "unrestricted" battery for the app.

## Build
`gradle assembleRelease` in this folder (Android SDK 34, JDK 17+), or the "Jarvis Locator APK" GitHub Action, which
uploads the APK as a build artifact. `app/locator.keystore` signs it so a new version installs over the old one;
without it (the public copy) the normal debug key is used.
