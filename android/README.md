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

- **Server setup** — configure the API address after install (LAN IP,
  WireGuard IP, or domain), tested live against `/health` before saving;
  changeable anytime from Settings. No rebuild required to point at a
  different server.
- **Login / Register** — JWT auth against the backend, tokens stored in
  `EncryptedSharedPreferences` (Android Keystore-backed), not plain prefs.
- **Home dashboard** — family switcher, the hospital ID card(s) for whoever's
  selected, expiry alerts, folder tiles by document category, recent
  documents.
- **Family** — add/remove family members (spouse, child, parent, other);
  each gets managed independently, all under your one account.
- **Cards** — a person can have any number of hospital cards; add/view/
  long-press-to-delete. Patient ID numbers are encrypted server-side.
- **Documents** — camera capture or gallery/file picker, categorized as
  hospital card / prescription / lab report / insurance / vaccination /
  bill / medicine / other. Tap to download-and-open in any installed viewer.
- **Search** — search by hospital name across both cards and documents.
- **Reminders** — add a reminder (medicine, appointment, etc.) with optional
  repeat; schedules a local notification via WorkManager.

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
  medicine around 9am" but can drift by minutes under Doze. If you want
  alarm-clock precision, swap `ReminderScheduler` to use
  `AlarmManager.setExactAndAllowWhileIdle` + `SCHEDULE_EXACT_ALARM`.
- **No offline cache** — this is a thin REST client; if the Pi's down or
  you're off Wi-Fi/WireGuard, the app can't show cached cards. Adding a Room
  cache is a reasonable next step if that matters to you.
- **No refresh-token auto-retry yet** — when the access token expires
  (default 60 min), calls will start failing with 401 until you log in
  again. Wiring an OkHttp `Authenticator` that calls `/auth/refresh`
  automatically is the next thing I'd add.
- The Home screen's document tap and folder-tap wiring intentionally routes
  through the folder/list screen rather than opening documents directly from
  Home — keeps the dashboard fast and the download/open logic in one place.
