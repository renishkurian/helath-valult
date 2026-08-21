"""Per-module vault 2FA locks (Password / Document / Health)."""
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
    """Return current TOTP code for the user after enabling authenticator."""
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

    # Fresh code after enable may still be in same 30s window
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

    # People listing is not behind the health document lock
    people = client.get("/people", headers=h)
    assert people.status_code == 200
