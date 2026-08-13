# Health Vault API

FastAPI backend for the Health Vault Android app. Stores hospital ID cards,
medical documents (bills, reports, prescriptions, medicine photos), family
member profiles, and reminders — with sensitive fields and files encrypted
at rest.

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

`http://<your-pi>:8000/admin` — a browser version of the app, styled to
match the mobile app's design system (parchment background, navy ID cards,
folder tabs, ledger-style document lists). Log in with the same
email/password as any account you've registered (via the app or
`/auth/register`).

Covers everything the API supports:
- Dashboard: family switcher, hospital ID cards, expiry alerts, folders,
  recent documents
- Family: add/remove family members
- Per-person hospital cards: add/delete (patient ID stored encrypted)
- Documents: upload/download/delete, filtered by category
- Reminders: add/delete, with repeat rules

It uses its own signed session cookie (separate from the mobile app's JWT),
so logging in on the web doesn't log you out of the phone and vice versa.
Session cookies are signed with `JWT_SECRET` — make sure that's set to
something real in `.env` before exposing this beyond localhost.

**This is unauthenticated to the wider internet only by your network setup**
— it has login, but no rate limiting or 2FA. Keep it behind WireGuard/LAN
only, same as you would want for the API itself.

## API overview

All endpoints except `/auth/register` and `/auth/login` require
`Authorization: Bearer <access_token>`.

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

`category` for documents is one of: `hospital_card`, `prescription`,
`lab_report`, `insurance`, `vaccination`, `bill`, `medicine`, `other`.

## Notes / next steps worth considering

- Add rate limiting on `/auth/login` (e.g. slowapi) before exposing this
  outside your WireGuard network.
- The reminder model stores `repeat_rule` but this API doesn't send
  notifications itself — the Android app schedules local notifications via
  WorkManager based on `remind_at`. If you want push reminders that fire
  even when the phone hasn't synced recently, that'd need a small scheduler
  job on the Pi plus FCM, which isn't included here.
- Consider a periodic `storage/` backup (restic/rclone) to somewhere off the
  Pi — encrypted files are useless without the DB, and vice versa, so back
  up both together.
