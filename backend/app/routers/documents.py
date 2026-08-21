import json
from datetime import datetime, timedelta
from typing import Optional, List
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, crypto
from app.config import settings
from app.deps import get_current_user, get_owned_person, require_owner, vault_id, apply_person_visibility
from app.extract import extract_text, parse_lab_readings, enhance_scan, file_sha256

router = APIRouter(prefix="/documents", tags=["documents"])


def _log(db: Session, current_user: models.User, doc_id: Optional[str], action: models.AuditAction, detail: Optional[str] = None):
    db.add(models.AuditLog(user_id=current_user.id, document_id=doc_id, action=action, detail=detail))


def _expiry_reminder_datetime(expiry_date: str) -> datetime:
    """Reminder fires 7 days before expiry (same time of day, 9am), or immediately
    if the expiry is already within that window / in the past."""
    try:
        expiry = datetime.strptime(expiry_date, "%Y-%m-%d")
    except ValueError:
        return datetime.utcnow() + timedelta(days=1)
    remind = expiry - timedelta(days=7)
    remind = remind.replace(hour=9, minute=0, second=0, microsecond=0)
    now = datetime.utcnow()
    return remind if remind > now else now + timedelta(minutes=5)


def _to_file_out(f: models.DocumentFile) -> schemas.DocumentFileOut:
    return schemas.DocumentFileOut(
        id=f.id,
        document_id=f.document_id,
        original_filename=f.original_filename,
        file_type=f.file_type,
        file_size=f.file_size,
        created_at=f.created_at,
    )


def _to_out(doc: models.Document, include_text: bool = False, favorite: bool = False) -> schemas.DocumentOut:
    # Determine effective file_type / file_size:
    # Prefer the first DocumentFile row; fall back to legacy columns.
    first_file = doc.files[0] if doc.files else None
    return schemas.DocumentOut(
        id=doc.id,
        person_id=doc.person_id,
        category=doc.category,
        custom_category=doc.custom_category,
        title=doc.title,
        hospital_name=doc.hospital_name,
        doc_date=doc.doc_date,
        expiry_date=doc.expiry_date,
        tags=doc.tags,
        version=doc.version,
        file_type=first_file.file_type if first_file else doc.file_type,
        file_size=first_file.file_size if first_file else doc.file_size,
        file_count=len(doc.files) if doc.files else (1 if doc.file_path else 0),
        notes=crypto.decrypt_text(doc.notes_enc),
        extracted_text=doc.extracted_text if include_text else None,
        amount=doc.amount,
        pinned=bool(doc.pinned),
        favorite=favorite,
        deleted_at=doc.deleted_at,
        created_at=doc.created_at,
    )


