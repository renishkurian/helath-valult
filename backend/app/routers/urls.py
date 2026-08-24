"""URL Vault — bookmarks with categories, tags, Open Graph preview, and share links."""
from __future__ import annotations

import re
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, crypto
from app.deps import require_enabled_module, get_current_user, require_owner, vault_id
from app.og import fetch_preview, hostname_of, normalize_url
from app.templating import setup_templates

router = APIRouter(prefix="/urls", tags=["urls"], dependencies=[Depends(require_enabled_module("urls"))])
public_router = APIRouter(prefix="/urls", tags=["urls"])
templates = setup_templates()

DEFAULT_CATEGORIES = [
    ("Adult", "#FB7185", 10),
    ("Instagram", "#E1306C", 20),
    ("News", "#5B8CFF", 30),
    ("Songs", "#A89BFF", 40),
    ("Work", "#F5B942", 50),
    ("Personal", "#3DDC97", 60),
    ("Other", "#8B95A8", 70),
]
DEFAULT_TAGS = [
    ("video", "#FB7185"),
    ("article", "#5B8CFF"),
    ("music", "#A89BFF"),
    ("social", "#E1306C"),
    ("shopping", "#F5B942"),
]
CAT_COLORS = ["#5B8CFF", "#3DDC97", "#A89BFF", "#F5B942", "#FB7185", "#22D3EE", "#F97316", "#8B95A8"]


def ensure_defaults(db: Session, user: models.User) -> None:
    uid = vault_id(user)
    existing = db.query(models.UrlCategory).filter(models.UrlCategory.user_id == uid).count()
    if existing == 0:
        for name, color, order in DEFAULT_CATEGORIES:
            db.add(models.UrlCategory(
                user_id=uid, name=name, color=color, sort_order=order, is_default=True,
            ))
    tag_count = db.query(models.UrlTag).filter(models.UrlTag.user_id == uid).count()
    if tag_count == 0:
        for name, color in DEFAULT_TAGS:
            db.add(models.UrlTag(user_id=uid, name=name, color=color))
    if existing == 0 or tag_count == 0:
        db.commit()


def _owned_item(
    item_id: str,
    db: Session,
    user: models.User,
    *,
    include_deleted: bool = False,
) -> models.UrlItem:
    q = db.query(models.UrlItem).filter(
        models.UrlItem.id == item_id,
        models.UrlItem.user_id == vault_id(user),
    )
    if not include_deleted:
        q = q.filter(models.UrlItem.deleted_at.is_(None))
    item = q.first()
    if not item:
        raise HTTPException(status_code=404, detail="Link not found")
    return item


def _active_item_query(db: Session, user: models.User):
    return db.query(models.UrlItem).filter(
        models.UrlItem.user_id == vault_id(user),
        models.UrlItem.deleted_at.is_(None),
    )


def _purge_item(db: Session, item: models.UrlItem) -> None:
    db.delete(item)


