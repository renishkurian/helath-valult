# Health Vault

A self-hosted app for keeping hospital ID cards, medical documents, and
family health records — backend runs on your own server (e.g. a Raspberry
Pi), Android app talks to it directly. Nothing goes through a third party.

```
HealthVault/
├── backend/     FastAPI + SQLAlchemy API, encrypted storage, admin web UI
├── android/     Kotlin + Jetpack Compose app
└── .github/workflows/   CI for both, scoped by path so each only runs
                          when its own folder changes
```

Each folder has its own README with full setup details:
- **[backend/README.md](backend/README.md)** — local dev, Docker deploy on
  the Pi, encryption model, admin UI, API reference
- **[android/README.md](android/README.md)** — Android Studio setup,
  runtime server configuration, signing releases

## Quick start

1. **Backend**: `cd backend`, follow its README to get the API running
   locally or on your Pi.
2. **Android**: `cd android`, open in Android Studio, run it, and enter
   your server's address on the first-run setup screen (no rebuild needed —
   the server URL is configured at runtime, like Immich's app).

## CI

Two workflows, each path-filtered so a change to one project doesn't
trigger a build of the other:

- **`android-ci.yml`** — builds a debug APK + runs unit tests on every
  push/PR touching `android/**`.
- **`backend-ci.yml`** — runs the pytest suite on every push/PR touching
  `backend/**`, then (on `main`) builds and pushes a multi-arch Docker image
  to GHCR.

Tag pushes matching `android-v*` (e.g. `android-v1.0.0`) trigger
`android-release.yml`, which builds a release APK and attaches it to a
GitHub Release.

## Why one repo

Nothing about this pairing requires a monorepo — you could just as easily
split `backend/` and `android/` into two repos later if that ever gets
unwieldy, since the CI is already fully scoped per folder and neither
project imports code from the other. Kept together here because they're
developed and versioned together and it's simpler to clone once.
