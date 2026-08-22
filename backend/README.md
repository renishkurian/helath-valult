# Vault Hub API

FastAPI backend for Vault Hub (Health Vault, Password Vault, Money Manager,
Expense Analyser, AI, Document Vault, Shopping List, URL Vault, Digital Diary).
Sensitive fields and files are encrypted at rest with `MASTER_KEY`. Browser
admin UI and Android app share this API.

Module overview and public share links: see the **[root README](../README.md)**.


## Quick start (local test)

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# fill in JWT_SECRET and MASTER_KEY (commands to generate them are in the file)

uvicorn app.main:app --reload
```

Visit `http://localhost:8000/docs` for interactive API docs (Swagger UI), or
`http://localhost:8000/admin` for the browser admin UI (see below).

## CI/CD

`.github/workflows/backend-ci.yml` runs on every push/PR:
- **Tests** (`pytest`) — 9 tests covering register/login, family members,
  cards, cross-account isolation (user B can't touch user A's data),
  encrypted upload/download (asserts the on-disk file never contains the
  plaintext), search, reminders, and the admin UI login flow.
- **Docker build** (main branch only) — builds a multi-arch image
  (`linux/amd64` + `linux/arm64`, so it runs natively on the Pi without
  emulation) and pushes it to GitHub Container Registry as
  `ghcr.io/<you>/healthvault-backend:latest`.

To use it:
1. Push this to a GitHub repo.
2. Edit `docker-compose.yml` — replace `<your-github-username>` in the
   `image:` line with your actual GitHub username/org.
