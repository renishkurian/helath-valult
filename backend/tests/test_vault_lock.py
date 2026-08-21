"""Per-module vault locks (Password / Document / Health) and per-item 2FA locks."""
from fastapi.testclient import TestClient

from app.main import app
from app import security, totp as totp_util, crypto
from app.database import SessionLocal
from app import models

client = TestClient(app)


def _register(email: str):
    r = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "full_name": "Lock Tester"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _headers(token: str, unlock: str | None = None) -> dict:
    h = {"Authorization": f"Bearer {token}"}
    if unlock:
        h["X-Vault-Unlock"] = unlock
    return h


def _enable_totp(user_id: str) -> str:
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        secret = totp_util.begin_setup(user)
        totp_util.enable(user)
        db.commit()
        return security.totp_code(secret)
    finally:
        db.close()


def _user_id_from_token(token: str) -> str:
    return security.decode_token(token)["sub"]


def test_vault_lock_blocks_locker_until_unlocked():
    data = _register("vaultlock_locker@example.com")
    token = data["access_token"]
    uid = _user_id_from_token(token)
    code = _enable_totp(uid)
    h = _headers(token)

    st = client.get("/auth/vault-lock", headers=h)
    assert st.status_code == 200
    assert st.json()["locker"] is False

    r = client.post(
        "/auth/vault-lock",
        json={"module": "locker", "enabled": True, "code": code},
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["lock_locker"] is True

    blocked = client.get("/locker/folders", headers=h)
    assert blocked.status_code == 423, blocked.text
    detail = blocked.json()["detail"]
    assert detail["code"] == "vault_locked"
    assert detail["module"] == "locker"

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == uid).first()
        secret = crypto.decrypt_text(user.totp_secret_enc)
        unlock_code = security.totp_code(secret)
    finally:
        db.close()

    unlocked = client.post(
        "/auth/vault-lock/unlock",
        json={"module": "locker", "code": unlock_code, "method": "totp"},
        headers=h,
    )
    assert unlocked.status_code == 200, unlocked.text
    unlock_token = unlocked.json()["unlock_token"]

    ok = client.get("/locker/folders", headers=_headers(token, unlock_token))
    assert ok.status_code == 200, ok.text


def test_vault_lock_health_blocks_documents():
    data = _register("vaultlock_health@example.com")
    token = data["access_token"]
    uid = _user_id_from_token(token)
    code = _enable_totp(uid)
    h = _headers(token)

    r = client.post(
        "/auth/vault-lock",
        json={"module": "health", "enabled": True, "code": code},
        headers=h,
    )
    assert r.status_code == 200, r.text

    blocked = client.get("/documents", headers=h)
    assert blocked.status_code == 423

    people = client.get("/people", headers=h)
    assert people.status_code == 200


def test_item_require_2fa_flag_on_locker():
    data = _register("itemlock_locker@example.com")
    token = data["access_token"]
    uid = _user_id_from_token(token)
    _enable_totp(uid)
    h = _headers(token)

    db = SessionLocal()
    try:
        item = models.LockerItem(user_id=uid, title="PAN Card", doc_type="pan", require_2fa=True)
        db.add(item)
        db.commit()
        item_id = item.id
    finally:
        db.close()

    listed = client.get("/locker", headers=h)
    assert listed.status_code == 200, listed.text
    row = next(x for x in listed.json() if x["id"] == item_id)
    assert row["require_2fa"] is True