def _owned_category(category_id: str, db: Session, user: models.User) -> models.UrlCategory:
    row = (
        db.query(models.UrlCategory)
        .filter(models.UrlCategory.id == category_id, models.UrlCategory.user_id == vault_id(user))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Category not found")
    return row


def _owned_tag(tag_id: str, db: Session, user: models.User) -> models.UrlTag:
    row = (
        db.query(models.UrlTag)
        .filter(models.UrlTag.id == tag_id, models.UrlTag.user_id == vault_id(user))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Tag not found")
    return row


def _norm_color(color: Optional[str], fallback: str) -> str:
    raw = (color or "").strip()
    if re.fullmatch(r"#?[0-9A-Fa-f]{3,8}", raw or ""):
        return raw if raw.startswith("#") else f"#{raw}"
    return fallback


def _tag_out(tag: models.UrlTag, count: int = 0) -> schemas.UrlTagOut:
    return schemas.UrlTagOut(id=tag.id, name=tag.name, color=tag.color, count=count)


def _cat_out(cat: models.UrlCategory, count: int = 0) -> schemas.UrlCategoryOut:
    return schemas.UrlCategoryOut(
        id=cat.id, name=cat.name, color=cat.color,
        sort_order=cat.sort_order or 0, is_default=bool(cat.is_default), count=count,
    )


def _to_out(item: models.UrlItem) -> schemas.UrlItemOut:
    cat = item.category
    return schemas.UrlItemOut(
        id=item.id,
        title=item.title,
        url=item.url,
        category_id=item.category_id,
        category_name=cat.name if cat else None,
        category_color=cat.color if cat else None,
        tags=[_tag_out(t) for t in (item.tags or [])],
        notes=crypto.decrypt_text(item.notes_enc),
        favorite=bool(item.favorite),
        og_title=item.og_title,
        og_description=item.og_description,
        og_image=item.og_image,
        og_site_name=item.og_site_name,
        favicon_url=item.favicon_url,
        created_at=item.created_at,
        updated_at=item.updated_at,
        deleted_at=item.deleted_at,
    )


def _share_out(share: models.UrlShare) -> schemas.UrlShareOut:
    item = share.item
    return schemas.UrlShareOut(
        id=share.id,
        token=share.token,
        item_id=share.item_id,
        item_title=item.title if item else None,
        item_url=item.url if item else None,
        expires_at=share.expires_at,
        max_views=share.max_views,
        view_count=share.view_count or 0,
        revoked=bool(share.revoked),
        created_at=share.created_at,
    )


def _apply_preview(item: models.UrlItem, preview: dict) -> None:
    if not preview:
        return
    item.og_title = preview.get("title")
    item.og_description = preview.get("description")
    item.og_image = preview.get("image")
    item.og_site_name = preview.get("site_name")
    item.favicon_url = preview.get("favicon_url")


def _set_tags(item: models.UrlItem, tag_ids: list[str], db: Session, user: models.User) -> None:
    uid = vault_id(user)
    ids = [t for t in dict.fromkeys(tag_ids) if t]
    if not ids:
        item.tags = []
        return
    rows = (
        db.query(models.UrlTag)
        .filter(models.UrlTag.user_id == uid, models.UrlTag.id.in_(ids))
        .all()
    )
    item.tags = rows


def _resolve_category(category_id: Optional[str], db: Session, user: models.User) -> Optional[str]:
    if not category_id:
        return None
    return _owned_category(category_id, db, user).id


# ---------- categories / tags / summary (static paths first) ----------
@router.get("/summary", response_model=schemas.UrlSummaryOut)
def urls_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ensure_defaults(db, current_user)
    uid = vault_id(current_user)
    items = (
        db.query(models.UrlItem)
        .filter(
            models.UrlItem.user_id == uid,
            models.UrlItem.deleted_at.is_(None),
        )
        .all()
    )
    trash = (
        db.query(models.UrlItem)
        .filter(
            models.UrlItem.user_id == uid,
            models.UrlItem.deleted_at.isnot(None),
        )
        .count()
    )
    cats = (
        db.query(models.UrlCategory)
        .filter(models.UrlCategory.user_id == uid)
        .order_by(models.UrlCategory.sort_order, models.UrlCategory.name)
        .all()
    )
    tags = (
        db.query(models.UrlTag)
        .filter(models.UrlTag.user_id == uid)
        .order_by(models.UrlTag.name)
        .all()
    )
    cat_counts: dict[str, int] = {}
    for item in items:
        if item.category_id:
            cat_counts[item.category_id] = cat_counts.get(item.category_id, 0) + 1
    tag_counts: dict[str, int] = {}
    for item in items:
        for t in item.tags or []:
            tag_counts[t.id] = tag_counts.get(t.id, 0) + 1
    unfiled = sum(1 for i in items if not i.category_id)
    return schemas.UrlSummaryOut(
        total=len(items),
        favorites=sum(1 for i in items if i.favorite),
        trash=trash,
        unfiled=unfiled,
        categories=[_cat_out(c, cat_counts.get(c.id, 0)) for c in cats],
        tags=[_tag_out(t, tag_counts.get(t.id, 0)) for t in tags],
    )


@router.get("/categories", response_model=list[schemas.UrlCategoryOut])
def list_categories(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return urls_summary(db=db, current_user=current_user).categories


@router.post("/categories", response_model=schemas.UrlCategoryOut, status_code=201)
def create_category(
    body: schemas.UrlCategoryIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    ensure_defaults(db, current_user)
    uid = vault_id(current_user)
    name = body.name.strip()
    dup = (
        db.query(models.UrlCategory)
        .filter(models.UrlCategory.user_id == uid, func.lower(models.UrlCategory.name) == name.lower())
        .first()
    )
    if dup:
        raise HTTPException(400, "A category with that name already exists")
    max_order = (
        db.query(func.max(models.UrlCategory.sort_order))
        .filter(models.UrlCategory.user_id == uid)
        .scalar()
    ) or 0
    row = models.UrlCategory(
        user_id=uid,
        name=name,
        color=_norm_color(body.color, CAT_COLORS[max_order % len(CAT_COLORS)]),
        sort_order=body.sort_order if body.sort_order is not None else max_order + 10,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _cat_out(row)


@router.patch("/categories/{category_id}", response_model=schemas.UrlCategoryOut)
def update_category(
    category_id: str,
    body: schemas.UrlCategoryIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = _owned_category(category_id, db, current_user)
    name = body.name.strip()
    dup = (
        db.query(models.UrlCategory)
        .filter(
            models.UrlCategory.user_id == row.user_id,
            func.lower(models.UrlCategory.name) == name.lower(),
            models.UrlCategory.id != row.id,
        )
        .first()
    )
    if dup:
        raise HTTPException(400, "A category with that name already exists")
    row.name = name
    if body.color is not None:
        row.color = _norm_color(body.color, row.color or CAT_COLORS[0])
    if body.sort_order is not None:
        row.sort_order = body.sort_order
    db.commit()
    db.refresh(row)
    return _cat_out(row)


@router.delete("/categories/{category_id}", status_code=204)
def delete_category(
    category_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = _owned_category(category_id, db, current_user)
    db.query(models.UrlItem).filter(models.UrlItem.category_id == row.id).update(
        {models.UrlItem.category_id: None}
    )
    db.delete(row)
    db.commit()


@router.get("/tags", response_model=list[schemas.UrlTagOut])
def list_tags(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return urls_summary(db=db, current_user=current_user).tags


@router.post("/tags", response_model=schemas.UrlTagOut, status_code=201)
def create_tag(
    body: schemas.UrlTagIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    ensure_defaults(db, current_user)
    uid = vault_id(current_user)
    name = body.name.strip()
    dup = (
        db.query(models.UrlTag)
        .filter(models.UrlTag.user_id == uid, func.lower(models.UrlTag.name) == name.lower())
        .first()
    )
    if dup:
        raise HTTPException(400, "A tag with that name already exists")
    n = db.query(models.UrlTag).filter(models.UrlTag.user_id == uid).count()
    row = models.UrlTag(
        user_id=uid, name=name,
        color=_norm_color(body.color, CAT_COLORS[n % len(CAT_COLORS)]),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _tag_out(row)


@router.patch("/tags/{tag_id}", response_model=schemas.UrlTagOut)
def update_tag(
    tag_id: str,
    body: schemas.UrlTagIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = _owned_tag(tag_id, db, current_user)
    name = body.name.strip()
    dup = (
        db.query(models.UrlTag)
        .filter(
            models.UrlTag.user_id == row.user_id,
            func.lower(models.UrlTag.name) == name.lower(),
            models.UrlTag.id != row.id,
        )
        .first()
    )
    if dup:
        raise HTTPException(400, "A tag with that name already exists")
    row.name = name
    if body.color is not None:
        row.color = _norm_color(body.color, row.color or CAT_COLORS[0])
    db.commit()
    db.refresh(row)
    return _tag_out(row)


@router.delete("/tags/{tag_id}", status_code=204)
def delete_tag(
    tag_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = _owned_tag(tag_id, db, current_user)
    row.items = []
    db.delete(row)
    db.commit()


@router.get("/shares", response_model=list[schemas.UrlShareOut])
def list_shares(
    item_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    uid = vault_id(current_user)
    q = (
        db.query(models.UrlShare)
        .join(models.UrlItem)
        .filter(
            models.UrlItem.user_id == uid,
            models.UrlItem.deleted_at.is_(None),
        )
    )
    if item_id:
        q = q.filter(models.UrlShare.item_id == item_id)
    rows = q.order_by(models.UrlShare.created_at.desc()).all()
    return [_share_out(s) for s in rows]


@router.post("/shares/{share_id}/revoke", status_code=204)
def revoke_share(
    share_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    share = (
        db.query(models.UrlShare)
        .join(models.UrlItem)
        .filter(models.UrlShare.id == share_id, models.UrlItem.user_id == vault_id(current_user))
        .first()
    )
    if not share:
        raise HTTPException(404, "Share not found")
    share.revoked = True
    db.commit()


def _public_share(token: str, db: Session) -> models.UrlShare:
    share = db.query(models.UrlShare).filter(models.UrlShare.token == token).first()
    if not share or share.revoked:
        raise HTTPException(404, "Link not found")
    if share.expires_at and share.expires_at < datetime.utcnow():
        raise HTTPException(410, "This link has expired")
    if share.max_views is not None and (share.view_count or 0) >= share.max_views:
        raise HTTPException(410, "This link has reached its view limit")
    if not share.item or share.item.deleted_at is not None:
        raise HTTPException(404, "Link not found")
    return share


@public_router.get("/public/{token}", response_model=schemas.UrlItemOut)
def public_item(token: str, db: Session = Depends(get_db)):
    share = _public_share(token, db)
    share.view_count = (share.view_count or 0) + 1
    db.commit()
    return _to_out(share.item)


@public_router.get("/public/{token}/page", response_class=HTMLResponse)
def public_page(token: str, request: Request, db: Session = Depends(get_db)):
    share = _public_share(token, db)
    share.view_count = (share.view_count or 0) + 1
    db.commit()
    item = _to_out(share.item)
    return templates.TemplateResponse(
        request, "url_share_public.html",
        {"item": item, "share": share, "token": token},
    )


@router.post("/preview", response_model=schemas.UrlPreviewOut)
def preview_url(
    body: schemas.UrlPreviewIn,
    current_user: models.User = Depends(get_current_user),
):
    try:
        url = normalize_url(body.url)
    except ValueError as e:
        raise HTTPException(422, str(e))
    preview = fetch_preview(url)
    return schemas.UrlPreviewOut(
        url=url,
        title=preview.get("title"),
        description=preview.get("description"),
        image=preview.get("image"),
        site_name=preview.get("site_name") or hostname_of(url),
        favicon_url=preview.get("favicon_url"),
    )


# ---------- items ----------
@router.get("", response_model=list[schemas.UrlItemOut])
def list_items(
    q: Optional[str] = None,
    category_id: Optional[str] = None,
    tag_id: Optional[str] = None,
    favorite: bool = False,
    unfiled: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ensure_defaults(db, current_user)
    query = _active_item_query(db, current_user)
    if unfiled:
        query = query.filter(models.UrlItem.category_id.is_(None))
    elif category_id:
        query = query.filter(models.UrlItem.category_id == category_id)
    if favorite:
        query = query.filter(models.UrlItem.favorite.is_(True))
    if tag_id:
        query = query.join(models.UrlItem.tags).filter(models.UrlTag.id == tag_id)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(or_(
            models.UrlItem.title.ilike(like),
            models.UrlItem.url.ilike(like),
            models.UrlItem.og_title.ilike(like),
            models.UrlItem.og_site_name.ilike(like),
            models.UrlItem.og_description.ilike(like),
        ))
    rows = query.order_by(models.UrlItem.favorite.desc(), models.UrlItem.created_at.desc()).all()
    return [_to_out(i) for i in rows]


@router.get("/trash", response_model=list[schemas.UrlItemOut])
def list_trash(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    rows = (
        db.query(models.UrlItem)
        .filter(
            models.UrlItem.user_id == vault_id(current_user),
            models.UrlItem.deleted_at.isnot(None),
        )
        .order_by(models.UrlItem.deleted_at.desc())
        .all()
    )
    return [_to_out(i) for i in rows]


@router.post("/trash/empty")
def empty_trash(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    rows = (
        db.query(models.UrlItem)
        .filter(
            models.UrlItem.user_id == vault_id(current_user),
            models.UrlItem.deleted_at.isnot(None),
        )
        .all()
    )
    n = len(rows)
    for item in rows:
        _purge_item(db, item)
    db.commit()
    return {"ok": True, "deleted": n}


@router.post("", response_model=schemas.UrlItemOut, status_code=201)
def create_item(
    body: schemas.UrlItemIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    ensure_defaults(db, current_user)
    try:
        url = normalize_url(body.url)
    except ValueError as e:
        raise HTTPException(422, str(e))
    preview = fetch_preview(url) if body.fetch_preview else {}
    title = (body.title or "").strip() or (preview.get("title") or "") or hostname_of(url)
    item = models.UrlItem(
        user_id=vault_id(current_user),
        title=title[:255],
        url=url,
        category_id=_resolve_category(body.category_id, db, current_user),
        notes_enc=crypto.encrypt_text(body.notes),
        favorite=bool(body.favorite),
    )
    _apply_preview(item, preview)
    db.add(item)
    db.flush()
    _set_tags(item, body.tag_ids, db, current_user)
    db.commit()
    db.refresh(item)
    return _to_out(item)


@router.get("/{item_id}", response_model=schemas.UrlItemOut)
def get_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _to_out(_owned_item(item_id, db, current_user))


@router.patch("/{item_id}", response_model=schemas.UrlItemOut)
def update_item(
    item_id: str,
    body: schemas.UrlItemUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    item = _owned_item(item_id, db, current_user)
    data = body.model_dump(exclude_unset=True)
    url_changed = False
    if "url" in data and data["url"] is not None:
        try:
            item.url = normalize_url(data.pop("url"))
        except ValueError as e:
            raise HTTPException(422, str(e))
        url_changed = True
    if "title" in data and data["title"] is not None:
        title = data.pop("title").strip()
        if title:
            item.title = title[:255]
    if "category_id" in data:
        item.category_id = _resolve_category(data.pop("category_id"), db, current_user)
    if "notes" in data:
        item.notes_enc = crypto.encrypt_text(data.pop("notes"))
    if "favorite" in data:
        item.favorite = bool(data.pop("favorite"))
    fetch = data.pop("fetch_preview", None)
    if "tag_ids" in data:
        _set_tags(item, data.pop("tag_ids") or [], db, current_user)
    if fetch or (url_changed and fetch is not False):
        _apply_preview(item, fetch_preview(item.url))
        if not (item.title or "").strip():
            item.title = item.og_title or hostname_of(item.url)
    item.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return _to_out(item)


@router.delete("/{item_id}", status_code=204)
def delete_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Soft-delete: move link to trash."""
    require_owner(current_user)
    item = _owned_item(item_id, db, current_user)
    item.deleted_at = datetime.utcnow()
    item.updated_at = datetime.utcnow()
    db.commit()


@router.post("/{item_id}/restore", response_model=schemas.UrlItemOut)
def restore_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    item = _owned_item(item_id, db, current_user, include_deleted=True)
    if item.deleted_at is None:
        raise HTTPException(status_code=400, detail="Link is not in trash")
    item.deleted_at = None
    item.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return _to_out(item)


@router.delete("/{item_id}/permanent", status_code=204)
def permanent_delete_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    item = _owned_item(item_id, db, current_user, include_deleted=True)
    if item.deleted_at is None:
        raise HTTPException(status_code=400, detail="Move to trash before permanent delete")
    _purge_item(db, item)
    db.commit()


@router.post("/{item_id}/preview", response_model=schemas.UrlItemOut)
def refresh_preview(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    item = _owned_item(item_id, db, current_user)
    _apply_preview(item, fetch_preview(item.url))
    item.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return _to_out(item)


@router.post("/{item_id}/favorite", response_model=schemas.UrlItemOut)
def toggle_favorite(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    item = _owned_item(item_id, db, current_user)
    item.favorite = not bool(item.favorite)
    item.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return _to_out(item)


@router.post("/{item_id}/share", response_model=schemas.UrlShareOut, status_code=201)
def create_share(
    item_id: str,
    body: schemas.UrlShareCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    item = _owned_item(item_id, db, current_user)
    share = models.UrlShare(
        token=secrets.token_urlsafe(24),
        item_id=item.id,
        created_by=current_user.id,
        expires_at=datetime.utcnow() + timedelta(hours=body.expires_in_hours),
        max_views=body.max_views,
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    share.item = item
    return _share_out(share)
