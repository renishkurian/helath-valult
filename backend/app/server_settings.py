"""Encrypted server-wide settings, edited in Super Admin."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app import crypto, models

GOOGLE_CLIENT_ID_KEY = "google_client_id"
GOOGLE_CLIENT_SECRET_KEY = "google_client_secret"
FCM_SERVER_KEY = "fcm_server_key"


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


def fcm_server_key(db: Session | None = None) -> str:
    """Dashboard secret first, then FCM_SERVER_KEY in .env."""
    if db is not None:
        saved = get_secret(db, FCM_SERVER_KEY)
        if saved:
            return saved
    from app.config import settings
    return (getattr(settings, "FCM_SERVER_KEY", "") or "").strip()
