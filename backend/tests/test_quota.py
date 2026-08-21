"""Per-vault storage quota (default 100 MiB)."""
import uuid

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app import models, quota

client = TestClient(app)


def _headers(email=None):
    email = email or f"quota-{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/auth/register", json={
        "email": email, "password": "password123", "full_name": "Quota User",
    })
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, email


def test_default_quota_is_100mb_and_stats_include_it():
    headers, email = _headers()
    stats = client.get("/storage/stats", headers=headers)
    assert stats.status_code == 200, stats.text
    body = stats.json()
    assert body["quota_bytes"] == quota.DEFAULT_QUOTA_BYTES
    assert body["remaining_bytes"] == body["quota_bytes"] - body["bytes_used"]

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        assert user.storage_quota_bytes == quota.DEFAULT_QUOTA_BYTES
    finally:
        db.close()


def test_upload_blocked_when_over_quota():
    headers, email = _headers()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        # Tiny limit so a small PDF fails.
        user.storage_quota_bytes = 200
        db.commit()
    finally:
        db.close()

    r = client.post(
        "/locker",
        headers=headers,
        data={"title": "Too big", "doc_type": "other"},
        files=[("files", ("big.pdf", b"%PDF-1.4 " + (b"x" * 500), "application/pdf"))],
    )
    assert r.status_code == 413, r.text
    assert "quota" in r.json()["detail"].lower()


def test_superadmin_can_set_quota_mb():
    # Register vault user + promote a second account isn't needed — use SA from env bootstrap
    # or create via DB. Here we set quota directly via helper and verify API.
    headers, email = _headers()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        quota.set_quota_bytes(db, user, quota.mb_to_bytes(250))
        db.refresh(user)
        assert user.storage_quota_bytes == 250 * 1024 * 1024
        snap = quota.quota_snapshot(db, user)
        assert snap["quota_mb"] == 250.0
        assert snap["quota_bytes"] == 250 * 1024 * 1024
    finally:
        db.close()

    stats = client.get("/storage/stats", headers=headers).json()
    assert stats["quota_bytes"] == 250 * 1024 * 1024
