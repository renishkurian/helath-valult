"""Render every admin page against a throwaway DB and report failures.

Also reports class names used in templates that no stylesheet defines, which
catches markup left behind after the Bootstrap conversion.

Usage: ./venv/bin/python smoke_pages.py
"""
import os
import re
import shutil
import sys
from pathlib import Path

os.environ.setdefault("MASTER_KEY", "mIN27fAPCnrASKIwM8I6Mac9LqKm3g0jYyt6xxW9Zyk=")
os.environ.setdefault("JWT_SECRET", "smoke-secret")
os.environ.setdefault("DATABASE_URL", "sqlite:///./smoke.db")
os.environ.setdefault("STORAGE_DIR", "./smoke_storage")

# Derive artifact paths from the env so parallel runs can use separate DBs:
#   DATABASE_URL=sqlite:///./smoke-pw.db STORAGE_DIR=./smoke_pw_storage python smoke_pages.py
DB_PATH = os.environ["DATABASE_URL"].split("///")[-1]
STORAGE_PATH = os.environ["STORAGE_DIR"]

for _p in (DB_PATH, STORAGE_PATH):
    p = Path(_p)
    if p.is_dir():
        shutil.rmtree(p, ignore_errors=True)
    elif p.exists():
        p.unlink()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

EMAIL = "smoke@example.com"
PASSWORD = "smoke-pass-1234"

client = TestClient(app, follow_redirects=False)

r = client.post("/auth/register", json={"email": EMAIL, "password": PASSWORD, "full_name": "ravi kumar"})
assert r.status_code < 400, ("register failed", r.status_code, r.text[:400])
r = client.post("/admin/login", data={"email": EMAIL, "password": PASSWORD})
assert r.status_code in (302, 303), ("login failed", r.status_code, r.text[:400])


def post(path, **kwargs):
    resp = client.post(path, **kwargs)
    if resp.status_code >= 400:
        print(f"  seed warning: {path} -> {resp.status_code} {resp.text[:120]}")
    return resp


print("seeding...")
post("/admin/family/add", data={"name": "asha kumar", "relation": "spouse", "blood_group": "O+"})

import sqlite3  # noqa: E402

db = sqlite3.connect(DB_PATH)


def one(sql):
    try:
        row = db.execute(sql).fetchone()
        return row[0] if row else None
    except Exception:
        return None


person_id = one("select id from people limit 1")
post("/admin/cards/add", data={
    "person_id": person_id, "hospital_name": "city hospital", "ward": "B2",
    "blood_group": "O+", "patient_id": "PT-1001", "valid_till": "2027-01-01",
})
post("/admin/reminders/add", data={
    "person_id": person_id, "title": "dentist follow-up",
    "remind_at": "2026-12-01T09:00", "description": "bring the old x-ray",
})
post("/admin/documents/add", data={"person_id": person_id, "title": "blood work", "category": "lab_report"},
     files={"file": ("report.txt", b"cbc normal", "text/plain")})
post("/admin/passwords/add", data={
    "item_type": "login", "name": "netflix", "username": "ravi",
    "password": "hunter2hunter2", "uris": "https://netflix.com", "notes": "family plan",
})
post("/admin/passwords/add", data={"item_type": "note", "name": "wifi codes", "notes": "guest: vault-guest"})
post("/admin/passwords/sends", data={
    "name": "share password", "send_type": "text", "text": "temp-pass-99", "expires_in_hours": "24",
})
post("/admin/finance/accounts/add", data={"name": "hdfc savings", "account_type": "bank", "opening_balance": "25000"})
account_id = one("select id from finance_accounts limit 1") or ""
post("/admin/finance/add", data={
    "txn_type": "expense", "account_id": account_id, "amount": "480",
    "txn_date": "2026-08-01", "payee": "milk booth", "notes": "monthly",
})
post("/admin/finance/add", data={
    "txn_type": "income", "account_id": account_id, "amount": "62000",
    "txn_date": "2026-08-01", "payee": "salary",
})
post("/admin/locker/add", data={
    "title": "aadhaar card", "doc_type": "aadhaar", "id_number": "1234 5678 9012",
    "holder_name": "ravi kumar", "expiry_date": "2027-03-01",
}, files={"files": ("aadhaar.txt", b"scan placeholder", "text/plain")})
post("/admin/urls/add", data={"url": "https://example.com/reading", "title": "reading list", "notes": "later"})

db.close()
db = sqlite3.connect(DB_PATH)
db.execute("UPDATE users SET role = 'superadmin' WHERE email = ?", (EMAIL.lower(),))
db.commit()
pw_id = one("select id from vault_items limit 1")
lk_id = one("select id from locker_documents limit 1") or one("select id from locker_items limit 1")
url_id = one("select id from url_items limit 1") or one("select id from saved_urls limit 1")
doc_id = one("select id from documents limit 1")
acct_id = one("select id from finance_accounts limit 1")
db.close()