@router.get("", response_model=list[schemas.DocumentOut])
def list_documents(
    person_id: Optional[str] = None,
    category: Optional[models.DocCategory] = None,
    tag: Optional[str] = None,
    year: Optional[str] = None,
    hospital: Optional[str] = None,
    expiring: bool = False,
    favorite: bool = False,
    pinned: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    q = db.query(models.Document).join(models.Person).filter(models.Person.user_id == vault_id(current_user))
    q = apply_person_visibility(q, db, current_user)
    q = q.filter(models.Document.deleted_at.is_(None))
    if person_id:
        q = q.filter(models.Document.person_id == person_id)
    if category:
        q = q.filter(models.Document.category == category)
    if tag:
        q = q.filter(models.Document.tags.ilike(f"%{tag}%"))
    if year:
        q = q.filter(models.Document.doc_date.ilike(f"{year}%"))
    if hospital:
        q = q.filter(models.Document.hospital_name.ilike(f"%{hospital}%"))
    if pinned:
        q = q.filter(models.Document.pinned.is_(True))
    if expiring:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        soon = (datetime.utcnow() + timedelta(days=30)).strftime("%Y-%m-%d")
        q = q.filter(models.Document.expiry_date.isnot(None), models.Document.expiry_date >= today, models.Document.expiry_date <= soon)
    fav_ids = {
        r.document_id for r in db.query(models.Favorite).filter(models.Favorite.user_id == current_user.id).all()
    }
    if favorite:
        q = q.filter(models.Document.id.in_(fav_ids or ["__none__"]))
    return [_to_out(d, favorite=d.id in fav_ids) for d in q.order_by(models.Document.created_at.desc()).all()]


def attach_document_files(
    db: Session,
    *,
    doc: models.Document,
    file_parts: list[tuple[bytes, str, str | None]],
    person_dir: Path,
    user: models.User | None = None,
) -> tuple[list[str], str | None, int]:
    """Store encrypted DocumentFile rows. ``file_parts`` is (raw, filename, content_type).

    Images are compressed via ``enhance_scan`` (JPEG). Returns (ocr_chunks, first_mime, first_size).
    """
    if not file_parts:
        raise HTTPException(status_code=422, detail="At least one file is required")

    from app import quota

    prepared: list[tuple[bytes, str, str]] = []
    for idx, (raw, filename, content_type) in enumerate(file_parts):
        stored_mime = (content_type or "application/octet-stream").split(";")[0].strip()
        name = filename or f"file_{idx}"
        if stored_mime.startswith("image/") or (
            not stored_mime.startswith("application/") and _looks_like_image(raw)
        ):
            raw = enhance_scan(raw, stored_mime if stored_mime.startswith("image/") else "image/jpeg")
            stored_mime = "image/jpeg"
            if not name.lower().endswith((".jpg", ".jpeg")):
                name = f"{name.rsplit('.', 1)[0]}.jpg"

        size_mb = len(raw) / (1024 * 1024)
        if size_mb > settings.MAX_UPLOAD_MB:
            raise HTTPException(
                status_code=413,
                detail=f"File '{name}' exceeds {settings.MAX_UPLOAD_MB} MB limit",
            )
        if not raw:
            raise HTTPException(400, f"Empty file '{name}'")
        prepared.append((raw, name, stored_mime))

    if user is not None:
        quota.assert_can_store(db, user, sum(len(r) for r, _, _ in prepared))

    ocr_chunks: list[str] = []
    first_mime: str | None = None
    first_size = 0
    for idx, (raw, name, stored_mime) in enumerate(prepared):
        enc_path = person_dir / f"{doc.id}_{idx}.enc"
        enc_path.write_bytes(crypto.encrypt_bytes(raw))
        ocr_chunks.append(extract_text(raw, stored_mime, name))
        db.add(models.DocumentFile(
            document_id=doc.id,
            original_filename=name,
            file_path=str(enc_path.relative_to(settings.STORAGE_DIR)),
            file_type=stored_mime,
            file_size=len(raw),
            content_hash=file_sha256(raw),
        ))
        if idx == 0:
            first_mime = stored_mime
            first_size = len(raw)

    return ocr_chunks, first_mime, first_size


def _looks_like_image(raw: bytes) -> bool:
    if len(raw) < 8:
        return False
    return raw[:3] == b"\xff\xd8\xff" or raw[:8] == b"\x89PNG\r\n\x1a\n" or raw[:4] == b"RIFF"


@router.post("", response_model=schemas.DocumentOut, status_code=201)
async def upload_document(
    person_id: str = Form(...),
    category: models.DocCategory = Form(...),
    custom_category: Optional[str] = Form(None),
    title: str = Form(...),
    hospital_name: Optional[str] = Form(None),
    doc_date: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    expiry_date: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    amount: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Upload a document entry with one or more files (pages, scans, PDFs)."""
    require_owner(current_user)
    get_owned_person(person_id, db, current_user)

    if not files:
        raise HTTPException(status_code=422, detail="At least one file is required")

    # If a custom category is provided, force the main category to 'other'
    actual_category = models.DocCategory.other if custom_category else category
    hosp = (hospital_name or "").strip() or None
    if models.category_requires_hospital(actual_category) and not hosp:
        raise HTTPException(
            status_code=422,
            detail="hospital_name is required for this category (only insurance is personal)",
        )
    if actual_category == models.DocCategory.insurance:
        hosp = None

    doc = models.Document(
        person_id=person_id,
        category=actual_category,
        custom_category=custom_category,
        title=title,
        hospital_name=hosp,
        doc_date=doc_date,
        expiry_date=expiry_date,
        tags=tags,
        amount=amount,
        notes_enc=crypto.encrypt_text(notes),
        file_path="",  # legacy — no longer used for new uploads
    )
    db.add(doc)
    db.flush()  # get doc.id without committing

    person_dir: Path = settings.STORAGE_DIR / vault_id(current_user) / person_id
    person_dir.mkdir(parents=True, exist_ok=True)

    parts: list[tuple[bytes, str, str | None]] = []
    for upload in files:
        raw = await upload.read()
        parts.append((raw, upload.filename or "file", upload.content_type))

    try:
        ocr_chunks, first_mime, first_size = attach_document_files(
            db, doc=doc, file_parts=parts, person_dir=person_dir, user=current_user,
        )
    except HTTPException:
        db.rollback()
        raise

    doc.file_type = first_mime
    doc.file_size = first_size

    combined = "\n".join(c for c in ocr_chunks if c).strip() or None
    doc.extracted_text = combined
    if combined:
        for reading in parse_lab_readings(combined):
            db.add(models.LabReading(
                person_id=person_id,
                document_id=doc.id,
                metric=reading["metric"],
                value=reading["value"],
                unit=reading["unit"],
                measured_at=doc_date,
            ))

    if expiry_date:
        db.add(models.Reminder(
            person_id=person_id,
            document_id=doc.id,
            title=f"{title} expires",
            description=f"Renew/replace before {expiry_date}",
            remind_at=_expiry_reminder_datetime(expiry_date),
            repeat_rule=models.RepeatRule.none,
        ))

    db.commit()
    db.refresh(doc)
    return _to_out(doc)


def _get_owned_document(
    document_id: str,
    db: Session,
    current_user: models.User,
    *,
    include_deleted: bool = False,
) -> models.Document:
    doc = (
        db.query(models.Document)
        .join(models.Person)
        .filter(models.Document.id == document_id, models.Person.user_id == vault_id(current_user))
        .first()
    )
    if not doc or (doc.deleted_at and not include_deleted):
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/trash", response_model=list[schemas.DocumentOut])
def list_trash(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    q = (
        db.query(models.Document)
        .join(models.Person)
        .filter(
            models.Person.user_id == vault_id(current_user),
            models.Document.deleted_at.isnot(None),
        )
    )
    q = apply_person_visibility(q, db, current_user)
    return [_to_out(d) for d in q.order_by(models.Document.deleted_at.desc()).all()]


@router.post("/trash/empty", status_code=204)
def empty_trash(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    rows = (
        db.query(models.Document)
        .join(models.Person)
        .filter(
            models.Person.user_id == vault_id(current_user),
            models.Document.deleted_at.isnot(None),
        )
        .all()
    )
    for doc in rows:
        _purge_document(db, current_user, doc)
    db.commit()


@router.get("/duplicates", response_model=list[schemas.DuplicateGroup])
def list_duplicates(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    files = (
        db.query(models.DocumentFile)
        .join(models.Document).join(models.Person)
        .filter(
            models.Person.user_id == vault_id(current_user),
            models.DocumentFile.content_hash.isnot(None),
            models.Document.deleted_at.is_(None),
        )
        .all()
    )
    grouped: dict[str, list[models.DocumentFile]] = {}
    for f in files:
        grouped.setdefault(f.content_hash, []).append(f)
    return [
        schemas.DuplicateGroup(
            content_hash=h,
            document_ids=list({f.document_id for f in rows}),
            filenames=[f.original_filename for f in rows],
        )
        for h, rows in grouped.items() if len(rows) > 1
    ]


@router.get("/recent", response_model=list[schemas.DocumentOut])
def recent_documents(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    rows = (
        db.query(models.RecentOpen)
        .filter(models.RecentOpen.user_id == current_user.id)
        .order_by(models.RecentOpen.opened_at.desc())
        .limit(20)
        .all()
    )
    out = []
    seen = set()
    for r in rows:
        if r.document_id in seen:
            continue
        seen.add(r.document_id)
        try:
            doc = _get_owned_document(r.document_id, db, current_user)
        except HTTPException:
            continue
        out.append(_to_out(doc))
    return out


@router.post("/bulk/delete", status_code=204)
def bulk_delete(body: schemas.BulkIds, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    for doc_id in body.ids:
        try:
            delete_document(doc_id, db, current_user)
        except HTTPException:
            continue


@router.post("/bulk/tag", response_model=list[schemas.DocumentOut])
def bulk_tag(body: schemas.BulkIds, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    tagged = []
    extra = (body.tags or "").strip()
    for doc_id in body.ids:
        try:
            doc = _get_owned_document(doc_id, db, current_user)
        except HTTPException:
            continue
        existing = [t.strip() for t in (doc.tags or "").split(",") if t.strip()]
        for t in extra.split(","):
            t = t.strip()
            if t and t not in existing:
                existing.append(t)
        doc.tags = ", ".join(existing) if existing else None
        tagged.append(doc)
    db.commit()
    return [_to_out(d) for d in tagged]


@router.post("/{document_id}/favorite", status_code=204)
def favorite_document(document_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    _get_owned_document(document_id, db, current_user)
    existing = db.query(models.Favorite).filter(models.Favorite.user_id == current_user.id, models.Favorite.document_id == document_id).first()
    if not existing:
        db.add(models.Favorite(user_id=current_user.id, document_id=document_id))
        db.commit()


@router.delete("/{document_id}/favorite", status_code=204)
def unfavorite_document(document_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    db.query(models.Favorite).filter(models.Favorite.user_id == current_user.id, models.Favorite.document_id == document_id).delete()
    db.commit()


@router.get("/{document_id}", response_model=schemas.DocumentOut)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    doc = _get_owned_document(document_id, db, current_user)
    _log(db, current_user, doc.id, models.AuditAction.view)
    db.add(models.RecentOpen(user_id=current_user.id, document_id=doc.id))
    db.commit()
    fav = db.query(models.Favorite).filter(models.Favorite.user_id == current_user.id, models.Favorite.document_id == doc.id).first()
    return _to_out(doc, include_text=True, favorite=bool(fav))


@router.put("/{document_id}", response_model=schemas.DocumentOut)
def update_document(
    document_id: str,
    update_data: schemas.DocumentUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    doc = _get_owned_document(document_id, db, current_user)

    if update_data.title is not None:
        doc.title = update_data.title
    if update_data.category is not None:
        doc.category = update_data.category
    if update_data.custom_category is not None:
        doc.custom_category = update_data.custom_category if update_data.custom_category != "" else None
    if update_data.hospital_name is not None:
        doc.hospital_name = update_data.hospital_name if update_data.hospital_name != "" else None
    if update_data.doc_date is not None:
        doc.doc_date = update_data.doc_date if update_data.doc_date != "" else None
    if update_data.notes is not None:
        doc.notes_enc = crypto.encrypt_text(update_data.notes if update_data.notes != "" else None)
    if update_data.expiry_date is not None:
        doc.expiry_date = update_data.expiry_date if update_data.expiry_date != "" else None
    if update_data.tags is not None:
        doc.tags = update_data.tags if update_data.tags != "" else None
    if update_data.amount is not None:
        doc.amount = update_data.amount if update_data.amount != "" else None
    if update_data.pinned is not None:
        doc.pinned = update_data.pinned

    if doc.category == models.DocCategory.insurance:
        doc.hospital_name = None
    elif models.category_requires_hospital(doc.category) and not (doc.hospital_name or "").strip():
        raise HTTPException(
            status_code=422,
            detail="hospital_name is required for this category (only insurance is personal)",
        )

    db.commit()
    db.refresh(doc)
    return _to_out(doc)


@router.get("/{document_id}/files", response_model=List[schemas.DocumentFileOut])
def list_document_files(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """List all files (pages) attached to a document."""
    doc = _get_owned_document(document_id, db, current_user)
    return [_to_file_out(f) for f in doc.files]


@router.get("/{document_id}/download")
def download_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Download the first (or only) file. For multi-file documents, use /files/{file_id}/download."""
    doc = _get_owned_document(document_id, db, current_user)

    # Prefer the first DocumentFile entry; fall back to the legacy file_path column.
    if doc.files:
        first = doc.files[0]
        enc_path = settings.STORAGE_DIR / first.file_path
        mime = first.file_type or "application/octet-stream"
        fname = first.original_filename
    elif doc.file_path:
        enc_path = settings.STORAGE_DIR / doc.file_path
        mime = doc.file_type or "application/octet-stream"
        fname = doc.title
    else:
        raise HTTPException(status_code=404, detail="No file attached to this document")

    if not enc_path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")

    plain = crypto.decrypt_bytes(enc_path.read_bytes())
    _log(db, current_user, doc.id, models.AuditAction.download, detail=fname)
    db.commit()
    return Response(
        content=plain,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/{document_id}/files/{file_id}/download")
def download_document_file(
    document_id: str,
    file_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Download a specific file page from a multi-file document."""
    doc = _get_owned_document(document_id, db, current_user)
    doc_file = next((f for f in doc.files if f.id == file_id), None)
    if not doc_file:
        raise HTTPException(status_code=404, detail="File not found")

    enc_path = settings.STORAGE_DIR / doc_file.file_path
    if not enc_path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")

    plain = crypto.decrypt_bytes(enc_path.read_bytes())
    return Response(
        content=plain,
        media_type=doc_file.file_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{doc_file.original_filename}"'},
    )


@router.post("/{document_id}/versions", response_model=schemas.DocumentOut, status_code=201)
async def replace_document_version(
    document_id: str,
    title: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Re-upload a document: archives the current files as a version snapshot, then
    replaces them with the new ones. Old versions stay retrievable via
    GET /{document_id}/versions and /versions/{version_id}/download."""
    require_owner(current_user)
    doc = _get_owned_document(document_id, db, current_user)
    if not files:
        raise HTTPException(status_code=422, detail="At least one file is required")

    # Archive current files as a version snapshot.
    snapshot = [
        {
            "original_filename": f.original_filename,
            "file_path": f.file_path,
            "file_type": f.file_type,
            "file_size": f.file_size,
        }
        for f in doc.files
    ]
    if snapshot:
        db.add(models.DocumentVersion(
            document_id=doc.id,
            version=doc.version,
            title=doc.title,
            notes_enc=doc.notes_enc,
            files_json=json.dumps(snapshot),
        ))

    # Remove old DocumentFile rows (their files on disk stay — the version snapshot
    # above still points at those paths, so we do NOT delete the underlying bytes).
    for f in list(doc.files):
        db.delete(f)

    doc.version += 1
    if title:
        doc.title = title
    if notes is not None:
        doc.notes_enc = crypto.encrypt_text(notes if notes != "" else None)

    person_dir: Path = settings.STORAGE_DIR / vault_id(current_user) / doc.person_id
    person_dir.mkdir(parents=True, exist_ok=True)

    from app import quota

    prepared: list[tuple[bytes, str, str]] = []
    for idx, upload in enumerate(files):
        raw = await upload.read()
        stored_mime = (upload.content_type or "application/octet-stream").split(";")[0].strip()
        name = upload.filename or f"file_{idx}"
        if stored_mime.startswith("image/") or (
            not stored_mime.startswith("application/") and _looks_like_image(raw)
        ):
            raw = enhance_scan(raw, stored_mime if stored_mime.startswith("image/") else "image/jpeg")
            stored_mime = "image/jpeg"
            if not name.lower().endswith((".jpg", ".jpeg")):
                name = f"{name.rsplit('.', 1)[0]}.jpg"
        size_mb = len(raw) / (1024 * 1024)
        if size_mb > settings.MAX_UPLOAD_MB:
            db.rollback()
            raise HTTPException(status_code=413, detail=f"File '{name}' exceeds {settings.MAX_UPLOAD_MB} MB limit")
        if not raw:
            db.rollback()
            raise HTTPException(400, f"Empty file '{name}'")
        prepared.append((raw, name, stored_mime))

    try:
        quota.assert_can_store(db, current_user, sum(len(r) for r, _, _ in prepared))
    except HTTPException:
        db.rollback()
        raise

    ocr_chunks: list[str] = []
    first_mime: str | None = None
    first_size = 0
    for idx, (raw, name, stored_mime) in enumerate(prepared):
        enc_path = person_dir / f"{doc.id}_v{doc.version}_{idx}.enc"
        enc_path.write_bytes(crypto.encrypt_bytes(raw))
        ocr_chunks.append(extract_text(raw, stored_mime, name))

        db.add(models.DocumentFile(
            document_id=doc.id,
            original_filename=name,
            file_path=str(enc_path.relative_to(settings.STORAGE_DIR)),
            file_type=stored_mime,
            file_size=len(raw),
            content_hash=file_sha256(raw),
        ))
        if idx == 0:
            first_mime = stored_mime
            first_size = len(raw)

    doc.file_type = first_mime
    doc.file_size = first_size
    combined = "\n".join(c for c in ocr_chunks if c).strip() or None
    doc.extracted_text = combined
    db.query(models.LabReading).filter(models.LabReading.document_id == doc.id).delete()
    if combined:
        for reading in parse_lab_readings(combined):
            db.add(models.LabReading(
                person_id=doc.person_id,
                document_id=doc.id,
                metric=reading["metric"],
                value=reading["value"],
                unit=reading["unit"],
                measured_at=doc.doc_date,
            ))

    db.commit()
    db.refresh(doc)
    return _to_out(doc)


@router.get("/{document_id}/versions", response_model=List[schemas.DocumentVersionOut])
def list_document_versions(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    doc = _get_owned_document(document_id, db, current_user)
    versions = (
        db.query(models.DocumentVersion)
        .filter(models.DocumentVersion.document_id == doc.id)
        .order_by(models.DocumentVersion.version.desc())
        .all()
    )
    return [
        schemas.DocumentVersionOut(
            id=v.id, document_id=v.document_id, version=v.version, title=v.title,
            notes=crypto.decrypt_text(v.notes_enc), created_at=v.created_at,
        )
        for v in versions
    ]


@router.get("/{document_id}/versions/{version_id}/files/{index}/download")
def download_version_file(
    document_id: str,
    version_id: str,
    index: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    doc = _get_owned_document(document_id, db, current_user)
    version = db.query(models.DocumentVersion).filter(
        models.DocumentVersion.id == version_id, models.DocumentVersion.document_id == doc.id
    ).first()
    if not version:
        raise HTTPException(status_code=404, detail="Version not found")
    snapshot = json.loads(version.files_json)
    if index < 0 or index >= len(snapshot):
        raise HTTPException(status_code=404, detail="File not found in this version")
    entry = snapshot[index]
    enc_path = settings.STORAGE_DIR / entry["file_path"]
    if not enc_path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    plain = crypto.decrypt_bytes(enc_path.read_bytes())
    _log(db, current_user, doc.id, models.AuditAction.download, detail=f"v{version.version}:{entry['original_filename']}")
    db.commit()
    return Response(
        content=plain,
        media_type=entry.get("file_type") or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{entry["original_filename"]}"'},
    )


@router.delete("/{document_id}", status_code=204)
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Move a document to trash (soft delete). Files stay until permanent delete."""
    require_owner(current_user)
    doc = _get_owned_document(document_id, db, current_user)
    doc.deleted_at = datetime.utcnow()
    _log(db, current_user, doc.id, models.AuditAction.delete, detail="trash")
    db.commit()


@router.post("/{document_id}/restore", response_model=schemas.DocumentOut)
def restore_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    doc = _get_owned_document(document_id, db, current_user, include_deleted=True)
    if not doc.deleted_at:
        raise HTTPException(400, "Document is not in trash")
    doc.deleted_at = None
    db.commit()
    db.refresh(doc)
    return _to_out(doc)


@router.delete("/{document_id}/permanent", status_code=204)
def delete_document_forever(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    doc = _get_owned_document(document_id, db, current_user, include_deleted=True)
    if not doc.deleted_at:
        raise HTTPException(400, "Move the document to trash first")
    _purge_document(db, current_user, doc)
    db.commit()


def _purge_document(db: Session, current_user: models.User, doc: models.Document) -> None:
    """Hard-delete document row, related DB rows, and encrypted files on disk."""
    for f in list(doc.files or []):
        if not f.file_path:
            continue
        enc_path = settings.STORAGE_DIR / f.file_path
        if enc_path.exists():
            enc_path.unlink()
    if doc.file_path:
        enc_path = settings.STORAGE_DIR / doc.file_path
        if enc_path.exists():
            enc_path.unlink()
    versions = db.query(models.DocumentVersion).filter(models.DocumentVersion.document_id == doc.id).all()
    for v in versions:
        try:
            entries = json.loads(v.files_json or "[]")
        except Exception:
            entries = []
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                rel = entry.get("file_path")
                if not rel:
                    continue
                p = settings.STORAGE_DIR / rel
                if p.exists():
                    p.unlink()
        db.delete(v)
    share_ids = [row.id for row in db.query(models.ShareLink).filter(models.ShareLink.document_id == doc.id).all()]
    if share_ids:
        db.query(models.ShareAccess).filter(models.ShareAccess.share_link_id.in_(share_ids)).delete(synchronize_session=False)
    db.query(models.ShareLink).filter(models.ShareLink.document_id == doc.id).delete()
    db.query(models.AuditLog).filter(models.AuditLog.document_id == doc.id).delete()
    db.query(models.LabReading).filter(models.LabReading.document_id == doc.id).delete()
    db.query(models.Favorite).filter(models.Favorite.document_id == doc.id).delete()
    db.query(models.RecentOpen).filter(models.RecentOpen.document_id == doc.id).delete()
    db.query(models.SharePackItem).filter(models.SharePackItem.document_id == doc.id).delete()
    db.query(models.Reminder).filter(models.Reminder.document_id == doc.id).update(
        {models.Reminder.document_id: None}, synchronize_session=False
    )
    db.query(models.Medicine).filter(models.Medicine.document_id == doc.id).update(
        {models.Medicine.document_id: None}, synchronize_session=False
    )
    db.query(models.VaccinationRecord).filter(models.VaccinationRecord.document_id == doc.id).update(
        {models.VaccinationRecord.document_id: None}, synchronize_session=False
    )
    db.query(models.Claim).filter(models.Claim.document_id == doc.id).update(
        {models.Claim.document_id: None}, synchronize_session=False
    )
    _log(db, current_user, None, models.AuditAction.delete, detail=f"permanent:{doc.title}")
    db.delete(doc)
