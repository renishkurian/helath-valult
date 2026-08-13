"""Run encrypted vault snapshots to Google Drive and prune old copies."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import crypto, gdrive, models
from app.config import settings
from app.deps import vault_id

log = logging.getLogger("vault.gdrive")


def _row(db: Session, user: models.User) -> models.GoogleDriveBackup | None:
    return (
        db.query(models.GoogleDriveBackup)
        .filter(models.GoogleDriveBackup.user_id == vault_id(user))
        .first()
    )


def get_or_create(db: Session, user: models.User) -> models.GoogleDriveBackup:
    row = _row(db, user)
    if row:
        return row
    row = models.GoogleDriveBackup(user_id=vault_id(user), hour=3, keep_days=14, enabled=False)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def oauth_creds(
    db: Session | None = None,
    row: models.GoogleDriveBackup | None = None,
) -> tuple[str, str]:
    """Super Admin DB first, then .env, then a legacy per-vault client."""
    if db is not None:
        from app.server_settings import google_app
        cid, secret = google_app(db)
        if cid and secret:
            return cid, secret
    cid = (settings.GOOGLE_CLIENT_ID or "").strip()
    secret = (settings.GOOGLE_CLIENT_SECRET or "").strip()
    if cid and secret:
        return cid, secret
    if row:
        return (row.client_id or "").strip(), crypto.decrypt_text(row.client_secret_enc) or ""
    return "", ""


def oauth_ready(
    db: Session | None = None,
    row: models.GoogleDriveBackup | None = None,
) -> bool:
    cid, secret = oauth_creds(db, row)
    return bool(cid and secret)


def status_dict(row: models.GoogleDriveBackup | None, db: Session | None = None) -> dict:
    server = oauth_ready(db)
    if not row:
        return {
            "connected": False, "email": None, "enabled": False, "hour": 3, "keep_days": 14,
            "has_password": False, "has_client": False, "server_oauth": server,
            "last_run_at": None, "last_ok": None, "last_error": None, "last_file_name": None,
        }
    return {
        "connected": bool(row.refresh_token_enc),
        "email": row.connected_email,
        "enabled": bool(row.enabled),
        "hour": int(row.hour or 3),
        "keep_days": int(row.keep_days or 14),
        "has_password": bool(row.password_enc),
        "has_client": oauth_ready(db, row),
        "server_oauth": server,
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
        "last_ok": row.last_ok,
        "last_error": row.last_error,
        "last_file_name": row.last_file_name,
    }


def should_run_now(row: models.GoogleDriveBackup, now: datetime | None = None) -> bool:
    if not row.enabled or not row.refresh_token_enc or not row.password_enc:
        return False
    now = now or datetime.now()
    if now.hour < int(row.hour or 3):
        return False
    if row.last_run_at and row.last_ok and row.last_run_at.date() == now.date():
        return False
    return True


def run_backup(db: Session, user: models.User) -> dict:
    row = get_or_create(db, user)
    if not row.refresh_token_enc:
        raise RuntimeError("Google Drive is not connected")
    password = crypto.decrypt_text(row.password_enc)
    if not password:
        raise RuntimeError("Set a backup password before uploading to Drive")
    client_id, client_secret = oauth_creds(db, row)
    if not client_id or not client_secret:
        raise RuntimeError("Google Drive is not configured on this server")
    refresh = crypto.decrypt_text(row.refresh_token_enc) or ""
    from app.routers.backup import _build_zip
    people = db.query(models.Person).filter(models.Person.user_id == vault_id(user)).all()
    locker_items = db.query(models.LockerItem).filter(models.LockerItem.user_id == vault_id(user)).all()
    blob = crypto.encrypt_backup(_build_zip(people, locker_items), password)
    name = f"healthvault-{datetime.now().strftime('%Y%m%d-%H%M')}.hvbak"
    try:
        token = gdrive.refresh_access_token(client_id, client_secret, refresh)
        folder_id = gdrive.ensure_folder(token, row.folder_id)
        gdrive.upload_bytes(token, folder_id, name, blob)
        keep = max(3, int(row.keep_days or 14))
        cutoff = datetime.utcnow() - timedelta(days=keep)
        for item in gdrive.list_backups(token, folder_id):
            created = item.get("createdTime") or ""
            try:
                when = datetime.fromisoformat(created.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                continue
            if when < cutoff and item.get("id"):
                try:
                    gdrive.delete_file(token, item["id"])
                except Exception:
                    log.warning("could not prune Drive file %s", item.get("name"))
        row.folder_id = folder_id
        row.last_run_at = datetime.utcnow()
        row.last_ok = True
        row.last_error = None
        row.last_file_name = name
        db.commit()
        return {"ok": True, "file": name, "bytes": len(blob)}
    except Exception as exc:
        row.last_run_at = datetime.utcnow()
        row.last_ok = False
        row.last_error = str(exc)[:500]
        db.commit()
        raise


def run_due_backups() -> None:
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        rows = db.query(models.GoogleDriveBackup).filter(
            models.GoogleDriveBackup.enabled.is_(True),
            models.GoogleDriveBackup.refresh_token_enc.isnot(None),
        ).all()
        now = datetime.now()
        for row in rows:
            if not should_run_now(row, now):
                continue
            user = db.query(models.User).filter(models.User.id == row.user_id).first()
            if not user:
                continue
            try:
                run_backup(db, user)
                log.info("Drive backup ok for %s → %s", user.email, row.last_file_name)
            except Exception:
                log.exception("Drive backup failed for %s", user.email)
    finally:
        db.close()
