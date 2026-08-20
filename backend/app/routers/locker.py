"""Document Vault — encrypted IDs, certificates, RC, insurance, warranties."""
from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app import models, schemas, crypto
from app.deps import require_enabled_module, get_current_user, require_owner, vault_id
from app.extract import enhance_scan, file_sha256

router = APIRouter(prefix="/locker", tags=["locker"], dependencies=[Depends(require_enabled_module("locker"))])

LOCKER_TYPES = [
    ("aadhaar", "Aadhaar"),
    ("pan", "PAN"),
    ("passport", "Passport"),
    ("driving_license", "Driving licence"),
    ("voter_id", "Voter ID"),
    ("certificate", "Certificate"),
    ("rc", "Vehicle RC"),
    ("insurance", "Insurance"),
    ("warranty", "Warranty"),
    ("property", "Property"),
    ("other", "Other"),
]
TYPE_LABELS = {k: v for k, v in LOCKER_TYPES}
TYPE_IDS = {k for k, _ in LOCKER_TYPES}
_RELATION_ORDER = ("self", "spouse", "child", "parent", "other")


def type_label(doc_type: str, custom_type: Optional[str] = None, folder_name: Optional[str] = None) -> str:
    if doc_type == "other" and custom_type:
        return custom_type
    if doc_type == "other" and folder_name:
        return folder_name
    return TYPE_LABELS.get(doc_type, custom_type or doc_type.replace("_", " ").title())


def title_name(value: Optional[str]) -> str:
    """Title-case a folder / person display name (bank → Bank)."""
    text = (value or "").strip()
    if not text:
        return ""
    return " ".join(part[:1].upper() + part[1:] if part else part for part in text.split())


def _people_for(db: Session, user: models.User) -> list[models.Person]:
    rows = (
        db.query(models.Person)
        .filter(models.Person.user_id == vault_id(user))
        .all()
    )
    return sorted(
        rows,
        key=lambda p: (
            _RELATION_ORDER.index(p.relation.value) if p.relation and p.relation.value in _RELATION_ORDER else 99,
            (p.name or "").lower(),
        ),
    )


def _folders_for(db: Session, user: models.User) -> list[models.LockerFolder]:
    rows = (
        db.query(models.LockerFolder)
        .filter(models.LockerFolder.user_id == vault_id(user))
        .order_by(models.LockerFolder.name)
        .all()
    )
    return rows


def _resolve_person(
    db: Session, user: models.User, person_id: Optional[str],
) -> Optional[models.Person]:
    pid = (person_id or "").strip()
    if not pid:
        return None
    return (
        db.query(models.Person)
        .filter(models.Person.id == pid, models.Person.user_id == vault_id(user))
        .first()
    )


def _resolve_folder(
    db: Session, user: models.User, folder_id: Optional[str],
) -> Optional[models.LockerFolder]:
    fid = (folder_id or "").strip()
    if not fid:
        return None
    return (
        db.query(models.LockerFolder)
        .filter(models.LockerFolder.id == fid, models.LockerFolder.user_id == vault_id(user))
        .first()
    )


def _to_file_out(f: models.LockerFile) -> schemas.LockerFileOut:
    return schemas.LockerFileOut(
        id=f.id, item_id=f.item_id, original_filename=f.original_filename,
        file_type=f.file_type, file_size=f.file_size, created_at=f.created_at,
    )


def _to_out(
    item: models.LockerItem,
    person_name: Optional[str] = None,
    folder_name: Optional[str] = None,
) -> schemas.LockerItemOut:
    first = item.files[0] if item.files else None
    pname = person_name
    if pname is None and getattr(item, "person", None) is not None:
        pname = item.person.name
    fname = folder_name
    if fname is None and getattr(item, "folder", None) is not None:
        fname = item.folder.name
    return schemas.LockerItemOut(
        id=item.id,
        doc_type=item.doc_type,
        type_label=type_label(item.doc_type, item.custom_type, fname),
        custom_type=item.custom_type,
        folder_id=item.folder_id,
        folder_name=fname,
        person_id=item.person_id,
        person_name=pname,
        title=item.title,
        holder_name=item.holder_name,
        issuer=item.issuer,
        id_number=crypto.decrypt_text(item.id_number_enc),
        issued_on=item.issued_on,
        expiry_date=item.expiry_date,
        tags=item.tags,
        notes=crypto.decrypt_text(item.notes_enc),
        pinned=bool(item.pinned),
        file_type=first.file_type if first else None,
        file_size=first.file_size if first else None,
        file_count=len(item.files) if item.files else 0,
        created_at=item.created_at,
    )


