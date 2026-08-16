from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, crypto, security
from app.config import settings
from app.deps import get_current_user, require_owner, vault_id
from app.extract import watermark_bytes
from app.routers.documents import _get_owned_document, _to_out as doc_to_out
from app.templating import setup_templates

router = APIRouter(prefix="/share", tags=["share"])
templates = setup_templates()


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client:
        return (request.client.host or "")[:64]
    return None


def _record_access(db: Session, link: models.ShareLink, action: str, request: Request):
    ua = (request.headers.get("user-agent") or "")[:400]
    db.add(models.ShareAccess(
        share_link_id=link.id,
        action=action,
        ip=_client_ip(request),
        user_agent=ua or None,
    ))
    link.view_count = (link.view_count or 0) + 1
    db.add(models.AuditLog(
        user_id=None,
        document_id=link.document_id,
        action=models.AuditAction.share_view,
        detail=f"{action} ip={_client_ip(request) or '?'} ua={(ua or '')[:80]}",
    ))


def _link_out(link: models.ShareLink) -> schemas.ShareLinkOut:
    accesses = list(link.accesses or [])
    downloads = sum(1 for a in accesses if a.action == "download")
    last = max((a.created_at for a in accesses), default=None)
    title = link.document.title if link.document else None
    return schemas.ShareLinkOut(
        id=link.id,
        token=link.token,
        document_id=link.document_id,
        document_title=title,
        expires_at=link.expires_at,
        max_views=link.max_views,
        view_count=link.view_count,
        download_count=downloads,
        last_access_at=last,
        revoked=link.revoked,
        created_at=link.created_at,
    )


