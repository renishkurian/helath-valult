# Vault Hub — Android App

Kotlin + Jetpack Compose client for Vault Hub (passwords, health, finance,
shopping, and more on your own server).

## CI/CD

Two workflows in `.github/workflows/`:

- **`android-ci.yml`** — runs on every push/PR to `main`. Builds a debug
  APK and runs unit tests, uploading both as workflow artifacts (Actions
  tab → the run → Artifacts). Uses `gradle` directly via
  `gradle/actions/setup-gradle` rather than `./gradlew`, since this repo
  doesn't check in the wrapper's binary jar (`gradle-wrapper.jar`) — see
  "Local Gradle wrapper" below.

- **`android-release.yml`** — triggered by pushing a version tag
  (`git tag v1.0.0 && git push origin v1.0.0`) or manually from the Actions
  tab. Builds a release APK and attaches it to a new GitHub Release.
  Unsigned by default; see "Signing releases" below to enable signing.

### Local Gradle wrapper

Opening the project in Android Studio generates `gradlew` / `gradlew.bat` /
`gradle-wrapper.jar` automatically on first sync — nothing to do. If you
want them checked into git (so CI could use `./gradlew` too, or so command-
line builds work without Android Studio having run first), generate them
once locally and commit the result:
```bash
gradle wrapper --gradle-version 8.7
git add gradlew gradlew.bat gradle/wrapper/gradle-wrapper.jar
```

### Signing releases

Without a keystore, `android-release.yml` attaches an unsigned APK — fine
for sideloading onto your own device, but Android will refuse to install it
as an *update* over a previously-signed install, and unsigned APKs can't go
on the Play Store. To sign releases in CI:

```bash
keytool -genkey -v -keystore release.keystore -alias healthvault \
  -keyalg RSA -keysize 2048 -validity 10000
base64 -w0 release.keystore > release.keystore.base64   # -w0 avoids line wraps
```
Then add four repo secrets (Settings → Secrets and variables → Actions):
- `KEYSTORE_BASE64` — contents of `release.keystore.base64`
- `KEYSTORE_PASSWORD`, `KEY_ALIAS` (`healthvault` above), `KEY_PASSWORD`

The release workflow picks these up automatically and signs the APK before
attaching it — no workflow file changes needed.

## Setup

1. Open the `android/` folder in Android Studio (Koala or newer).
   It will offer to create the Gradle wrapper jar automatically on first
   sync — let it.
2. Run on a device or emulator on the same network as the Pi (or connected
   via WireGuard).
3. On first launch, the app shows a **server setup screen** — enter your
   Pi's address (e.g. `192.168.0.50:8000`, `http://` assumed if you leave
   off the scheme), tap Connect. It pings `/health` before saving, so you
   get an immediate "can't reach that" instead of a silent failure later.
   From then on the app remembers it — no rebuild needed to point at a
   different server.
4. You can change the server later from the gear icon on the Home screen →
   Settings, or from the "Change" link on the Login screen. Changing to a
   genuinely different server automatically logs you out, since a login
   token from one server isn't valid on another.

The address is stored on-device only (plain SharedPreferences — it's an
address, not a secret) and every request is routed through it via an OkHttp
interceptor, the same way Immich's app lets you point at your own server
post-install. `app/build.gradle.kts` has a `DEFAULT_SERVER_URL` field that
only prefills the setup screen's text field as a convenience — it's not
used for actual networking.

**Cleartext HTTP note:** since the server address isn't known at build
time, `network_security_config.xml` permits cleartext traffic app-wide
(same trade-off Immich makes) rather than allowlisting a specific domain.
This only matters if you point the app at a plain `http://` address — if
your server's behind HTTPS, traffic is encrypted regardless.

## Push notifications (FCM)

Super Admin → Server settings storing an FCM **service account** only lets the
**server** send pushes. The Android app must also:

1. Use a `google-services.json` from the **same** Firebase project as that
   service account (Firebase Console → Project settings → Your apps → Android
   package `com.rklab.healthvault` → Download `google-services.json`).
2. Place it at `android/app/google-services.json` (gitignored; an example
   placeholder is auto-copied for local builds until you replace it).
3. Rebuild/install the app, sign in once, and allow notifications when asked.

After that, login-approve and Send access-request pushes reach the device even
when the app is in the background (server sends **data-only** FCM so the app
can always show a tray notification with the right deep link). With the app
open, pending access requests also show an in-app dialog and poll every few
seconds. A WorkManager job also polls every ~15 minutes as a fallback if FCM
is delayed.

## What's implemented

Full module list: **[root README](../README.md)**. On Android specifically:

- **Server setup** — configure API address after install (LAN, WireGuard, or
  domain); live `/health` probe; changeable from Settings / Login
- **Auth** — register / login; JWT in Keystore-backed encrypted prefs;
  refresh-token retry on 401; optional TOTP; QR login approve; app-approve
  for web logins
- **Module hub** — Family, Health, Passwords, Secret Share, Finance, Expense
  Analyser, AI, Locker, Shopping List, URLs, Diary (respects server enablement)
- **Health** — family, hospital cards, documents (camera / gallery), search,
  reminders (WorkManager), care, doctors
- **Passwords** — items, profile filter / assign profile, editor, generator,
  health report, Sends (incl. first-browser lock), trash; autofill service
- **Secret Share** — paste text → expiring link; PIN / grant / email OTP /
  first-browser lock; revoke and request list
- **Finance** — transactions, stats, accounts, EMIs, SMS inbox, add flow
- **Expense Analyser, AI, Locker, Tracker, URLs, Diary** — module screens
  aligned with the web app
- **Settings** — server URL, theme (dark / large text), Ask AI FAB, PIN /
  biometric lock, Drive / backup status
- **Offline** — Room cache + SyncWorker for core health data; last-viewed
  document file cache; offline upload queue
- **Push** — FCM for login-approve and Send access requests, plus ~15m poll
  fallback

## Fonts (optional, for exact design parity)

The typography currently uses system font families (serif/sans/monospace)
so the project builds with zero extra assets. To match the original mockup
exactly:

1. Download **Roboto Slab**, **IBM Plex Sans**, and **IBM Plex Mono** from
   Google Fonts.
2. Put the `.ttf` files in `app/src/main/res/font/` named e.g.
   `roboto_slab_regular.ttf`, `roboto_slab_bold.ttf`, `plex_sans_regular.ttf`,
   `plex_sans_medium.ttf`, `plex_sans_semibold.ttf`, `plex_mono_regular.ttf`,
   `plex_mono_medium.ttf`.
3. In `ui/theme/Type.kt`, replace the `FontFamily.Serif` /
   `.SansSerif` / `.Monospace` fallbacks with `FontFamily(Font(R.font.xxx, ...))`
   entries pointing at those files (the original version of this file, with
   that wiring already done, is in the build history if you want to restore
   it verbatim).

## Notes / things worth doing before relying on this daily

- **Reminders use WorkManager**, not exact alarms — fine for "take your
  medicine around 9am" but can drift by minutes under Doze. For
  alarm-clock precision, swap `ReminderScheduler` to
  `AlarmManager.setExactAndAllowWhileIdle` + `SCHEDULE_EXACT_ALARM`.
- FCM needs a real `google-services.json` from the same Firebase project as
  the Super Admin service account (see above).
- The Home screen's document / folder taps route through the list screens
  so download/open logic stays in one place.
