from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import settings
from app.database import SessionLocal
from app import models
from app.login_guard import failed_count, rate_limited

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_login_attempts():
    db = SessionLocal()
    try:
        db.query(models.LoginAttempt).delete(synchronize_session=False)
        db.query(models.ServerSetting).filter(models.ServerSetting.key.in_((
            "recaptcha_site_key", "recaptcha_secret", "recaptcha_enabled",
            "login_max_attempts", "login_lockout_minutes", "login_rate_limit_enabled",
        ))).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()
    yield


def _register(email="lock@example.com"):
    r = client.post(
        "/auth/register",
        json={"email": email, "password": "password123", "full_name": "Lock User"},
    )
    assert r.status_code == 201, r.text


def test_login_page_skips_recaptcha_when_keys_empty():
    fresh = TestClient(app)
    r = fresh.get("/admin/login")
    assert r.status_code == 200
    assert "g-recaptcha" not in r.text
    assert "recaptcha/api.js" not in r.text


def test_html_login_requires_recaptcha_when_configured(monkeypatch):
    monkeypatch.setattr(settings, "RECAPTCHA_SITE_KEY", "test-site-key")
    monkeypatch.setattr(settings, "RECAPTCHA_SECRET", "test-secret")
    fresh = TestClient(app)
    email = "captcha@example.com"
    r = fresh.post(
        "/auth/register",
        json={"email": email, "password": "password123", "full_name": "Captcha User"},
    )
    assert r.status_code == 201, r.text
    page = fresh.get("/admin/login")
    assert page.status_code == 200
    assert "g-recaptcha" in page.text
    assert "test-site-key" in page.text
    blocked = fresh.post("/admin/login", data={"email": email, "password": "password123"})
    assert blocked.status_code == 401
    assert "not a robot" in blocked.text
    # Android / API login must still work without a widget.
    api = fresh.post("/auth/login", data={"username": email, "password": "password123"})
    assert api.status_code == 200
    assert "access_token" in api.json()


def test_failed_admin_login_is_logged():
    _register()
    r = client.post("/admin/login", data={"email": "lock@example.com", "password": "wrong-pass"})
    assert r.status_code == 401
    assert "Incorrect email or password" in r.text
    db = SessionLocal()
    try:
        rows = db.query(models.LoginAttempt).filter(models.LoginAttempt.email == "lock@example.com").all()
        assert len(rows) == 1
        assert rows[0].success is False
        assert rows[0].reason == "bad_credentials"
    finally:
        db.close()


def test_unknown_email_is_still_logged():
    r = client.post("/admin/login", data={"email": "nobody@example.com", "password": "x"})
    assert r.status_code == 401
    db = SessionLocal()
    try:
        n = db.query(models.LoginAttempt).filter(models.LoginAttempt.email == "nobody@example.com").count()
        assert n == 1
    finally:
        db.close()


def test_login_lockout_after_threshold(monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "LOGIN_LOCKOUT_MINUTES", 15)
    _register("gated@example.com")
    for _ in range(3):
        client.post("/admin/login", data={"email": "gated@example.com", "password": "nope"})
    r = client.post("/admin/login", data={"email": "gated@example.com", "password": "password123"})
    assert r.status_code == 401
    assert "Too many failed attempts" in r.text
    api = client.post("/auth/login", data={"username": "gated@example.com", "password": "password123"})
    assert api.status_code == 429


def test_successful_html_login_is_logged():
    _register("oklogin@example.com")
    r = client.post(
        "/admin/login",
        data={"email": "oklogin@example.com", "password": "password123"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "Your vaults" in r.text
    db = SessionLocal()
    try:
        row = db.query(models.LoginAttempt).filter(
            models.LoginAttempt.email == "oklogin@example.com",
            models.LoginAttempt.success.is_(True),
        ).first()
        assert row is not None
        user = db.query(models.User).filter(models.User.email == "oklogin@example.com").first()
        assert user.last_seen_at is not None
    finally:
        db.close()


def test_rate_limited_helper_counts_email_and_ip(monkeypatch):
    monkeypatch.setattr(settings, "LOGIN_MAX_ATTEMPTS", 2)
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        for i in range(2):
            db.add(models.LoginAttempt(
                email="a@example.com", ip="1.2.3.4", success=False,
                reason="bad_credentials", created_at=now - timedelta(seconds=i),
            ))
        db.commit()
        blocked, mins = rate_limited(db, "a@example.com", "9.9.9.9")
        assert blocked is True
        assert mins >= 1
        assert failed_count(db, email="a@example.com") == 2
    finally:
        db.close()