3. The GHCR package is private by default. Either make it public (package
   settings → Change visibility), or `docker login ghcr.io` on the Pi with a
   [personal access token](https://github.com/settings/tokens) that has
   `read:packages` scope.
4. On the Pi: `docker compose pull && docker compose up -d` — no build step
   needed, since CI already built it for arm64.

If you'd rather build on-device instead of pulling from GHCR, swap the
`image:` line in `docker-compose.yml` for `build: .` (commented out right
above it).

## Deploying on the Pi (systemd + nginx)

The Pi runs uvicorn as a systemd service on `127.0.0.1:8076`, behind nginx
and a Cloudflare Tunnel at `https://vault.rklab.online`. Copy-paste install
is in **[deploy/README.md](deploy/README.md)**.

## Deploying on the Pi (Docker, matches your MarketMind setup)

```bash
cd backend
cp .env.example .env
nano .env   # set JWT_SECRET, MASTER_KEY, and DATABASE_URL

docker compose up -d --build
```

The API will be reachable at `http://192.168.0.50:8000` on your LAN, or over
WireGuard when you're out. Point the Android app's base URL at whichever one
you use.

**Back up `MASTER_KEY` somewhere durable (e.g. Vaultwarden).** If it's lost,
every encrypted card field and every uploaded file becomes permanently
unreadable — there's no recovery path by design.

## Using your existing MySQL instead of SQLite

Since you already run MySQL on the Pi for MarketMind, you can point this at
it instead:

```
DATABASE_URL=mysql+pymysql://healthvault:PASSWORD@127.0.0.1:3306/healthvault
```

Create the DB/user first:
```sql
CREATE DATABASE healthvault CHARACTER SET utf8mb4;
CREATE USER 'healthvault'@'%' IDENTIFIED BY 'PASSWORD';
GRANT ALL PRIVILEGES ON healthvault.* TO 'healthvault'@'%';
```

Tables are created automatically on first run.

## How encryption works

- **Text fields** (patient ID numbers, notes) are encrypted with Fernet
  (AES-128-CBC + HMAC) before being written to the database, using
  `MASTER_KEY`.
- **Uploaded files** are encrypted the same way before touching disk —
  `storage/` never contains a readable file. Decryption happens in-memory
  only when you call the download endpoint, authenticated to your account.
- Searchable fields (hospital name, document title) are intentionally left
  in plaintext so `/search` can query them with a simple `LIKE`. If you want
  those encrypted too later, the trade-off is losing SQL-level search and
  needing to filter client-side after decrypting per-row — worth revisiting
  if this ever leaves your home network.

## Admin web UI

`http://<your-pi>:8000/admin` — browser UI for every enabled module (same
accounts as the Android app). Log in with email/password; optional TOTP,
app-approve, and QR login when configured.

Covers:
- **Module picker** — open only what Super Admin enabled for the vault
- **Family Vault** — invite household logins; link to profiles; private shares
- **Health** — family, cards, documents, care, reminders, shares, ICE, audit, storage
- **Passwords** — items, profile tags, ownership transfer, generator, health report, Sends (grant / email OTP / first-browser lock / requests)
- **Secret Share** — paste text → expiring `/v/` link with the same gates + first-browser lock
- **Finance** — accounts, ledger, budgets, EMIs, SMS inbox
- **Expense Analyser** — Gmail sync, PDF statements, insights
- **AI, Locker, Shopping List, URLs, Diary** — as in the [root README](../README.md)
- **Super Admin** — users, modules, presence, failed logins, server settings (OAuth, FCM, mail, lockout)

Phone browsers use the same `/admin` UI (responsive CSS, touch targets, profile chip scroller).
The Android app covers the same modules over JWT (see root README → Clients).

It uses a signed session cookie (separate from the mobile JWT), so web and
phone sessions do not invalidate each other. Cookies are signed with
`JWT_SECRET`.

Public share pages (doc, pack, Send, Secret Share, shop, URL, ICE) do not require login.
Keep admin behind LAN / WireGuard / your tunnel edge the same way you would
the API.


## API overview

Interactive docs: `http://localhost:8000/docs` (Swagger).

Auth: register / login / refresh / me; optional TOTP; app-approve and QR
challenges; viewer invites; device tokens for FCM.

Most module routes require `Authorization: Bearer <access_token>` and respect
per-vault module enablement. Public exceptions include share / Send / shop /
ICE pages and short-link redirects (`/s`, `/p`, `/v`, `/u`, `/shop`, `/ice`).

Core health-oriented examples:

| Method | Path                          | Purpose                                  |
|--------|-------------------------------|-------------------------------------------|
| POST   | `/auth/register`              | Create account (auto-creates a "self" person) |
| POST   | `/auth/login`                 | Get access + refresh tokens               |
| POST   | `/auth/refresh`                | Exchange refresh token for new tokens     |
| GET    | `/auth/me`                     | Current user                              |
| GET    | `/people`                      | List self + family members                |
| POST   | `/people`                      | Add a family member                       |
| PATCH  | `/people/{id}`                 | Update a person                           |
| DELETE | `/people/{id}`                 | Remove a family member                    |
| GET    | `/cards?person_id=`            | List hospital cards (optionally per person) |
| POST   | `/cards`                       | Add a hospital card                       |
| PATCH  | `/cards/{id}`                  | Update a card                             |
| DELETE | `/cards/{id}`                  | Delete a card                             |
| GET    | `/documents?person_id=&category=` | List documents                        |
| POST   | `/documents` (multipart)       | Upload a document                         |
| GET    | `/documents/{id}/download`     | Download (decrypted) file                 |
| DELETE | `/documents/{id}`              | Delete a document                         |
| GET    | `/reminders?person_id=`        | List reminders                            |
| POST   | `/reminders`                   | Create a reminder                         |
| PATCH  | `/reminders/{id}`              | Update a reminder                         |
| DELETE | `/reminders/{id}`              | Delete a reminder                         |
| GET    | `/search?q=&person_id=`        | Search cards + documents by title, tags, and OCR/PDF text |
| POST   | `/share`                       | Timed read-only link for a document (hospital front desk) |
| GET    | `/share/public/{token}`        | Public view of a shared document (no login) |
| GET    | `/labs/trends?person_id=`      | Parsed lab/vital values over time |
| GET    | `/backup/export`               | Zip of the vault (`?person_id=` for one person, `?password=` to encrypt) |
| POST   | `/backup/restore`              | Restore an exported zip / encrypted backup |
| POST   | `/auth/invite`                 | Create a view-only login for this vault |
| GET    | `/audit`                       | Who viewed/downloaded/shared what |

Additional prefixes (see Swagger for full lists): `/vault`, `/secrets`, `/family`,
`/finance`, `/expense-analyser`, `/ai`, `/locker`, `/tracker`, `/urls`, `/diary`,
`/storage`, `/health` (care APIs).

`category` for health documents is one of: `hospital_card`, `prescription`,
`lab_report`, `insurance`, `vaccination`, `bill`, `medicine`, `other`.

## Notes

- Prefer LAN / WireGuard / your tunnel edge for admin and API access.
- Login lockout and optional reCAPTCHA are configurable in Super Admin →
  Server settings; TOTP and app-approve further harden accounts.
- The reminder model stores `repeat_rule`; the Android app schedules local
  notifications. Server-side push for care reminders is not a separate
  product feature beyond FCM used for login-approve and Send requests.
- Back up `storage/` and the database together — encrypted files need the
  DB (and `MASTER_KEY`) to be useful.
- Feature inventory lives in the **[root README](../README.md)**.