PAGES = [
    "/admin/modules", "/admin", f"/admin?person={person_id}",
    "/admin/family", f"/admin/documents?person={person_id}&category=lab_report",
    f"/admin/care?person={person_id}", f"/admin/reminders?person={person_id}",
    "/admin/shares", "/admin/activity", "/admin/storage", "/admin/security",
    "/admin/passwords", "/admin/passwords?q=net", "/admin/passwords?item_type=note",
    "/admin/passwords/generator", "/admin/passwords/health",
    "/admin/passwords/sends", "/admin/passwords/trash",
    "/admin/finance", "/admin/finance?view=calendar", "/admin/finance?view=monthly", "/admin/finance?view=total",
    "/admin/finance/add", "/admin/finance/add?txn_type=income", "/admin/finance/stats",
    "/admin/finance/accounts", "/admin/finance/more",
    "/admin/finance/categories", "/admin/finance/plan", "/admin/finance/recurring", "/admin/finance/ai",
    "/admin/ai", "/admin/ai/providers",
    "/admin/locker", "/admin/locker?expiring=1", "/admin/locker/add",
    "/admin/urls", "/admin/urls?favorite=1", "/admin/urls/add", "/admin/urls/manage",
    "/admin/sa", "/admin/sa/users", "/admin/sa/online", "/admin/sa/logins",
    "/admin/sa/signup", "/admin/sa/settings", "/admin/sa/users?q=smoke", "/admin/sa/logins?outcome=all",
    "/admin/login/qr",
]
if pw_id:
    PAGES.append(f"/admin/passwords/{pw_id}")
if lk_id:
    PAGES.append(f"/admin/locker/{lk_id}")
if url_id:
    PAGES.append(f"/admin/urls/{url_id}")
if acct_id:
    PAGES.append(f"/admin/finance/accounts/{acct_id}")

follow = TestClient(app, follow_redirects=True)
follow.cookies = client.cookies

fails = []
for path in PAGES:
    try:
        resp = follow.get(path)
    except Exception as exc:
        fails.append((path, "EXC", f"{type(exc).__name__}: {exc}"))
        continue
    if resp.status_code != 200:
        fails.append((path, resp.status_code, resp.text[:300].replace("\n", " ")))
        continue
    if "Traceback (most recent call last)" in resp.text:
        fails.append((path, "TRACEBACK", resp.text[:300]))
        continue
    # A lost session redirects to the sign-in page, which also answers 200 —
    # without this check every page would "pass" while rendering the login form.
    if "auth-wrap" in resp.text or "Vault — Sign in" in resp.text:
        fails.append((path, "LOGIN-REDIRECT", "page rendered the sign-in screen, not the requested view"))

out = TestClient(app, follow_redirects=True)
resp = out.get("/admin/login")
if resp.status_code != 200:
    fails.append(("/admin/login", resp.status_code, resp.text[:200]))

print(f"\nchecked {len(PAGES) + 1} pages")
for f in fails:
    print("FAIL", f[0], "->", f[1])
    print("     ", str(f[2])[:400])
print("RESULT:", "OK" if not fails else f"{len(fails)} FAILING")

# ---------------------------------------------------------------------------
# Undefined-class report: any class used in a template but defined by no CSS.
# ---------------------------------------------------------------------------
static = Path("app/static")
defined = set()
for css in (static / "vendor/bootstrap.min.css", static / "vendor/bootstrap-icons.min.css", static / "vault.css"):
    if css.exists():
        defined |= set(re.findall(r"\.(-?[A-Za-z_][\w-]*)", css.read_text()))

JINJA = re.compile(r"\{\{.*?\}\}|\{%.*?%\}", re.S)
IGNORE_PREFIX = ("js-", "bi-")
IGNORE = {"active", "on", "open", "show", "collapsed", "selected", "current", "h-100", "w-100"}

used = {}
for tpl in sorted(Path("app/templates").glob("*.html")):
    text = tpl.read_text()
    for attr in re.findall(r'class="([^"]*)"', text):
        for name in JINJA.sub(" ", attr).split():
            if not re.fullmatch(r"-?[A-Za-z_][\w-]*", name):
                continue
            if name.startswith(IGNORE_PREFIX) or name in IGNORE or name in defined:
                continue
            used.setdefault(tpl.name, set()).add(name)

if used:
    print("\nclasses with no CSS definition (unstyled markup):")
    for name in sorted(used):
        print(f"  {name}: {', '.join(sorted(used[name]))}")
else:
    print("\nevery template class is defined in CSS")

sys.exit(1 if fails else 0)
