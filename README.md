# Family Vault

Self-hosted vault for your household — family members with private entries and
selective sharing, hospital records, passwords, money, shopping, IDs, bookmarks,
and a diary — on your own server (e.g. a Raspberry Pi). Browser admin UI and
Android app talk to the same backend. Secrets and files are encrypted at rest;
nothing requires a third-party cloud.

```
HealthVault/
├── backend/              FastAPI + SQLAlchemy, encrypted storage, admin web UI
├── android/              Kotlin + Jetpack Compose client
└── .github/workflows/    CI for both (path-filtered)
```

Each folder has its own setup README:
- **[backend/README.md](backend/README.md)** — local dev, Docker / systemd deploy, encryption
- **[backend/deploy/README.md](backend/deploy/README.md)** — Pi install (nginx, Cloudflare Tunnel)
- **[android/README.md](android/README.md)** — Android Studio, runtime server URL, FCM, signing

Modules can be enabled or disabled per vault from **Super Admin**. Owners and
viewers only see what is turned on.

---

## Modules

### Health Vault
Family medical records under one account.

- **Family** — self, spouse, child, parent, other; each person managed separately
- **Hospital ID cards** — multiple cards per person; patient IDs encrypted; optional card photo
- **Documents** — prescriptions, lab reports, insurance, vaccination, bills, medicine photos, and more
- **Upload pipeline** — multi-file docs, OCR / PDF text extract for search, image enhance & compress
- **Versions** — replace a file and keep prior versions downloadable
- **Lab readings** — values parsed from lab reports (API trends / simple alerts)
- **Care** — blood group, allergies, conditions, emergency contact, ABHA, DOB
- **Medicines, vaccines, visits, growth, UHIDs** — care log and hospital identifiers
- **Insurance claims** — claims plus yearly spend summary
- **Doctors** — contacts with specialty; WhatsApp deep links on web
- **Reminders** — medicine / appointment style with daily / weekly / monthly / yearly repeat
- **Search** — cards and documents by title, tags, and OCR text
- **Favorites, pins, trash** — soft-delete / restore / permanent delete; bulk delete & tag
- **Duplicates** — find duplicate documents by content hash
- **ICE card** — public emergency page at `/ice/{token}` (no login) for paramedics
- **Document shares** — timed read-only links with optional PIN, max views, expiry (`/s/{token}`)
- **Share packs** — multi-document packs for front desk (`/p/{token}`)
- **Activity / audit** — who viewed, downloaded, shared, or deleted
- **Storage & backup** — on-disk snapshots, export / restore, optional Google Drive schedule

### Password Vault
Bitwarden-style secrets on your Pi.

- **Item types** — login, secure note, payment card, identity
- **Folders, favorites, trash** — organize, soft-delete, restore, empty trash
- **Family profiles** — tag items to Renish / Deepthi (etc.) like Health Vault; works **before** that person has a login
- **Ownership transfer** — move a login to another family member account; optional keep-access share for the manager
- **Encryption** — passwords, notes, card numbers / CVV, TOTP secrets encrypted at rest
- **Authenticator (TOTP)** — store secrets; live codes in app and web
- **Password history** — previous values kept when you change a login
- **Generator** — strong password / passphrase generation
- **Password health** — weak, reused, missing TOTP, aging passwords
- **Sends** — share text or a login snapshot via link (`/v/{token}`); optional PIN, expiry, max views
- **Send options** — include TOTP; require owner **grant** before revealing; **email OTP** to allowlisted addresses; **first-browser lock** (only the first browser that opens the link can view it until expiry)
- **Access requests** — recipient can request access (optional photo); owner grants or dismisses; blocked second-browser attempts appear here too
- **Live alerts** — FCM push + admin SSE toasts / modal for pending requests
- **Request chat** — short chat on a pending request (owner ↔ recipient)
- **Video verify** — optional WebRTC face / video check before grant
- **Sealed page** — branded locked-door page when a send is expired or out of views
- **Short links** — `/v/{token}` and `/v/{token}/qr` for authenticator setup

