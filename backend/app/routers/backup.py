import io
import json
import zipfile
from datetime import datetime, date

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, crypto
from app.config import settings
from app.deps import get_current_user

router = APIRouter(prefix="/backup", tags=["backup"])


def _json_default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    return str(o)


@router.get("/export")
def export_backup(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Zip of everything in the account: a manifest.json (people, cards, documents,
    reminders — decrypted, since this export is meant to be re-encrypted/stored by
    the person themselves) plus every original document file, organized by person.
    Good for an offline backup or handing a full record set to a new doctor."""
    people = db.query(models.Person).filter(models.Person.user_id == current_user.id).all()

    manifest = {"exported_at": datetime.utcnow().isoformat(), "user_email": current_user.email, "people": []}

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
                    "tags": doc.tags, "notes": crypto.decrypt_text(doc.notes_enc), "files": file_names,
                })
            for rem in person.reminders:
                person_entry["reminders"].append({
                    "title": rem.title, "description": rem.description,
                    "remind_at": rem.remind_at, "repeat_rule": rem.repeat_rule.value, "is_active": rem.is_active,
                })
            manifest["people"].append(person_entry)

        zf.writestr("manifest.json", json.dumps(manifest, indent=2, default=_json_default))

    buf.seek(0)
    fname = f"healthvault-backup-{datetime.utcnow().strftime('%Y%m%d')}.zip"
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
