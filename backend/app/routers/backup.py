import io
import json
import zipfile
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, crypto
from app.config import settings
from app.deps import get_current_user, require_owner, vault_id
from app.extract import extract_text, parse_lab_readings

router = APIRouter(prefix="/backup", tags=["backup"])


def _json_default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    return str(o)


def _build_zip(people) -> bytes:
    manifest = {"exported_at": datetime.utcnow().isoformat(), "people": []}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for person in people:
            person_entry = {
                "name": person.name, "relation": person.relation.value if person.relation else None,
                "dob": person.dob, "blood_group": person.blood_group,
                "cards": [], "documents": [], "reminders": [],
            }
            for card in person.cards:
                person_entry["cards"].append({
                    "hospital_name": card.hospital_name, "ward": card.ward, "blood_group": card.blood_group,
                    "valid_from": card.valid_from, "valid_till": card.valid_till,
                    "patient_id": crypto.decrypt_text(card.patient_id_enc),
                    "notes": crypto.decrypt_text(card.notes_enc),
                })
            for doc in person.documents:
                doc_folder = f"{person.name}/{doc.category.value}/{doc.id}"
                file_names = []
                for f in doc.files:
                    enc_path = settings.STORAGE_DIR / f.file_path
                    if enc_path.exists():
                        plain = crypto.decrypt_bytes(enc_path.read_bytes())
                        arcname = f"{doc_folder}/{f.original_filename}"
                        zf.writestr(arcname, plain)
                        file_names.append(arcname)
                person_entry["documents"].append({
                    "title": doc.title, "category": doc.category.value, "custom_category": doc.custom_category,
                    "hospital_name": doc.hospital_name, "doc_date": doc.doc_date, "expiry_date": doc.expiry_date,
                    "tags": doc.tags, "notes": crypto.decrypt_text(doc.notes_enc),
                    "extracted_text": doc.extracted_text, "files": file_names,
                })
            for rem in person.reminders:
                person_entry["reminders"].append({
                    "title": rem.title, "description": rem.description,
                    "remind_at": rem.remind_at, "repeat_rule": rem.repeat_rule.value, "is_active": rem.is_active,
                })
            manifest["people"].append(person_entry)
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, default=_json_default))
    return buf.getvalue()