### Secret Share
Standalone expiring text shares (same gates as Password Send).

- **Paste a secret** — create a link recipients open without an account (`/v/{token}`)
- **Gates** — PIN, one-time view, grant request, email OTP, authenticator
- **First-browser lock** — bind the reveal to the first browser; other browsers are blocked and logged
- **Access requests** — pending grants and blocked-browser attempts in one list

### Family Vault
Household logins under one vault owner.

- **Invite member** — create a login for a spouse / relative and link it to their profile
- **Private by default** — each member’s passwords / locker docs stay private until shared
- **Per-item share** — view or edit permission to another household login
- **Module** — enable / disable from Super Admin like other modules

### Money Manager
Household ledger.

- **Accounts** — assets and liabilities with balances
- **Transactions** — income / expense with optional receipt images
- **Categories** — hierarchical category tree
- **Stats & reports** — period summaries
- **Budgets (Plan)** — category budgets
- **Recurring** — repeating expenses; mark paid
- **EMIs** — schedules with post / pause; server scheduler auto-posts due EMIs
- **SMS inbox** — ingest bank SMS → AI / rules tagging → accept or ignore as transactions
- **Finance AI rules** — keyword → category rules; uses shared AI providers when configured

### Expense Analyser
Turn bank email and PDF statements into ledger rows.

- **Gmail OAuth sync** — pull card / bank alert mail on a schedule
- **Inbox** — match, ignore, or post into Money Manager
- **Retag & reconcile** — bulk / per-item retag; find gaps
- **Insights** — spend overview
- **Bank PDF import** — upload statements (HDFC, SBI, generic parsers)
- **Mail PDFs** — pull statement attachments; view / download / ignore
- **PDF passwords** — store passwords for encrypted bank PDFs
- **Sync log & clear** — history of runs; wipe analyser data

### AI
Shared intelligence for the vault.

- **Ask AI** — threaded chat with vault-aware context
- **Providers** — add, test, and delete API keys used across modules
- **Usage logs** — per-call usage and summaries
- **Apply actions** — push chat results into shopping list, diary, or finance
- **Ask AI FAB** — optional floating button (web + Android); toggle in settings

### Document Vault (Locker)
IDs and papers that are not hospital records.

- **Types** — Aadhaar, PAN, passport, driving licence, voter ID, certificate, RC, insurance, warranty, property, custom
- **Document scanner (Android)** — Adobe-style scan inside Locker (edge detect, crop, filters, multi-page); optional PDF; copy kept on phone and uploaded encrypted to the vault
- **Encrypted ID numbers & notes** — multi-file attachments
- **Expiry tracking** — expiry date and “expiring soon” filter
- **Pin** — keep important docs at the top

### Shopping List
Shared grocery / errand lists.

- **Lists** — create, categorize, live check-off
- **Trash** — soft-delete / restore
- **Public share** — guests add / toggle / edit via `/shop/{token}`
- **Friends** — contacts; send a list; inbox accept / reject / recall
- **Catalog & quick-add** — saved chips; Manglish → English assist
- **Suggest / recognize** — grocery suggest and recognize helpers
- **Receipts** — attach receipt images to a list
- **Post to Finance** — completed list → Money Manager expense
- **WhatsApp** — share list text from the web UI

### URL Vault
Bookmarks that stay on your server.

- **Links** — CRUD with optional preview fetch
- **Categories & tags** — organize and filter
- **Favorites**
- **Public share** — timed preview links (`/u/{token}`)

### Digital Diary
Private journal with photos.

- **Entries** — freeform notes with timestamps
- **Folders** — organize entries
- **Photos** — attach / download / delete (encrypted on disk)
- **Pinned** — filter pinned entries

### Super Admin
Server control plane (superadmin only).

