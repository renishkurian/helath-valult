"""Login rate limiting, failed-attempt log, reCAPTCHA, and last-seen heartbeat."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from fastapi import Request
from sqlalchemy.orm import Session

from app import models, security
from app.config import settings
from app.database import SessionLocal


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client:
        return (request.client.host or "")[:64]
    return None


def client_ua(request: Request) -> str:
    return (request.headers.get("user-agent") or "")[:400]


def recaptcha_enabled() -> bool:
    return bool(settings.RECAPTCHA_SITE_KEY and settings.RECAPTCHA_SECRET)


def verify_recaptcha(token: str, ip: str | None) -> bool:
    if not recaptcha_enabled():
        return True
    if not (token or "").strip():
        return False
    body = urllib.parse.urlencode({
        "secret": settings.RECAPTCHA_SECRET,
        "response": token.strip(),
        "remoteip": ip or "",
    }).encode()
    req = urllib.request.Request(
        "https://www.google.com/recaptcha/api/siteverify",
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            payload = json.loads(resp.read().decode() or "{}")
        return bool(payload.get("success"))
    except Exception:
        return False


def log_attempt(
    db: Session,
    *,
    email: str,
    ip: str | None,
    user_agent: str,
    success: bool,
    reason: str,
) -> None:
    # Own session so a commit here does not expire objects on the request session.
    own = SessionLocal()
    try:
        own.add(models.LoginAttempt(
            email=(email or "")[:255],
            ip=ip,
            user_agent=(user_agent or "")[:400],
            success=success,
            reason=(reason or "bad_credentials")[:40],
        ))
        own.commit()
    finally:
        own.close()


def _window_start() -> datetime:
    return datetime.utcnow() - timedelta(minutes=max(1, settings.LOGIN_LOCKOUT_MINUTES))


def failed_count(db: Session, *, email: str | None = None, ip: str | None = None) -> int:
    q = db.query(models.LoginAttempt).filter(
        models.LoginAttempt.success.is_(False),
        models.LoginAttempt.created_at >= _window_start(),
        models.LoginAttempt.reason.in_(("bad_credentials", "totp_bad", "recaptcha")),
    )
    if email:
        q = q.filter(models.LoginAttempt.email == email)
    elif ip:
        q = q.filter(models.LoginAttempt.ip == ip)
    else:
        return 0
    return q.count()


def rate_limited(db: Session, email: str, ip: str | None) -> tuple[bool, int]:
    """Return (blocked, minutes remaining)."""
    limit = max(1, settings.LOGIN_MAX_ATTEMPTS)
    window = max(1, settings.LOGIN_LOCKOUT_MINUTES)
    email_hits = failed_count(db, email=email) if email else 0
    ip_hits = failed_count(db, ip=ip) if ip else 0
    if email_hits < limit and ip_hits < limit:
        return False, 0
    return True, window


def touch_last_seen(user: models.User) -> None:
    now = datetime.utcnow()
    if user.last_seen_at and (now - user.last_seen_at).total_seconds() < 60:
        return
    db = SessionLocal()
    try:
        db.query(models.User).filter(models.User.id == user.id).update(
            {"last_seen_at": now}, synchronize_session=False,
        )
        db.commit()
        user.last_seen_at = now
    finally:
        db.close()


def online_since() -> datetime:
    return datetime.utcnow() - timedelta(minutes=max(1, settings.ONLINE_WINDOW_MINUTES))


def is_online(user: models.User) -> bool:
    return bool(user.last_seen_at and user.last_seen_at >= online_since())


def authenticate(
    db: Session,
    request: Request,
    *,
    email: str,
    password: str,
    recaptcha_token: str = "",
    check_recaptcha: bool = False,
) -> tuple[models.User | None, str | None]:
    """Shared HTML + API login. Returns (user, error). Never reveals whether the email exists."""
    email_norm = (email or "").strip().lower()
    ip = client_ip(request)
    ua = client_ua(request)

    blocked, retry = rate_limited(db, email_norm, ip)
    if blocked:
        log_attempt(db, email=email_norm, ip=ip, user_agent=ua, success=False, reason="rate_limited")
        return None, f"Too many failed attempts. Try again in {retry} minute(s)."

    if check_recaptcha and not verify_recaptcha(recaptcha_token, ip):
        log_attempt(db, email=email_norm, ip=ip, user_agent=ua, success=False, reason="recaptcha")
        return None, "Please confirm you are not a robot."

    user = db.query(models.User).filter(models.User.email == email_norm).first()
    if not user:
        user = db.query(models.User).filter(models.User.email == (email or "").strip()).first()
    if not user or not security.verify_password(password, user.hashed_password):
        log_attempt(db, email=email_norm, ip=ip, user_agent=ua, success=False, reason="bad_credentials")
        return None, "Incorrect email or password"

    from app.totp import is_enabled as totp_on
    needs_totp = totp_on(user)
    log_attempt(
        db, email=email_norm, ip=ip, user_agent=ua, success=True,
        reason="totp_pending" if needs_totp else "ok",
    )
    if not needs_totp:
        touch_last_seen(user)
    return user, None