def _owned(item_id: str, db: Session, user: models.User) -> models.LockerItem:
    item = (
        db.query(models.LockerItem)
        .filter(models.LockerItem.id == item_id, models.LockerItem.user_id == vault_id(user))
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Document not found")
    return item


def _norm_type(doc_type: Optional[str], custom_type: Optional[str]) -> tuple[str, Optional[str]]:
    raw = (doc_type or "other").strip().lower().replace(" ", "_")
    custom = (custom_type or "").strip() or None
    if custom:
        return "other", custom
    if raw not in TYPE_IDS:
        return "other", custom
    return raw, None


def _folder_outs(db: Session, user: models.User, items: list[models.LockerItem] | None = None) -> list[schemas.LockerFolderOut]:
    if items is None:
        items = db.query(models.LockerItem).filter(models.LockerItem.user_id == vault_id(user)).all()
    counts: dict[str, int] = {}
    for item in items:
        if item.folder_id:
            counts[item.folder_id] = counts.get(item.folder_id, 0) + 1
    out: list[schemas.LockerFolderOut] = []
    dirty = False
    for f in _folders_for(db, user):
        titled = title_name(f.name)
        if titled and f.name != titled:
            f.name = titled
            dirty = True
        out.append(schemas.LockerFolderOut(
            id=f.id, name=f.name, count=counts.get(f.id, 0), created_at=f.created_at,
        ))
    if dirty:
        db.commit()
    return out


@router.get("/types", response_model=list[schemas.LockerTypeOut])
def list_types(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    items = db.query(models.LockerItem).filter(models.LockerItem.user_id == vault_id(current_user)).all()
    counts: dict[str, int] = {k: 0 for k, _ in LOCKER_TYPES}
    for item in items:
        counts[item.doc_type] = counts.get(item.doc_type, 0) + 1
    out = [schemas.LockerTypeOut(id=k, label=v, count=counts.get(k, 0)) for k, v in LOCKER_TYPES]
    for folder in _folder_outs(db, current_user, items):
        out.append(schemas.LockerTypeOut(
            id=f"folder:{folder.id}", label=folder.name, count=folder.count, custom=True,
        ))
    return out


@router.get("/folders", response_model=list[schemas.LockerFolderOut])
def list_folders(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _folder_outs(db, current_user)


@router.post("/folders", response_model=schemas.LockerFolderOut, status_code=201)
def create_folder(
    body: schemas.LockerFolderIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    name = title_name(body.name)
    if not name:
        raise HTTPException(status_code=422, detail="Folder name is required")
    existing = (
        db.query(models.LockerFolder)
        .filter(
            models.LockerFolder.user_id == vault_id(current_user),
            models.LockerFolder.name.ilike(name),
        )
        .first()
    )
    if existing:
        if existing.name != name:
            existing.name = name
            db.commit()
            db.refresh(existing)
        return schemas.LockerFolderOut(
            id=existing.id, name=existing.name, count=0, created_at=existing.created_at,
        )
    row = models.LockerFolder(user_id=vault_id(current_user), name=name)
    db.add(row)
    db.commit()
    db.refresh(row)
    return schemas.LockerFolderOut(id=row.id, name=row.name, count=0, created_at=row.created_at)


@router.delete("/folders/{folder_id}", status_code=204)
def delete_folder(
    folder_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    folder = _resolve_folder(db, current_user, folder_id)
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    db.query(models.LockerItem).filter(
        models.LockerItem.folder_id == folder.id,
        models.LockerItem.user_id == vault_id(current_user),
    ).update({models.LockerItem.folder_id: None}, synchronize_session=False)
    db.delete(folder)
    db.commit()


@router.get("/summary", response_model=schemas.LockerSummaryOut)
def locker_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    items = db.query(models.LockerItem).filter(models.LockerItem.user_id == vault_id(current_user)).all()
    today = datetime.utcnow().strftime("%Y-%m-%d")
    soon = (datetime.utcnow() + timedelta(days=60)).strftime("%Y-%m-%d")
    expiring = sum(
        1 for i in items
        if i.expiry_date and today <= i.expiry_date <= soon
    )
    counts: dict[str, int] = {k: 0 for k, _ in LOCKER_TYPES}
    person_counts: dict[str, int] = {}
    unassigned = 0
    for item in items:
        counts[item.doc_type] = counts.get(item.doc_type, 0) + 1
        if item.person_id:
            person_counts[item.person_id] = person_counts.get(item.person_id, 0) + 1
        else:
            unassigned += 1
    people = [
        schemas.LockerPersonOut(
            id=p.id,
            name=p.name,
            relation=p.relation.value if p.relation else "other",
            count=person_counts.get(p.id, 0),
        )
        for p in _people_for(db, current_user)
    ]
    folders = _folder_outs(db, current_user, items)
    types = [schemas.LockerTypeOut(id=k, label=v, count=counts.get(k, 0)) for k, v in LOCKER_TYPES]
    for folder in folders:
        types.append(schemas.LockerTypeOut(
            id=f"folder:{folder.id}", label=folder.name, count=folder.count, custom=True,
        ))
    return schemas.LockerSummaryOut(
        total=len(items),
        expiring=expiring,
        unassigned=unassigned,
        types=types,
        folders=folders,
        people=people,
    )


@router.get("", response_model=list[schemas.LockerItemOut])
def list_items(
    doc_type: Optional[str] = None,
    folder_id: Optional[str] = None,
    q: Optional[str] = None,
    person_id: Optional[str] = None,
    expiring: bool = False,
    pinned: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.LockerItem).filter(models.LockerItem.user_id == vault_id(current_user))
    raw_type = (doc_type or "").strip()
    fid = (folder_id or "").strip()
    if raw_type.startswith("folder:"):
        fid = raw_type.split(":", 1)[1].strip()
        raw_type = ""
    if fid:
        query = query.filter(models.LockerItem.folder_id == fid)
    elif raw_type:
        query = query.filter(models.LockerItem.doc_type == raw_type)
    if pinned:
        query = query.filter(models.LockerItem.pinned.is_(True))
    # Search always spans every family profile; person filter applies only when not searching.
    needle = (q or "").strip()
    if needle:
        like = f"%{needle}%"
        people_ids = [
            row[0] for row in db.query(models.Person.id).filter(
                models.Person.user_id == vault_id(current_user),
                models.Person.name.ilike(like),
            ).all()
        ]
        clauses = [
            models.LockerItem.title.ilike(like),
            models.LockerItem.holder_name.ilike(like),
            models.LockerItem.issuer.ilike(like),
            models.LockerItem.tags.ilike(like),
            models.LockerItem.custom_type.ilike(like),
        ]
        if people_ids:
            clauses.append(models.LockerItem.person_id.in_(people_ids))
        query = query.filter(or_(*clauses))
    else:
        pid = (person_id or "").strip()
        if pid == "none":
            query = query.filter(models.LockerItem.person_id.is_(None))
        elif pid:
            query = query.filter(models.LockerItem.person_id == pid)
    if expiring:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        soon = (datetime.utcnow() + timedelta(days=60)).strftime("%Y-%m-%d")
        query = query.filter(
            models.LockerItem.expiry_date.isnot(None),
            models.LockerItem.expiry_date >= today,
            models.LockerItem.expiry_date <= soon,
        )
    rows = query.order_by(models.LockerItem.created_at.desc()).all()
    names = {p.id: p.name for p in _people_for(db, current_user)}
    folder_names = {f.id: f.name for f in _folders_for(db, current_user)}
    return [_to_out(i, names.get(i.person_id), folder_names.get(i.folder_id)) for i in rows]


@router.post("", response_model=schemas.LockerItemOut, status_code=201)
async def create_item(
    title: str = Form(...),
    doc_type: str = Form("other"),
    custom_type: Optional[str] = Form(None),
    folder_id: Optional[str] = Form(None),
    person_id: Optional[str] = Form(None),
    holder_name: Optional[str] = Form(None),
    issuer: Optional[str] = Form(None),
    id_number: Optional[str] = Form(None),
    issued_on: Optional[str] = Form(None),
    expiry_date: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    if not files:
        raise HTTPException(status_code=422, detail="At least one file is required")
    folder = _resolve_folder(db, current_user, folder_id)
    kind, custom = _norm_type(doc_type, custom_type)
    if folder and kind == "other" and not custom:
        custom = folder.name
    person = _resolve_person(db, current_user, person_id)
    holder = (holder_name or "").strip() or None
    if person and not holder:
        holder = person.name
    item = models.LockerItem(
        user_id=vault_id(current_user),
        person_id=person.id if person else None,
        folder_id=folder.id if folder else None,
        doc_type=kind,
        custom_type=custom,
        title=title.strip(),
        holder_name=holder,
        issuer=(issuer or "").strip() or None,
        id_number_enc=crypto.encrypt_text(id_number),
        issued_on=issued_on or None,
        expiry_date=expiry_date or None,
        tags=(tags or "").strip() or None,
        notes_enc=crypto.encrypt_text(notes),
    )
    db.add(item)
    db.flush()
    await _save_files(item, files, current_user, db)
    db.commit()
    db.refresh(item)
    return _to_out(item, person.name if person else None, folder.name if folder else None)


async def _save_files(
    item: models.LockerItem,
    files: List[UploadFile],
    current_user: models.User,
    db: Session,
):
    from app.models import gen_id
    dest = settings.STORAGE_DIR / vault_id(current_user) / "locker"
    dest.mkdir(parents=True, exist_ok=True)
    for upload in files:
        raw = await upload.read()
        if (upload.content_type or "").startswith("image/"):
            raw = enhance_scan(raw, upload.content_type)
        if len(raw) / (1024 * 1024) > settings.MAX_UPLOAD_MB:
            db.rollback()
            raise HTTPException(
                status_code=413,
                detail=f"File '{upload.filename}' exceeds {settings.MAX_UPLOAD_MB} MB limit",
            )
        token = gen_id()
        enc_path = dest / f"{item.id}_{token}.enc"
        enc_path.write_bytes(crypto.encrypt_bytes(raw))
        db.add(models.LockerFile(
            item_id=item.id,
            original_filename=upload.filename or f"file_{token[:8]}",
            file_path=str(enc_path.relative_to(settings.STORAGE_DIR)),
            file_type=upload.content_type,
            file_size=len(raw),
            content_hash=file_sha256(raw),
        ))


@router.post("/{item_id}/files", response_model=list[schemas.LockerFileOut], status_code=201)
async def add_files(
    item_id: str,
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    item = _owned(item_id, db, current_user)
    uploads = [f for f in (files or []) if f is not None and getattr(f, "filename", None)]
    if not uploads:
        raise HTTPException(status_code=422, detail="At least one file is required")
    await _save_files(item, uploads, current_user, db)
    item.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return [_to_file_out(f) for f in item.files]


@router.delete("/{item_id}/files/{file_id}", status_code=204)
def delete_file(
    item_id: str,
    file_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    item = _owned(item_id, db, current_user)
    doc_file = next((f for f in item.files if f.id == file_id), None)
    if not doc_file:
        raise HTTPException(status_code=404, detail="File not found")
    path = settings.STORAGE_DIR / doc_file.file_path
    if path.exists():
        path.unlink()
    db.delete(doc_file)
    item.updated_at = datetime.utcnow()
    db.commit()


@router.get("/{item_id}", response_model=schemas.LockerItemOut)
def get_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = _owned(item_id, db, current_user)
    pname = None
    if item.person_id:
        person = _resolve_person(db, current_user, item.person_id)
        pname = person.name if person else None
    fname = None
    if item.folder_id:
        folder = _resolve_folder(db, current_user, item.folder_id)
        fname = folder.name if folder else None
    return _to_out(item, pname, fname)


@router.patch("/{item_id}", response_model=schemas.LockerItemOut)
def update_item(
    item_id: str,
    body: schemas.LockerItemUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    item = _owned(item_id, db, current_user)
    data = body.model_dump(exclude_unset=True)
    if "folder_id" in data:
        folder = _resolve_folder(db, current_user, data.pop("folder_id"))
        item.folder_id = folder.id if folder else None
        if folder and "custom_type" not in data and not item.custom_type:
            item.custom_type = folder.name
            if item.doc_type not in TYPE_IDS or item.doc_type == "other":
                item.doc_type = "other"
    if "doc_type" in data or "custom_type" in data:
        kind, custom = _norm_type(
            data.get("doc_type", item.doc_type),
            data.get("custom_type", item.custom_type),
        )
        item.doc_type = kind
        item.custom_type = custom
        data.pop("doc_type", None)
        data.pop("custom_type", None)
    if "person_id" in data:
        person = _resolve_person(db, current_user, data.pop("person_id"))
        item.person_id = person.id if person else None
        if person and not data.get("holder_name") and not item.holder_name:
            item.holder_name = person.name
    if "id_number" in data:
        item.id_number_enc = crypto.encrypt_text(data.pop("id_number"))
    if "notes" in data:
        item.notes_enc = crypto.encrypt_text(data.pop("notes"))
    for key, val in data.items():
        setattr(item, key, val if val != "" else None)
    item.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    pname = None
    if item.person_id:
        person = _resolve_person(db, current_user, item.person_id)
        pname = person.name if person else None
    fname = None
    if item.folder_id:
        folder = _resolve_folder(db, current_user, item.folder_id)
        fname = folder.name if folder else None
    return _to_out(item, pname, fname)


@router.delete("/{item_id}", status_code=204)
def delete_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    item = _owned(item_id, db, current_user)
    for f in list(item.files or []):
        path = settings.STORAGE_DIR / f.file_path
        if path.exists():
            path.unlink()
    db.delete(item)
    db.commit()


@router.get("/{item_id}/files", response_model=list[schemas.LockerFileOut])
def list_files(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = _owned(item_id, db, current_user)
    return [_to_file_out(f) for f in item.files]


@router.get("/{item_id}/download")
def download_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = _owned(item_id, db, current_user)
    if not item.files:
        raise HTTPException(status_code=404, detail="No file attached")
    return _file_response(item.files[0], inline=False)


@router.get("/{item_id}/view")
def view_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Inline preview bytes for the lightbox (images / PDF)."""
    item = _owned(item_id, db, current_user)
    if not item.files:
        raise HTTPException(status_code=404, detail="No file attached")
    return _file_response(item.files[0], inline=True)


@router.get("/{item_id}/files/{file_id}/download")
def download_file(
    item_id: str,
    file_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = _owned(item_id, db, current_user)
    doc_file = next((f for f in item.files if f.id == file_id), None)
    if not doc_file:
        raise HTTPException(status_code=404, detail="File not found")
    return _file_response(doc_file, inline=False)


@router.get("/{item_id}/files/{file_id}/view")
def view_file(
    item_id: str,
    file_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    item = _owned(item_id, db, current_user)
    doc_file = next((f for f in item.files if f.id == file_id), None)
    if not doc_file:
        raise HTTPException(status_code=404, detail="File not found")
    return _file_response(doc_file, inline=True)


def _file_response(doc_file: models.LockerFile, *, inline: bool = False) -> Response:
    enc_path = settings.STORAGE_DIR / doc_file.file_path
    if not enc_path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    plain = crypto.decrypt_bytes(enc_path.read_bytes())
    fname = doc_file.original_filename.replace('"', "")
    disposition = "inline" if inline else "attachment"
    headers = {
        "Content-Disposition": f'{disposition}; filename="{fname}"',
    }
    if inline:
        headers["Cache-Control"] = "private, no-store"
    return Response(
        content=plain,
        media_type=doc_file.file_type or "application/octet-stream",
        headers=headers,
    )


# ---------- Document share (Password Vault Send stack) ----------

@router.post("/{item_id}/sends", response_model=schemas.VaultSendOut, status_code=201)
def create_locker_send(
    item_id: str,
    body: schemas.VaultSendCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Create a share link for a Document Vault item (PIN, grant, email OTP, one-time)."""
    from app.routers import vault as vv
    require_owner(current_user)
    _owned(item_id, db, current_user)
    return vv.create_send(
        schemas.VaultSendCreate(
            name=(body.name or "").strip() or "Document",
            send_type="locker",
            item_id=item_id,
            notes=body.notes,
            pin=body.pin,
            expires_in_hours=body.expires_in_hours,
            max_views=body.max_views,
            require_grant=body.require_grant,
            require_email_otp=body.require_email_otp,
            allowed_emails=body.allowed_emails or [],
        ),
        db=db,
        current_user=current_user,
    )


@router.get("/{item_id}/sends", response_model=list[schemas.VaultSendOut])
def list_locker_item_sends(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app.routers import vault as vv
    require_owner(current_user)
    _owned(item_id, db, current_user)
    return vv.list_item_sends(item_id, db=db, current_user=current_user)


@router.delete("/sends/{send_id}", status_code=204)
def revoke_locker_send(
    send_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app.routers import vault as vv
    require_owner(current_user)
    row = (
        db.query(models.VaultSend)
        .filter(models.VaultSend.id == send_id, models.VaultSend.user_id == vault_id(current_user))
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Share not found")
    if row.send_type != "locker":
        raise HTTPException(status_code=400, detail="Not a document share")
    return vv.revoke_send(send_id, db=db, current_user=current_user)


@router.post("/{item_id}/sends/revoke-all", status_code=204)
def revoke_all_locker_item_sends(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app.routers import vault as vv
    require_owner(current_user)
    _owned(item_id, db, current_user)
    rows = (
        db.query(models.VaultSend)
        .filter(models.VaultSend.user_id == vault_id(current_user), models.VaultSend.revoked.is_(False))
        .all()
    )
    for row in rows:
        data = vv._payload(row)
        if data.get("item_id") == item_id or data.get("locker_item_id") == item_id:
            row.revoked = True
    db.commit()
    return Response(status_code=204)
