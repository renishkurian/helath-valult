from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, crypto
from app.config import settings
from app.deps import get_current_user, require_owner, vault_id
from app.extract import enhance_scan
from app.routers.documents import _get_owned_document

router = APIRouter(prefix="/storage", tags=["storage"])


@router.get("/stats", response_model=schemas.StorageStats)
def storage_stats(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app import quota as q

    snap = q.quota_snapshot(db, current_user)
    return schemas.StorageStats(
        bytes_used=snap["bytes_used"],
        file_count=snap["file_count"],
        quota_bytes=snap["quota_bytes"],
        remaining_bytes=snap["remaining_bytes"],
        backup_dir=str(settings.BACKUP_DIR) if settings.BACKUP_DIR else None,
    )


@router.post("/documents/{document_id}/compress", response_model=schemas.DocumentOut)
def compress_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Re-encode image scans to smaller JPEGs. PDFs are left alone."""
    from app.routers.documents import _to_out
    require_owner(current_user)
    doc = _get_owned_document(document_id, db, current_user)
    for f in doc.files:
        mime = (f.file_type or "").lower()
        if not mime.startswith("image/"):
            continue
        path = settings.STORAGE_DIR / f.file_path
        if not path.exists():
            continue
        raw = crypto.decrypt_bytes(path.read_bytes())
        smaller = enhance_scan(raw, mime)
        if len(smaller) < len(raw):
            path.write_bytes(crypto.encrypt_bytes(smaller))
            f.file_size = len(smaller)
            f.file_type = "image/jpeg"
    db.commit()
    db.refresh(doc)
    return _to_out(doc)
