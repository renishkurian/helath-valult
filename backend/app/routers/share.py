import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, crypto
from app.config import settings
from app.deps import get_current_user
from app.routers.documents import _get_owned_document, _to_out as doc_to_out

router = APIRouter(prefix="/share", tags=["share"])


@router.post("", response_model=schemas.ShareLinkOut, status_code=201)
def create_share_link(
    body: schemas.ShareLinkCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Create a read-only, expiring link for a single document — e.g. to show a
    hospital insurance card at a front desk without handing over your account."""
    doc = _get_owned_document(body.document_id, db, current_user)

    link = models.ShareLink(
        token=secrets.token_urlsafe(24),
        document_id=doc.id,
        created_by=current_user.id,
        expires_at=datetime.utcnow() + timedelta(hours=body.expires_in_hours),
        max_views=body.max_views,
    )
    db.add(link)
    db.add(models.AuditLog(user_id=current_user.id, document_id=doc.id, action=models.AuditAction.share_create))
    db.commit()
    db.refresh(link)
    return link


@router.get("/mine", response_model=list[schemas.ShareLinkOut])
def list_my_share_links(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return (
        db.query(models.ShareLink)
        .filter(models.ShareLink.created_by == current_user.id)
        .order_by(models.ShareLink.created_at.desc())
        .all()
    )


@router.delete("/{link_id}", status_code=204)
def revoke_share_link(
    link_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    link = db.query(models.ShareLink).filter(
        models.ShareLink.id == link_id, models.ShareLink.created_by == current_user.id
    ).first()
    if not link:
        raise HTTPException(status_code=404, detail="Share link not found")
    link.revoked = True
    db.commit()


def _load_valid_link(token: str, db: Session) -> models.ShareLink:
    link = db.query(models.ShareLink).filter(models.ShareLink.token == token).first()
    if not link or link.revoked:
        raise HTTPException(status_code=404, detail="Link not found or revoked")
    if link.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="Link has expired")
    if link.max_views is not None and link.view_count >= link.max_views:
        raise HTTPException(status_code=410, detail="Link has reached its view limit")
    return link


# ---------- Public, unauthenticated endpoints (the whole point of a share link) ----------
@router.get("/public/{token}", response_model=schemas.DocumentOut)
def public_view_document(token: str, db: Session = Depends(get_db)):
    link = _load_valid_link(token, db)
    doc = db.query(models.Document).filter(models.Document.id == link.document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document no longer exists")

    link.view_count += 1
    db.add(models.AuditLog(user_id=None, document_id=doc.id, action=models.AuditAction.share_view, detail=f"token:{token[:8]}..."))
    db.commit()
    return doc_to_out(doc)


@router.get("/public/{token}/download")
def public_download_document(token: str, db: Session = Depends(get_db)):
    link = _load_valid_link(token, db)
    doc = db.query(models.Document).filter(models.Document.id == link.document_id).first()
    if not doc or not doc.files:
        raise HTTPException(status_code=404, detail="No file available")

    first = doc.files[0]
    enc_path = settings.STORAGE_DIR / first.file_path
    if not enc_path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")

    plain = crypto.decrypt_bytes(enc_path.read_bytes())
    link.view_count += 1
    db.add(models.AuditLog(user_id=None, document_id=doc.id, action=models.AuditAction.share_view, detail=f"token:{token[:8]}...:download"))
    db.commit()
    return Response(
        content=plain,
        media_type=first.file_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{first.original_filename}"'},
    )