@router.get("/export")
def export_backup(
    person_id: Optional[str] = None,
    password: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Zip of the vault (or one person). Pass ?password= to wrap it in a password-encrypted envelope."""
    q = db.query(models.Person).filter(models.Person.user_id == vault_id(current_user))
    if person_id:
        q = q.filter(models.Person.id == person_id)
    people = q.all()
    if person_id and not people:
        raise HTTPException(status_code=404, detail="Person not found")

    zip_bytes = _build_zip(people)
    if password:
        zip_bytes = crypto.encrypt_backup(zip_bytes, password)
        fname = f"healthvault-backup-{datetime.utcnow().strftime('%Y%m%d')}.hvbak"
        media = "application/octet-stream"
    else:
        fname = f"healthvault-backup-{datetime.utcnow().strftime('%Y%m%d')}.zip"
        media = "application/zip"

    return StreamingResponse(
        io.BytesIO(zip_bytes), media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/snapshot")
def snapshot_to_disk(
    password: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Write an encrypted backup into BACKUP_DIR (USB / Syncthing folder)."""
    require_owner(current_user)
    if not settings.BACKUP_DIR:
        raise HTTPException(status_code=400, detail="BACKUP_DIR is not set on the server")
    settings.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    people = db.query(models.Person).filter(models.Person.user_id == vault_id(current_user)).all()
    blob = _build_zip(people)
    if password:
        blob = crypto.encrypt_backup(blob, password)
        name = f"healthvault-{datetime.utcnow().strftime('%Y%m%d-%H%M')}.hvbak"
    else:
        name = f"healthvault-{datetime.utcnow().strftime('%Y%m%d-%H%M')}.zip"
    dest = settings.BACKUP_DIR / name
    dest.write_bytes(blob)
    return {"ok": True, "path": str(dest), "bytes": len(blob)}


@router.post("/restore")
async def restore_backup(
    file: UploadFile = File(...),
    password: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Restore a previously exported zip (optionally password-encrypted) into this vault."""
    require_owner(current_user)
    blob = await file.read()
    try:
        zip_bytes = crypto.decrypt_backup(blob, password or "") if blob.startswith(b"HV1\0") else blob
        if blob.startswith(b"HV1\0") and not password:
            raise HTTPException(status_code=400, detail="This backup is encrypted — a password is required")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Could not decrypt backup — check the password")

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Not a valid backup zip")

    try:
        manifest = json.loads(zf.read("manifest.json"))
    except KeyError:
        raise HTTPException(status_code=400, detail="Backup is missing manifest.json")

    owner = vault_id(current_user)
    restored = {"people": 0, "documents": 0, "cards": 0}

    for person_entry in manifest.get("people", []):
        existing = (
            db.query(models.Person)
            .filter(models.Person.user_id == owner, models.Person.name == person_entry.get("name"))
            .first()
        )
        if existing:
            person = existing
        else:
            rel = person_entry.get("relation") or "other"
            try:
                relation = models.Relation(rel)
            except ValueError:
                relation = models.Relation.other
            if relation == models.Relation.self_:
                # Don't create a second 'self' — attach to the account's existing self profile.
                person = (
                    db.query(models.Person)
                    .filter(models.Person.user_id == owner, models.Person.relation == models.Relation.self_)
                    .first()
                )
                if not person:
                    person = models.Person(
                        user_id=owner, name=person_entry["name"], relation=relation,
                        dob=person_entry.get("dob"), blood_group=person_entry.get("blood_group"),
                    )
                    db.add(person)
                    db.flush()
            else:
                person = models.Person(
                    user_id=owner, name=person_entry["name"], relation=relation,
                    dob=person_entry.get("dob"), blood_group=person_entry.get("blood_group"),
                )
                db.add(person)
                db.flush()
                restored["people"] += 1

        for card in person_entry.get("cards", []):
            db.add(models.HospitalCard(
                person_id=person.id,
                hospital_name=card.get("hospital_name") or "Unknown",
                ward=card.get("ward"),
                blood_group=card.get("blood_group"),
                valid_from=card.get("valid_from"),
                valid_till=card.get("valid_till"),
                patient_id_enc=crypto.encrypt_text(card.get("patient_id")),
                notes_enc=crypto.encrypt_text(card.get("notes")),
            ))
            restored["cards"] += 1

        person_dir = settings.STORAGE_DIR / owner / person.id
        person_dir.mkdir(parents=True, exist_ok=True)

        for doc_entry in person_entry.get("documents", []):
            try:
                cat = models.DocCategory(doc_entry.get("category") or "other")
            except ValueError:
                cat = models.DocCategory.other
            doc = models.Document(
                person_id=person.id,
                category=cat,
                custom_category=doc_entry.get("custom_category"),
                title=doc_entry.get("title") or "Restored document",
                hospital_name=doc_entry.get("hospital_name"),
                doc_date=doc_entry.get("doc_date"),
                expiry_date=doc_entry.get("expiry_date"),
                tags=doc_entry.get("tags"),
                notes_enc=crypto.encrypt_text(doc_entry.get("notes")),
                extracted_text=doc_entry.get("extracted_text"),
                file_path="",
            )
            db.add(doc)
            db.flush()
            for idx, arcname in enumerate(doc_entry.get("files") or []):
                try:
                    raw = zf.read(arcname)
                except KeyError:
                    continue
                enc_path = person_dir / f"{doc.id}_{idx}.enc"
                enc_path.write_bytes(crypto.encrypt_bytes(raw))
                db.add(models.DocumentFile(
                    document_id=doc.id,
                    original_filename=arcname.split("/")[-1],
                    file_path=str(enc_path.relative_to(settings.STORAGE_DIR)),
                    file_type="application/octet-stream",
                    file_size=len(raw),
                ))
                if not doc.extracted_text:
                    text = extract_text(raw, None, arcname)
                    if text:
                        doc.extracted_text = (doc.extracted_text or "") + "\n" + text
            if doc.extracted_text:
                for reading in parse_lab_readings(doc.extracted_text):
                    db.add(models.LabReading(
                        person_id=person.id, document_id=doc.id,
                        metric=reading["metric"], value=reading["value"],
                        unit=reading["unit"], measured_at=doc.doc_date,
                    ))
            restored["documents"] += 1

        for rem in person_entry.get("reminders", []):
            try:
                rule = models.RepeatRule(rem.get("repeat_rule") or "none")
            except ValueError:
                rule = models.RepeatRule.none
            remind_at = rem.get("remind_at")
            if isinstance(remind_at, str):
                try:
                    remind_at = datetime.fromisoformat(remind_at.replace("Z", ""))
                except ValueError:
                    remind_at = datetime.utcnow()
            db.add(models.Reminder(
                person_id=person.id,
                title=rem.get("title") or "Reminder",
                description=rem.get("description"),
                remind_at=remind_at or datetime.utcnow(),
                repeat_rule=rule,
                is_active=bool(rem.get("is_active", True)),
            ))

    db.commit()
    return {"ok": True, **restored}
