from typing import Optional, List
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, crypto
from app.config import settings
from app.deps import get_current_user, get_owned_person

router = APIRouter(prefix="/documents", tags=["documents"])


def _to_file_out(f: models.DocumentFile) -> schemas.DocumentFileOut:
    return schemas.DocumentFileOut(
        id=f.id,
        document_id=f.document_id,
        original_filename=f.original_filename,
        file_type=f.file_type,
        file_size=f.file_size,
        created_at=f.created_at,
    )


def _to_out(doc: models.Document) -> schemas.DocumentOut:
    # Determine effective file_type / file_size:
    # Prefer the first DocumentFile row; fall back to legacy columns.
    first_file = doc.files[0] if doc.files else None
    return schemas.DocumentOut(
        id=doc.id,
        person_id=doc.person_id,
        category=doc.category,
        title=doc.title,
        hospital_name=doc.hospital_name,
        doc_date=doc.doc_date,
        file_type=first_file.file_type if first_file else doc.file_type,
        file_size=first_file.file_size if first_file else doc.file_size,
        file_count=len(doc.files) if doc.files else (1 if doc.file_path else 0),
        notes=crypto.decrypt_text(doc.notes_enc),
        created_at=doc.created_at,
    )


@router.get("", response_model=list[schemas.DocumentOut])
def list_documents(
    person_id: Optional[str] = None,
    category: Optional[models.DocCategory] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    q = db.query(models.Document).join(models.Person).filter(models.Person.user_id == current_user.id)
    if person_id:
        q = q.filter(models.Document.person_id == person_id)
    if category:
        q = q.filter(models.Document.category == category)
    return [_to_out(d) for d in q.order_by(models.Document.created_at.desc()).all()]


@router.post("", response_model=schemas.DocumentOut, status_code=201)
async def upload_document(
    person_id: str = Form(...),
    category: models.DocCategory = Form(...),
    title: str = Form(...),
    hospital_name: Optional[str] = Form(None),
    doc_date: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Upload a document entry with one or more files (pages, scans, PDFs)."""
    get_owned_person(person_id, db, current_user)

    if not files:
        raise HTTPException(status_code=422, detail="At least one file is required")

    doc = models.Document(
        person_id=person_id,
        category=category,
        title=title,
        hospital_name=hospital_name,
        doc_date=doc_date,
        notes_enc=crypto.encrypt_text(notes),
        file_path="",  # legacy — no longer used for new uploads
    )
    db.add(doc)
    db.flush()  # get doc.id without committing

    person_dir: Path = settings.STORAGE_DIR / current_user.id / person_id
    person_dir.mkdir(parents=True, exist_ok=True)

    for idx, upload in enumerate(files):
        raw = await upload.read()
        size_mb = len(raw) / (1024 * 1024)
        if size_mb > settings.MAX_UPLOAD_MB:
            db.rollback()
            raise HTTPException(
                status_code=413,
                detail=f"File '{upload.filename}' exceeds {settings.MAX_UPLOAD_MB} MB limit"
            )

        enc_path = person_dir / f"{doc.id}_{idx}.enc"
        enc_path.write_bytes(crypto.encrypt_bytes(raw))

        doc_file = models.DocumentFile(
            document_id=doc.id,
            original_filename=upload.filename or f"file_{idx}",
            file_path=str(enc_path.relative_to(settings.STORAGE_DIR)),
            file_type=upload.content_type,
            file_size=len(raw),
        )
        db.add(doc_file)

    db.commit()
    db.refresh(doc)
    return _to_out(doc)


def _get_owned_document(document_id: str, db: Session, current_user: models.User) -> models.Document:
    doc = (
        db.query(models.Document)
        .join(models.Person)
        .filter(models.Document.id == document_id, models.Person.user_id == current_user.id)
        .first()
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/{document_id}", response_model=schemas.DocumentOut)
def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    doc = _get_owned_document(document_id, db, current_user)
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


@router.delete("/{document_id}", status_code=204)
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    doc = _get_owned_document(document_id, db, current_user)
    # Delete all associated files from disk
    for f in doc.files:
        enc_path = settings.STORAGE_DIR / f.file_path
        if enc_path.exists():
            enc_path.unlink()
    # Also delete legacy file if present
    if doc.file_path:
        enc_path = settings.STORAGE_DIR / doc.file_path
        if enc_path.exists():
            enc_path.unlink()
    db.delete(doc)
    db.commit()