- **Users** — list accounts; enable / disable modules per vault
- **Block / unblock** — stop a compromised account
- **Disable 2FA / app-approve** — recovery if a device is lost
- **Online now** — presence from `last_seen_at`
- **Failed logins** — attempt log
- **Create user** — invite / signup from SA
- **Server settings** — Google OAuth client, FCM service account, reCAPTCHA, login lockout, mail (system SMTP or custom)

---

## Public links (no account)

| Short URL | Opens |
|-----------|--------|
| `/s/{token}` | Single medical document share |
| `/p/{token}` | Multi-document pack |
| `/v/{token}` | Password Vault Send **or** Secret Share |
| `/v/{token}/qr` | Authenticator setup for a Send (no password on page) |
| `/u/{token}` | Shared bookmark |
| `/shop/{token}` | Collaborative shopping list |
| `/ice/{token}` | Emergency ICE card |

Doc / pack / send shares support optional PIN, expiry, and view limits where configured.

---

## Security & accounts

- **Auth** — email + password; JWT (Android API) and signed session cookie (web admin)
- **Roles** — owner, family member (linked profile login), view-only invitee (scoped), superadmin
- **TOTP 2FA** — setup / enable / disable; enforced on web and API when on
- **App-approve login** — web login waits for Allow / Deny on a signed-in Android device (FCM)
- **QR login** — web shows a challenge QR; app scans and approves
- **Lockout** — configurable max attempts and lockout window (SA)
- **Optional reCAPTCHA** on login (SA)
- **Encryption** — Fernet with `MASTER_KEY` for secrets and files; searchable titles left plaintext by design
- **Module gating** — disabled modules blocked in admin UI and API

**Back up `MASTER_KEY`.** Losing it makes encrypted fields and files permanently unreadable.

---

## Clients

### Web admin (desktop + phone)
`/admin` — full module UI (dark vault theme), module picker, Ask AI FAB, live Send-request toasts via SSE.

- Responsive layout with bottom tab bar / slide-over nav on phones
- Touch-sized controls (44px+), safe-area padding, horizontal profile chips
- Password Vault profile filter, assign-profile, and Secret Share work in mobile Safari / Chrome
- Public share pages (`/v/…`, `/s/…`, `/shop/…`, …) are mobile-first

### Android
Kotlin + Compose hub matching the same modules: family, health, passwords (incl. Sends + profile tags), **Secret Share**, finance, expense analyser, AI, locker, shopping, URLs, diary, settings.

- Runtime **server URL** (Immich-style); probes `/health`
- Encrypted token store + refresh-token retry
- Room cache + sync worker; offline document file cache
- Autofill for vault logins
- FCM + poll for login-approve and Send access requests
- PIN / biometric app lock
- Theme prefs (dark, large text, Ask AI FAB)
- Password list filters by family profile; item screen can assign profile
- Secret Share module with first-browser lock option
- Password / locker Sends include first-browser lock when creating a link

---

## Ops snapshot

- **Target** — Raspberry Pi or any Linux host; SQLite or MySQL via `DATABASE_URL`
- **Process** — uvicorn (systemd sample in `backend/deploy/`); optional Docker + GHCR multi-arch
- **Edge** — nginx reverse proxy; Cloudflare Tunnel documented; SSE location for Send-request stream
- **Scheduler** — Drive backups, due EMIs, expense Gmail sync
- **Mail** — system SMTP env defaults or custom SMTP in Super Admin (for Send email OTP)

---

## Quick start

1. **Backend**: `cd backend`, follow [backend/README.md](backend/README.md) (venv or Docker).
2. **Android**: `cd android`, open in Android Studio, run, enter the server address on first launch.

## CI

Path-filtered workflows so each side builds only when it changes:

- **`backend-ci.yml`** — pytest; on `main`, multi-arch Docker → GHCR
- **`android-ci.yml`** — debug APK + unit tests
- **`android-release.yml`** — release APK on `android-v*` tags (or manual)

## Why one repo

Backend and Android are developed and versioned together. CI is already
scoped per folder; either side can be split out later without rewriting
build pipelines.
