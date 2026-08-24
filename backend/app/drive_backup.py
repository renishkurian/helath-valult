"""Run encrypted vault snapshots to Google Drive and prune old copies."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import crypto, gdrive, models
from app.config import settings, utc_naive_to_vault, vault_now
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
        "last_ok": None if row.last_ok is None else bool(row.last_ok),
        "last_error": row.last_error,
        "last_file_name": row.last_file_name,
    }


def should_run_now(row: models.GoogleDriveBackup, now: datetime | None = None) -> bool:
    if not row.enabled or not row.refresh_token_enc or not row.password_enc:
        return False
    now = now or vault_now()
    if now.hour < int(row.hour or 3):
        return False
    if row.last_run_at and row.last_ok:
        last_local = utc_naive_to_vault(row.last_run_at)
        if last_local.date() == now.date():
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
    from app.routers.backup import build_vault_backup
    blob = crypto.encrypt_backup(build_vault_backup(db, user), password)
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


def _access_token(db: Session, user: models.User) -> tuple[models.GoogleDriveBackup, str, str]:
    """Return (row, access_token, folder_id). Raises RuntimeError if not connected."""
    row = get_or_create(db, user)
    if not row.refresh_token_enc:
        raise RuntimeError("Google Drive is not connected")
    client_id, client_secret = oauth_creds(db, row)
    if not client_id or not client_secret:
        raise RuntimeError("Google Drive is not configured on this server")
    refresh = crypto.decrypt_text(row.refresh_token_enc) or ""
    token = gdrive.refresh_access_token(client_id, client_secret, refresh)
    folder_id = gdrive.ensure_folder(token, row.folder_id)
    if folder_id != row.folder_id:
        row.folder_id = folder_id
        db.commit()
    return row, token, folder_id


def list_remote_backups(db: Session, user: models.User) -> list[dict]:
    """List .hvbak (and other) files in this vault's Drive backup folder."""
    _row, token, folder_id = _access_token(db, user)
    out = []
    for item in gdrive.list_backups(token, folder_id):
        name = item.get("name") or ""
        try:
            size = int(item.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        out.append({
            "id": item.get("id") or "",
            "name": name,
            "created_time": item.get("createdTime") or "",
            "size": size,
        })
    return [f for f in out if f["id"]]


def restore_from_drive(db: Session, user: models.User, file_id: str, password: str) -> dict:
    """Download a Drive backup by id and merge-restore into this vault."""
    import io
    import json
    import zipfile

    from app.routers.backup import _restore_modules

    fid = (file_id or "").strip()
    if not fid:
        raise RuntimeError("No backup file selected")
    pwd = (password or "").strip()
    if not pwd:
        raise RuntimeError("Backup password is required to restore")

    _row, token, folder_id = _access_token(db, user)
    listing = gdrive.list_backups(token, folder_id)
    allowed = {f.get("id"): f for f in listing if f.get("id")}
    meta = allowed.get(fid)
    if not meta:
        try:
            info = gdrive.get_file(token, fid)
        except Exception as exc:
            raise RuntimeError("Backup file not found on Drive") from exc
        parents = info.get("parents") or []
        if folder_id not in parents or info.get("trashed"):
            raise RuntimeError("That file is not in your Health Vault Backups folder")
        name = info.get("name") or fid
    else:
        name = meta.get("name") or fid

    blob = gdrive.download_bytes(token, fid)
    try:
        if blob.startswith(b"HV1\0"):
            zip_bytes = crypto.decrypt_backup(blob, pwd)
        else:
            zip_bytes = blob
    except Exception as exc:
        raise RuntimeError("Could not decrypt backup — check the password") from exc

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        raise RuntimeError("Not a valid backup archive") from exc

    try:
        manifest = json.loads(zf.read("manifest.json"))
    except KeyError as exc:
        raise RuntimeError("Backup is missing manifest.json") from exc
    except Exception as exc:
        raise RuntimeError("Could not read backup manifest") from exc

    restored = _restore_modules(db, vault_id(user), zf, manifest)
    log.info("Drive restore ok for %s from %s", getattr(user, "email", "?"), name)
    return {"ok": True, "file": name, "modules": manifest.get("modules") or [], **restored}
