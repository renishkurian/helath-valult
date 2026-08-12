from typing import Optional
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, crypto
from app.config import settings
from app.deps import get_current_user, get_owned_person

router = APIRouter(prefix="/documents", tags=["documents"])


def _to_out(doc: models.Document) -> schemas.DocumentOut:
    return schemas.DocumentOut(
        id=doc.id,
        person_id=doc.person_id,
        category=doc.category,
        title=doc.title,
        hospital_name=doc.hospital_name,
        doc_date=doc.doc_date,
        file_type=doc.file_type,
        file_size=doc.file_size,
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
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    get_owned_person(person_id, db, current_user)

    raw = await file.read()
    size_mb = len(raw) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_MB:
        raise HTTPException(status_code=413, detail=f"File exceeds {settings.MAX_UPLOAD_MB} MB limit")

    doc = models.Document(
        person_id=person_id,
        category=category,
        title=title,
        hospital_name=hospital_name,
        doc_date=doc_date,
        file_type=file.content_type,
        file_size=len(raw),
        notes_enc=crypto.encrypt_text(notes),
        file_path="",  # set after we know the id
    )
    db.add(doc)
    db.flush()

    person_dir: Path = settings.STORAGE_DIR / current_user.id / person_id
    person_dir.mkdir(parents=True, exist_ok=True)
    enc_path = person_dir / f"{doc.id}.enc"
    enc_path.write_bytes(crypto.encrypt_bytes(raw))

    doc.file_path = str(enc_path.relative_to(settings.STORAGE_DIR))
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


@router.get("/{document_id}/download")
def download_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    doc = _get_owned_document(document_id, db, current_user)
    enc_path = settings.STORAGE_DIR / doc.file_path
    if not enc_path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")

    plain = crypto.decrypt_bytes(enc_path.read_bytes())
    return Response(
        content=plain,
        media_type=doc.file_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{doc.title}"'},
    )


@router.delete("/{document_id}", status_code=204)
def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    doc = _get_owned_document(document_id, db, current_user)
    enc_path = settings.STORAGE_DIR / doc.file_path
    if enc_path.exists():
        enc_path.unlink()
    db.delete(doc)
    db.commit()
