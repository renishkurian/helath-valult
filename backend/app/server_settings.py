"""Encrypted server-wide settings, edited in Super Admin."""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session

from app import crypto, models

GOOGLE_CLIENT_ID_KEY = "google_client_id"
GOOGLE_CLIENT_SECRET_KEY = "google_client_secret"
FCM_SERVICE_ACCOUNT_KEY = "fcm_service_account"
TELEGRAM_BOT_TOKEN_KEY = "telegram_bot_token"
RECAPTCHA_SITE_KEY_KEY = "recaptcha_site_key"
RECAPTCHA_SECRET_KEY = "recaptcha_secret"
RECAPTCHA_ENABLED_KEY = "recaptcha_enabled"
LOGIN_MAX_ATTEMPTS_KEY = "login_max_attempts"
LOGIN_LOCKOUT_MINUTES_KEY = "login_lockout_minutes"
LOGIN_RATE_LIMIT_ENABLED_KEY = "login_rate_limit_enabled"

MAIL_MODE_KEY = "mail_mode"
SMTP_HOST_KEY = "smtp_host"
SMTP_PORT_KEY = "smtp_port"
SMTP_USER_KEY = "smtp_user"
SMTP_PASSWORD_KEY = "smtp_password"
SMTP_FROM_KEY = "smtp_from"
SMTP_TLS_KEY = "smtp_tls"

LOGIN_ATTEMPTS_MIN, LOGIN_ATTEMPTS_MAX = 1, 50
LOGIN_LOCKOUT_MIN, LOGIN_LOCKOUT_MAX = 1, 1440


def _row(db: Session, key: str) -> models.ServerSetting | None:
    return db.query(models.ServerSetting).filter(models.ServerSetting.key == key).first()


def get_plain(db: Session, key: str) -> str:
    row = _row(db, key)
    return (row.value or "").strip() if row else ""


def get_secret(db: Session, key: str) -> str:
    row = _row(db, key)
    if not row or not row.value_enc:
        return ""
    return (crypto.decrypt_text(row.value_enc) or "").strip()


def put_plain(db: Session, key: str, value: str) -> None:
    text = (value or "").strip()
    row = _row(db, key)
    if not row:
        row = models.ServerSetting(key=key)
        db.add(row)
    row.value = text or None
    row.updated_at = datetime.utcnow()


def put_secret(db: Session, key: str, value: str) -> None:
    text = (value or "").strip()
    if not text:
        return
    row = _row(db, key)
    if not row:
        row = models.ServerSetting(key=key)
        db.add(row)
    row.value_enc = crypto.encrypt_text(text)
    row.updated_at = datetime.utcnow()


def google_app(db: Session) -> tuple[str, str]:
    return get_plain(db, GOOGLE_CLIENT_ID_KEY), get_secret(db, GOOGLE_CLIENT_SECRET_KEY)


def google_app_saved(db: Session) -> bool:
    cid, secret = google_app(db)
    return bool(cid and secret)


def parse_service_account(raw: str) -> dict | None:
    text = (raw or "").strip()
    if not text.startswith("{"):
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("type") != "service_account":
        return None
    if not (data.get("project_id") and data.get("client_email") and data.get("private_key")):
        return None
    return data


def fcm_service_account(db: Session | None = None) -> dict | None:
    """Dashboard JSON first, then FCM_SERVICE_ACCOUNT_JSON in .env."""
    raw = ""
    if db is not None:
        raw = get_secret(db, FCM_SERVICE_ACCOUNT_KEY)
    if not raw:
        from app.config import settings
        raw = (getattr(settings, "FCM_SERVICE_ACCOUNT_JSON", "") or "").strip()
    return parse_service_account(raw)


def clamp_int(raw: str | int | None, default: int, lo: int, hi: int) -> int:
    try:
        n = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


def recaptcha_site_key(db: Session) -> str:
    from app.config import settings
    return get_plain(db, RECAPTCHA_SITE_KEY_KEY) or (settings.RECAPTCHA_SITE_KEY or "").strip()


def recaptcha_secret(db: Session) -> str:
    from app.config import settings
    return get_secret(db, RECAPTCHA_SECRET_KEY) or (settings.RECAPTCHA_SECRET or "").strip()


def recaptcha_wanted(db: Session) -> bool:
    """Whether Super Admin asked for the widget. Default: on when both keys exist."""
    flag = get_plain(db, RECAPTCHA_ENABLED_KEY)
    if flag == "0":
        return False
    if flag == "1":
        return True
    return bool(recaptcha_site_key(db) and recaptcha_secret(db))


def recaptcha_ready(db: Session) -> bool:
    return recaptcha_wanted(db) and bool(recaptcha_site_key(db) and recaptcha_secret(db))


def login_max_attempts(db: Session) -> int:
    from app.config import settings
    default = max(LOGIN_ATTEMPTS_MIN, int(settings.LOGIN_MAX_ATTEMPTS or 5))
    raw = get_plain(db, LOGIN_MAX_ATTEMPTS_KEY)
    if not raw:
        return default
    return clamp_int(raw, default, LOGIN_ATTEMPTS_MIN, LOGIN_ATTEMPTS_MAX)


def login_lockout_minutes(db: Session) -> int:
    from app.config import settings
    default = max(LOGIN_LOCKOUT_MIN, int(settings.LOGIN_LOCKOUT_MINUTES or 15))
    raw = get_plain(db, LOGIN_LOCKOUT_MINUTES_KEY)
    if not raw:
        return default
    return clamp_int(raw, default, LOGIN_LOCKOUT_MIN, LOGIN_LOCKOUT_MAX)


def rate_limit_enabled(db: Session) -> bool:
    return get_plain(db, LOGIN_RATE_LIMIT_ENABLED_KEY) != "0"
