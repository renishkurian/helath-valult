"""Digital Diary — dated notes with categories, tags, and encrypted photos."""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app import models, schemas, crypto
from app.deps import get_current_user, require_owner, vault_id, require_enabled_module
from app.extract import enhance_scan, file_sha256

router = APIRouter(
    prefix="/diary",
    tags=["diary"],
    dependencies=[Depends(require_enabled_module("diary"))],
)

DEFAULT_CATEGORIES = [
    ("Personal", "#FB7185", 10),
    ("Work", "#5B8CFF", 20),
    ("Travel", "#22D3EE", 30),
    ("Health", "#4ADE9B", 40),
    ("Family", "#F0C36A", 50),
    ("Ideas", "#C0A8FF", 60),
    ("Other", "#8B95A8", 70),
]
CAT_COLORS = ["#5B8CFF", "#3DDC97", "#A89BFF", "#F5B942", "#FB7185", "#22D3EE", "#F97316", "#8B95A8"]


def ensure_defaults(db: Session, user: models.User) -> None:
    uid = vault_id(user)
    existing = db.query(models.DiaryCategory).filter(models.DiaryCategory.user_id == uid).count()
    if existing == 0:
        for name, color, order in DEFAULT_CATEGORIES:
            db.add(models.DiaryCategory(
                user_id=uid, name=name, color=color, sort_order=order, is_default=True,
            ))
        db.commit()


def _norm_color(color: Optional[str], fallback: str) -> str:
    raw = (color or "").strip()
    if re.fullmatch(r"#?[0-9A-Fa-f]{3,8}", raw or ""):
        return raw if raw.startswith("#") else f"#{raw}"
    return fallback