@router.post("", response_model=schemas.ShareLinkOut, status_code=201)
def create_share_link(
    body: schemas.ShareLinkCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Create a read-only, expiring link for a single document — e.g. to show a
    hospital insurance card at a front desk without handing over your account."""
    require_owner(current_user)
    doc = _get_owned_document(body.document_id, db, current_user)

    link = models.ShareLink(
        token=secrets.token_urlsafe(24),
        document_id=doc.id,
        created_by=current_user.id,
        expires_at=datetime.utcnow() + timedelta(hours=body.expires_in_hours),
        max_views=body.max_views,
        pin_hash=security.hash_password(body.pin) if body.pin else None,
        idle_days=body.idle_days or settings.SHARE_IDLE_DAYS,
    )
    db.add(link)
    db.add(models.AuditLog(user_id=current_user.id, document_id=doc.id, action=models.AuditAction.share_create))
    db.commit()
    db.refresh(link)
    link.document = doc
    return _link_out(link)


@router.get("/mine", response_model=list[schemas.ShareLinkOut])
def list_my_share_links(
    document_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    q = (
        db.query(models.ShareLink)
        .join(models.Document)
        .join(models.Person)
        .filter(models.Person.user_id == vault_id(current_user))
    )
    if document_id:
        q = q.filter(models.ShareLink.document_id == document_id)
    links = q.order_by(models.ShareLink.created_at.desc()).all()
    return [_link_out(link) for link in links]


def _pack_out(pack: models.SharePack) -> schemas.SharePackOut:
    return schemas.SharePackOut(
        id=pack.id, token=pack.token, title=pack.title,
        document_ids=[i.document_id for i in pack.items],
        expires_at=pack.expires_at, max_views=pack.max_views,
        view_count=pack.view_count, revoked=pack.revoked,
        has_pin=bool(pack.pin_hash), created_at=pack.created_at,
    )


@router.post("/packs", response_model=schemas.SharePackOut, status_code=201)
def create_share_pack(
    body: schemas.SharePackCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    if not body.document_ids:
        raise HTTPException(status_code=422, detail="Pick at least one document")
    pack = models.SharePack(
        token=secrets.token_urlsafe(24),
        created_by=current_user.id,
        title=body.title,
        pin_hash=security.hash_password(body.pin) if body.pin else None,
        expires_at=datetime.utcnow() + timedelta(hours=body.expires_in_hours),
        max_views=body.max_views,
        idle_days=settings.SHARE_IDLE_DAYS,
    )
    db.add(pack)
    db.flush()
    for doc_id in body.document_ids:
        _get_owned_document(doc_id, db, current_user)
        db.add(models.SharePackItem(pack_id=pack.id, document_id=doc_id))
    db.commit()
    db.refresh(pack)
    return _pack_out(pack)


@router.get("/packs", response_model=list[schemas.SharePackOut])
def list_share_packs(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    packs = (
        db.query(models.SharePack)
        .filter(models.SharePack.created_by == current_user.id)
        .order_by(models.SharePack.created_at.desc())
        .all()
    )
    return [_pack_out(p) for p in packs]


@router.delete("/packs/{pack_id}", status_code=204)
def revoke_share_pack(pack_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    pack = db.query(models.SharePack).filter(models.SharePack.id == pack_id, models.SharePack.created_by == current_user.id).first()
    if not pack:
        raise HTTPException(status_code=404, detail="Pack not found")
    pack.revoked = True
    db.commit()


@router.get("/{link_id}", response_model=schemas.ShareLinkDetailOut)
def get_share_link(
    link_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    link = (
        db.query(models.ShareLink)
        .join(models.Document)
        .join(models.Person)
        .filter(
            models.ShareLink.id == link_id,
            models.Person.user_id == vault_id(current_user),
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=404, detail="Share link not found")
    base = _link_out(link)
    accesses = sorted(link.accesses, key=lambda a: a.created_at or datetime.min, reverse=True)
    return schemas.ShareLinkDetailOut(
        **base.model_dump(),
        accesses=[
            schemas.ShareAccessOut(
                id=a.id, action=a.action, ip=a.ip,
                user_agent=a.user_agent, created_at=a.created_at,
            )
            for a in accesses
        ],
    )


@router.delete("/{link_id}", status_code=204)
def revoke_share_link(
    link_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    link = (
        db.query(models.ShareLink)
        .join(models.Document)
        .join(models.Person)
        .filter(
            models.ShareLink.id == link_id,
            models.Person.user_id == vault_id(current_user),
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=404, detail="Share link not found")
    link.revoked = True
    db.commit()


def _maybe_idle_revoke(link: models.ShareLink, db: Session):
    idle = link.idle_days or settings.SHARE_IDLE_DAYS
    if link.view_count == 0 and link.created_at and idle:
        if link.created_at + timedelta(days=idle) < datetime.utcnow():
            link.revoked = True
            db.commit()
            raise HTTPException(status_code=404, detail="Link not found or revoked")


def _require_pin(pin_hash: str | None, pin: str | None):
    if not pin_hash:
        return
    if not pin or not security.verify_password(pin, pin_hash):
        raise HTTPException(status_code=401, detail="PIN required")


def _load_valid_link(token: str, db: Session, pin: str | None = None) -> models.ShareLink:
    link = db.query(models.ShareLink).filter(models.ShareLink.token == token).first()
    if not link or link.revoked:
        raise HTTPException(status_code=404, detail="Link not found or revoked")
    _maybe_idle_revoke(link, db)
    if link.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="Link has expired")
    if link.max_views is not None and link.view_count >= link.max_views:
        raise HTTPException(status_code=410, detail="Link has reached its view limit")
    _require_pin(link.pin_hash, pin)
    return link


# ---------- Public, unauthenticated endpoints (the whole point of a share link) ----------
@router.get("/public/{token}", response_model=schemas.DocumentOut)
def public_view_document(token: str, request: Request, pin: str | None = None, db: Session = Depends(get_db)):
    link = _load_valid_link(token, db, pin)
    doc = db.query(models.Document).filter(models.Document.id == link.document_id).first()
    if not doc or doc.deleted_at:
        raise HTTPException(status_code=404, detail="Document no longer exists")
    _record_access(db, link, "view", request)
    db.commit()
    return doc_to_out(doc)


@router.get("/public/{token}/page", response_class=HTMLResponse)
def public_view_page(token: str, request: Request, pin: str | None = None, db: Session = Depends(get_db)):
    """Browser page for a hospital front desk — no login."""
    link = db.query(models.ShareLink).filter(models.ShareLink.token == token).first()
    if not link or link.revoked:
        raise HTTPException(status_code=404, detail="Link not found or revoked")
    if link.pin_hash and not pin:
        return templates.TemplateResponse(request, "share_pin.html", {"token": token, "kind": "doc", "error": None})
    link = _load_valid_link(token, db, pin)
    doc = db.query(models.Document).filter(models.Document.id == link.document_id).first()
    if not doc or doc.deleted_at:
        raise HTTPException(status_code=404, detail="Document no longer exists")
    _record_access(db, link, "view", request)
    db.commit()
    return templates.TemplateResponse(request, "share_public.html", {
        "doc": doc_to_out(doc),
        "token": token,
        "expires_at": link.expires_at,
    })


@router.get("/public/{token}/download")
def public_download_document(token: str, request: Request, pin: str | None = None, db: Session = Depends(get_db)):
    link = _load_valid_link(token, db, pin)
    doc = db.query(models.Document).filter(models.Document.id == link.document_id).first()
    if not doc or doc.deleted_at or not doc.files:
        raise HTTPException(status_code=404, detail="No file available")

    first = doc.files[0]
    enc_path = settings.STORAGE_DIR / first.file_path
    if not enc_path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")

    plain = watermark_bytes(crypto.decrypt_bytes(enc_path.read_bytes()), first.file_type)
    _record_access(db, link, "download", request)
    db.commit()
    return Response(
        content=plain,
        media_type=first.file_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{first.original_filename}"'},
    )


def _load_valid_pack(token: str, db: Session, pin: str | None = None) -> models.SharePack:
    pack = db.query(models.SharePack).filter(models.SharePack.token == token).first()
    if not pack or pack.revoked:
        raise HTTPException(status_code=404, detail="Pack not found or revoked")
    idle = pack.idle_days or settings.SHARE_IDLE_DAYS
    if pack.view_count == 0 and pack.created_at and idle:
        if pack.created_at + timedelta(days=idle) < datetime.utcnow():
            pack.revoked = True
            db.commit()
            raise HTTPException(status_code=404, detail="Pack not found or revoked")
    if pack.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="Pack has expired")
    if pack.max_views is not None and pack.view_count >= pack.max_views:
        raise HTTPException(status_code=410, detail="Pack has reached its view limit")
    _require_pin(pack.pin_hash, pin)
    return pack


@router.get("/public/pack/{token}/page", response_class=HTMLResponse)
def public_pack_page(token: str, request: Request, pin: str | None = None, db: Session = Depends(get_db)):
    pack = db.query(models.SharePack).filter(models.SharePack.token == token).first()
    if not pack or pack.revoked:
        raise HTTPException(status_code=404, detail="Pack not found or revoked")
    if pack.pin_hash and not pin:
        return templates.TemplateResponse(request, "share_pin.html", {"token": token, "kind": "pack", "error": None})
    pack = _load_valid_pack(token, db, pin)
    docs = []
    for item in pack.items:
        doc = db.query(models.Document).filter(models.Document.id == item.document_id).first()
        if doc and not doc.deleted_at:
            docs.append(doc_to_out(doc))
    pack.view_count = (pack.view_count or 0) + 1
    db.add(models.SharePackAccess(pack_id=pack.id, action="view", ip=_client_ip(request), user_agent=(request.headers.get("user-agent") or "")[:400]))
    db.commit()
    return templates.TemplateResponse(request, "share_pack.html", {
        "pack": pack, "docs": docs, "token": token, "pin": pin or "",
    })


@router.get("/public/pack/{token}/download/{document_id}")
def public_pack_download(token: str, document_id: str, request: Request, pin: str | None = None, db: Session = Depends(get_db)):
    pack = _load_valid_pack(token, db, pin)
    if document_id not in {i.document_id for i in pack.items}:
        raise HTTPException(status_code=404, detail="Not in this pack")
    doc = db.query(models.Document).filter(models.Document.id == document_id).first()
    if not doc or doc.deleted_at or not doc.files:
        raise HTTPException(status_code=404, detail="No file available")
    first = doc.files[0]
    enc_path = settings.STORAGE_DIR / first.file_path
    if not enc_path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    plain = watermark_bytes(crypto.decrypt_bytes(enc_path.read_bytes()), first.file_type)
    db.add(models.SharePackAccess(pack_id=pack.id, action="download", ip=_client_ip(request), user_agent=(request.headers.get("user-agent") or "")[:400]))
    db.commit()
    return Response(
        content=plain,
        media_type=first.file_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{first.original_filename}"'},
    )