def _owned_entry(entry_id: str, db: Session, user: models.User) -> models.DiaryEntry:
    entry = (
        db.query(models.DiaryEntry)
        .filter(models.DiaryEntry.id == entry_id, models.DiaryEntry.user_id == vault_id(user))
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return entry


def _owned_category(category_id: str, db: Session, user: models.User) -> models.DiaryCategory:
    row = (
        db.query(models.DiaryCategory)
        .filter(models.DiaryCategory.id == category_id, models.DiaryCategory.user_id == vault_id(user))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Category not found")
    return row


def _image_out(img: models.DiaryImage) -> schemas.DiaryImageOut:
    return schemas.DiaryImageOut(
        id=img.id, entry_id=img.entry_id, original_filename=img.original_filename,
        file_type=img.file_type, file_size=img.file_size, created_at=img.created_at,
    )


def _cat_out(
    cat: models.DiaryCategory,
    count: int = 0,
    child_count: int = 0,
    depth: int = 0,
    path_label: str | None = None,
) -> schemas.DiaryCategoryOut:
    return schemas.DiaryCategoryOut(
        id=cat.id, name=cat.name, color=cat.color,
        sort_order=cat.sort_order or 0, is_default=bool(cat.is_default), count=count,
        parent_id=cat.parent_id, child_count=child_count, depth=depth,
        path_label=path_label or cat.name,
        created_at=cat.created_at,
    )


def _to_out(entry: models.DiaryEntry, include_images: bool = False) -> schemas.DiaryEntryOut:
    cat = entry.category
    images = list(entry.images or [])
    return schemas.DiaryEntryOut(
        id=entry.id,
        title=entry.title,
        body=crypto.decrypt_text(entry.body_enc),
        entry_date=entry.entry_date,
        category_id=entry.category_id,
        category_name=cat.name if cat else None,
        category_color=cat.color if cat else None,
        tags=entry.tags,
        mood=entry.mood,
        pinned=bool(entry.pinned),
        image_count=len(images),
        images=[_image_out(i) for i in images] if include_images else [],
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


def _category_rows(db: Session, user: models.User) -> list[models.DiaryCategory]:
    return (
        db.query(models.DiaryCategory)
        .filter(models.DiaryCategory.user_id == vault_id(user))
        .order_by(models.DiaryCategory.sort_order, models.DiaryCategory.name)
        .all()
    )


def _entry_counts(db: Session, user: models.User) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in (
        db.query(models.DiaryEntry.category_id)
        .filter(
            models.DiaryEntry.user_id == vault_id(user),
            models.DiaryEntry.category_id.isnot(None),
        )
        .all()
    ):
        counts[row[0]] = counts.get(row[0], 0) + 1
    return counts


def _folder_outs(db: Session, user: models.User) -> list[schemas.DiaryCategoryOut]:
    rows = _category_rows(db, user)
    counts = _entry_counts(db, user)
    by_id = {c.id: c for c in rows}
    child_counts: dict[str, int] = {}
    for c in rows:
        if c.parent_id:
            child_counts[c.parent_id] = child_counts.get(c.parent_id, 0) + 1

    def path_for(cat: models.DiaryCategory) -> str:
        parts: list[str] = []
        cur: models.DiaryCategory | None = cat
        seen: set[str] = set()
        while cur and cur.id not in seen:
            seen.add(cur.id)
            parts.append(cur.name)
            cur = by_id.get(cur.parent_id) if cur.parent_id else None
        parts.reverse()
        return " / ".join(parts)

    return [
        _cat_out(
            c,
            count=counts.get(c.id, 0),
            child_count=child_counts.get(c.id, 0),
            path_label=path_for(c),
        )
        for c in rows
    ]


def folder_tree(db: Session, user: models.User) -> list[schemas.DiaryCategoryOut]:
    """Depth-first flat tree for the Diary Explorer sidebar."""
    folders = _folder_outs(db, user)
    by_parent: dict[str | None, list[schemas.DiaryCategoryOut]] = {}
    for f in folders:
        by_parent.setdefault(f.parent_id, []).append(f)
    for kids in by_parent.values():
        kids.sort(key=lambda x: ((x.sort_order or 0), (x.name or "").lower()))
    out: list[schemas.DiaryCategoryOut] = []

    def walk(parent_id: str | None, depth: int) -> None:
        for f in by_parent.get(parent_id, []):
            out.append(schemas.DiaryCategoryOut(
                id=f.id, name=f.name, color=f.color, sort_order=f.sort_order,
                is_default=f.is_default, count=f.count, parent_id=f.parent_id,
                child_count=f.child_count, depth=depth, path_label=f.path_label,
                created_at=f.created_at,
            ))
            walk(f.id, depth + 1)

    walk(None, 0)
    return out


def folder_crumbs(db: Session, user: models.User, folder_id: str) -> list[schemas.DiaryCategoryOut]:
    by_id = {c.id: c for c in _folder_outs(db, user)}
    crumbs: list[schemas.DiaryCategoryOut] = []
    cur = by_id.get(folder_id)
    seen: set[str] = set()
    while cur and cur.id not in seen:
        seen.add(cur.id)
        crumbs.append(cur)
        cur = by_id.get(cur.parent_id) if cur.parent_id else None
    crumbs.reverse()
    return crumbs


def child_folders(db: Session, user: models.User, parent_id: str | None) -> list[schemas.DiaryCategoryOut]:
    return [f for f in _folder_outs(db, user) if (f.parent_id or None) == (parent_id or None)]


def _resolve_parent(
    parent_id: Optional[str], db: Session, user: models.User, *, self_id: str | None = None,
) -> Optional[str]:
    if not parent_id:
        return None
    parent = _owned_category(parent_id, db, user)
    if self_id and parent.id == self_id:
        raise HTTPException(400, "A folder cannot be inside itself")
    by_id = {c.id: c for c in _category_rows(db, user)}
    if self_id:
        cur = parent
        seen = {self_id}
        while cur:
            if cur.id in seen:
                raise HTTPException(400, "That would create a folder loop")
            seen.add(cur.id)
            cur = by_id.get(cur.parent_id) if cur.parent_id else None
    depth = 0
    cur = parent
    while cur and depth < 8:
        depth += 1
        cur = by_id.get(cur.parent_id) if cur.parent_id else None
    if depth >= 6:
        raise HTTPException(400, "Folders can only nest 6 levels deep")
    return parent.id


def _resolve_category(category_id: Optional[str], db: Session, user: models.User) -> Optional[str]:
    if not category_id:
        return None
    return _owned_category(category_id, db, user).id


async def _save_images(
    entry: models.DiaryEntry,
    files: List[UploadFile],
    current_user: models.User,
    db: Session,
):
    from app import quota

    dest = settings.STORAGE_DIR / vault_id(current_user) / "diary"
    dest.mkdir(parents=True, exist_ok=True)
    existing = len(entry.images or [])
    payloads: list[tuple[bytes, UploadFile, int]] = []
    for idx, upload in enumerate(files):
        if not upload.filename and not (upload.content_type or "").startswith("image/"):
            continue
        raw = await upload.read()
        if not raw:
            continue
        if (upload.content_type or "").startswith("image/"):
            raw = enhance_scan(raw, upload.content_type)
        if len(raw) / (1024 * 1024) > settings.MAX_UPLOAD_MB:
            db.rollback()
            raise HTTPException(
                status_code=413,
                detail=f"File '{upload.filename}' exceeds {settings.MAX_UPLOAD_MB} MB limit",
            )
        payloads.append((raw, upload, existing + idx))
    quota.assert_can_store(db, current_user, sum(len(r) for r, _, _ in payloads))
    for raw, upload, n in payloads:
        enc_path = dest / f"{entry.id}_{n}.enc"
        enc_path.write_bytes(crypto.encrypt_bytes(raw))
        db.add(models.DiaryImage(
            entry_id=entry.id,
            original_filename=upload.filename or f"photo_{n}.jpg",
            file_path=str(enc_path.relative_to(settings.STORAGE_DIR)),
            file_type=upload.content_type,
            file_size=len(raw),
            content_hash=file_sha256(raw),
        ))


# ---------- categories / summary ----------
@router.get("/summary", response_model=schemas.DiarySummaryOut)
def diary_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ensure_defaults(db, current_user)
    uid = vault_id(current_user)
    entries = db.query(models.DiaryEntry).filter(models.DiaryEntry.user_id == uid).all()
    cats = folder_tree(db, current_user)
    return schemas.DiarySummaryOut(
        total=len(entries),
        pinned=sum(1 for e in entries if e.pinned),
        categories=cats,
    )


@router.get("/categories", response_model=list[schemas.DiaryCategoryOut])
def list_categories(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ensure_defaults(db, current_user)
    return folder_tree(db, current_user)


@router.post("/categories", response_model=schemas.DiaryCategoryOut, status_code=201)
def create_category(
    body: schemas.DiaryCategoryIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    ensure_defaults(db, current_user)
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Folder name is required")
    uid = vault_id(current_user)
    parent_id = _resolve_parent(body.parent_id, db, current_user)
    q = db.query(models.DiaryCategory).filter(
        models.DiaryCategory.user_id == uid,
        models.DiaryCategory.name.ilike(name),
    )
    if parent_id:
        q = q.filter(models.DiaryCategory.parent_id == parent_id)
    else:
        q = q.filter(models.DiaryCategory.parent_id.is_(None))
    existing = q.first()
    if existing:
        raise HTTPException(400, f"Folder “{existing.name}” already exists here")
    color = _norm_color(body.color, CAT_COLORS[0])
    if parent_id and not body.color:
        parent = _owned_category(parent_id, db, current_user)
        color = _norm_color(parent.color, color)
    row = models.DiaryCategory(
        user_id=uid,
        name=name,
        color=color,
        parent_id=parent_id,
        sort_order=body.sort_order if body.sort_order is not None else 100,
        is_default=False,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _cat_out(row, path_label=row.name)


@router.patch("/categories/{category_id}", response_model=schemas.DiaryCategoryOut)
def update_category(
    category_id: str,
    body: schemas.DiaryCategoryIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = _owned_category(category_id, db, current_user)
    row.name = body.name.strip()
    if body.color is not None:
        row.color = _norm_color(body.color, row.color or CAT_COLORS[0])
    if body.sort_order is not None:
        row.sort_order = body.sort_order
    data = body.model_dump(exclude_unset=True)
    if "parent_id" in data:
        row.parent_id = _resolve_parent(data.get("parent_id"), db, current_user, self_id=row.id)
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
    # Reparent child folders (Document Vault behavior).
    db.query(models.DiaryCategory).filter(
        models.DiaryCategory.parent_id == row.id,
        models.DiaryCategory.user_id == vault_id(current_user),
    ).update({models.DiaryCategory.parent_id: row.parent_id}, synchronize_session=False)
    db.query(models.DiaryEntry).filter(
        models.DiaryEntry.category_id == row.id,
        models.DiaryEntry.user_id == vault_id(current_user),
    ).update({models.DiaryEntry.category_id: None})
    db.delete(row)
    db.commit()


# ---------- entries ----------
@router.get("", response_model=list[schemas.DiaryEntryOut])
def list_entries(
    category_id: Optional[str] = None,
    q: Optional[str] = None,
    pinned: bool = False,
    unfiled: bool = False,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ensure_defaults(db, current_user)
    query = db.query(models.DiaryEntry).filter(models.DiaryEntry.user_id == vault_id(current_user))
    if unfiled:
        query = query.filter(models.DiaryEntry.category_id.is_(None))
    elif category_id:
        query = query.filter(models.DiaryEntry.category_id == category_id)
    if pinned:
        query = query.filter(models.DiaryEntry.pinned.is_(True))
    if from_date:
        query = query.filter(models.DiaryEntry.entry_date >= from_date)
    if to_date:
        query = query.filter(models.DiaryEntry.entry_date <= to_date)
    rows = query.order_by(
        models.DiaryEntry.pinned.desc(),
        models.DiaryEntry.entry_date.desc(),
        models.DiaryEntry.created_at.desc(),
    ).all()
    needle = (q or "").strip().casefold()
    if needle:
        matched = []
        for e in rows:
            cat = e.category.name if e.category else ""
            body = crypto.decrypt_text(e.body_enc) or ""
            hay = " ".join([
                e.title or "",
                e.tags or "",
                e.mood or "",
                cat,
                body,
            ]).casefold()
            if needle in hay:
                matched.append(e)
        rows = matched
    return [_to_out(e) for e in rows]


@router.post("", response_model=schemas.DiaryEntryOut, status_code=201)
async def create_entry(
    title: str = Form(...),
    body: Optional[str] = Form(None),
    entry_date: Optional[str] = Form(None),
    category_id: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    mood: Optional[str] = Form(None),
    pinned: bool = Form(False),
    images: List[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    ensure_defaults(db, current_user)
    date = (entry_date or "").strip() or datetime.utcnow().strftime("%Y-%m-%d")
    entry = models.DiaryEntry(
        user_id=vault_id(current_user),
        title=title.strip(),
        body_enc=crypto.encrypt_text(body),
        entry_date=date,
        category_id=_resolve_category(category_id, db, current_user),
        tags=(tags or "").strip() or None,
        mood=(mood or "").strip() or None,
        pinned=bool(pinned),
    )
    db.add(entry)
    db.flush()
    file_list = [f for f in (images or []) if f and (f.filename or f.content_type)]
    if file_list:
        await _save_images(entry, file_list, current_user, db)
    db.commit()
    db.refresh(entry)
    return _to_out(entry, include_images=True)


@router.get("/{entry_id}", response_model=schemas.DiaryEntryOut)
def get_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _to_out(_owned_entry(entry_id, db, current_user), include_images=True)


@router.patch("/{entry_id}", response_model=schemas.DiaryEntryOut)
def update_entry(
    entry_id: str,
    body: schemas.DiaryEntryUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    entry = _owned_entry(entry_id, db, current_user)
    data = body.model_dump(exclude_unset=True)
    if "body" in data:
        entry.body_enc = crypto.encrypt_text(data.pop("body"))
    if "category_id" in data:
        entry.category_id = _resolve_category(data.pop("category_id"), db, current_user)
    for key, val in data.items():
        if key == "title" and val is not None:
            setattr(entry, key, str(val).strip())
        elif key in ("tags", "mood", "entry_date"):
            setattr(entry, key, (val or "").strip() or None if isinstance(val, str) else val)
        else:
            setattr(entry, key, val)
    entry.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(entry)
    return _to_out(entry, include_images=True)


@router.delete("/{entry_id}", status_code=204)
def delete_entry(
    entry_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    entry = _owned_entry(entry_id, db, current_user)
    for img in list(entry.images or []):
        path = settings.STORAGE_DIR / img.file_path
        if path.exists():
            path.unlink()
    db.delete(entry)
    db.commit()


@router.post("/{entry_id}/images", response_model=schemas.DiaryEntryOut)
async def add_images(
    entry_id: str,
    images: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    entry = _owned_entry(entry_id, db, current_user)
    if not images:
        raise HTTPException(status_code=422, detail="At least one image is required")
    await _save_images(entry, images, current_user, db)
    entry.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(entry)
    return _to_out(entry, include_images=True)


@router.get("/{entry_id}/images/{image_id}/download")
def download_image(
    entry_id: str,
    image_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    entry = _owned_entry(entry_id, db, current_user)
    img = next((i for i in entry.images if i.id == image_id), None)
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    enc_path = settings.STORAGE_DIR / img.file_path
    if not enc_path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    plain = crypto.decrypt_bytes(enc_path.read_bytes())
    fname = img.original_filename.replace('"', "")
    return Response(
        content=plain,
        media_type=img.file_type or "application/octet-stream",
        headers={"Content-Disposition": f'inline; filename="{fname}"'},
    )


@router.delete("/{entry_id}/images/{image_id}", status_code=204)
def delete_image(
    entry_id: str,
    image_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    entry = _owned_entry(entry_id, db, current_user)
    img = next((i for i in entry.images if i.id == image_id), None)
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    path = settings.STORAGE_DIR / img.file_path
    if path.exists():
        path.unlink()
    db.delete(img)
    entry.updated_at = datetime.utcnow()
    db.commit()
