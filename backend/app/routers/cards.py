from typing import Optional
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app import models, schemas, crypto
from app.deps import get_current_user, get_owned_person, require_owner, vault_id
from app.templating import nice_name

router = APIRouter(prefix="/cards", tags=["cards"])

_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}


def _to_out(card: models.HospitalCard) -> schemas.CardOut:
    return schemas.CardOut(
        id=card.id,
        person_id=card.person_id,
        hospital_name=card.hospital_name,
        ward=card.ward,
        blood_group=card.blood_group,
        valid_from=card.valid_from,
        valid_till=card.valid_till,
        patient_id=crypto.decrypt_text(card.patient_id_enc),
        notes=crypto.decrypt_text(card.notes_enc),
        has_image=bool(card.image_path),
        created_at=card.created_at,
    )


def save_card_image(
    card: models.HospitalCard,
    *,
    raw: bytes,
    content_type: str | None,
    owner_id: str,
) -> None:
    """Encrypt and store a patient-card scan next to the hospital card row."""
    mime = (content_type or "image/jpeg").split(";")[0].strip().lower()
    if mime == "image/jpg":
        mime = "image/jpeg"
    if mime not in _IMAGE_TYPES:
        raise HTTPException(400, "Upload a JPG, PNG, WEBP, or GIF image")
    size_mb = len(raw) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_MB:
        raise HTTPException(413, f"Image exceeds {settings.MAX_UPLOAD_MB} MB limit")
    if not raw:
        raise HTTPException(400, "Empty image")

    # Remove previous file if replacing.
    if card.image_path:
        old = settings.STORAGE_DIR / card.image_path
        if old.is_file():
            old.unlink()

    person_dir = settings.STORAGE_DIR / owner_id / card.person_id / "cards"
    person_dir.mkdir(parents=True, exist_ok=True)
    enc_path = person_dir / f"{card.id}.enc"
    enc_path.write_bytes(crypto.encrypt_bytes(raw))
    card.image_path = str(enc_path.relative_to(settings.STORAGE_DIR))
    card.image_mime = mime


def unlink_card_image(card: models.HospitalCard) -> None:
    if not card.image_path:
        return
    path = settings.STORAGE_DIR / card.image_path
    if path.is_file():
        path.unlink()
    card.image_path = None
    card.image_mime = None


@router.get("", response_model=list[schemas.CardOut])
def list_cards(
    person_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    q = db.query(models.HospitalCard).join(models.Person).filter(models.Person.user_id == vault_id(current_user))
    if person_id:
        q = q.filter(models.HospitalCard.person_id == person_id)
    return [_to_out(c) for c in q.order_by(models.HospitalCard.created_at.desc()).all()]


@router.post("", response_model=schemas.CardOut, status_code=201)
def create_card(
    body: schemas.CardCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    get_owned_person(body.person_id, db, current_user)  # 404s if not owned

    hosp = nice_name(body.hospital_name)
    card = models.HospitalCard(
        person_id=body.person_id,
        hospital_name=hosp,
        ward=body.ward,
        blood_group=body.blood_group,
        valid_from=body.valid_from,
        valid_till=body.valid_till,
        patient_id_enc=crypto.encrypt_text(body.patient_id),
        notes_enc=crypto.encrypt_text(body.notes),
    )
    db.add(card)
    db.flush()
    if body.valid_till:
        from datetime import datetime, timedelta
        try:
            expiry = datetime.strptime(body.valid_till, "%Y-%m-%d")
            remind = (expiry - timedelta(days=7)).replace(hour=9, minute=0, second=0, microsecond=0)
            if remind <= datetime.utcnow():
                remind = datetime.utcnow() + timedelta(minutes=5)
            db.add(models.Reminder(
                person_id=body.person_id,
                title=f"{hosp} card expires",
                description=f"Renew before {body.valid_till}",
                remind_at=remind,
                repeat_rule=models.RepeatRule.none,
            ))
        except ValueError:
            pass
    db.commit()
    db.refresh(card)
    return _to_out(card)


def _get_owned_card(card_id: str, db: Session, current_user: models.User) -> models.HospitalCard:
    card = (
        db.query(models.HospitalCard)
        .join(models.Person)
        .filter(models.HospitalCard.id == card_id, models.Person.user_id == vault_id(current_user))
        .first()
    )
    if not card:
        raise HTTPException(status_code=404, detail="Card not found")
    return card


@router.patch("/{card_id}", response_model=schemas.CardOut)
def update_card(
    card_id: str,
    body: schemas.CardUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    card = _get_owned_card(card_id, db, current_user)
    data = body.dict(exclude_unset=True)
    if "patient_id" in data:
        card.patient_id_enc = crypto.encrypt_text(data.pop("patient_id"))
    if "notes" in data:
        card.notes_enc = crypto.encrypt_text(data.pop("notes"))
    if "hospital_name" in data and data["hospital_name"] is not None:
        data["hospital_name"] = nice_name(data["hospital_name"])
    for field, value in data.items():
        setattr(card, field, value)
    db.commit()
    db.refresh(card)
    return _to_out(card)


@router.post("/{card_id}/image", response_model=schemas.CardOut)
async def upload_card_image(
    card_id: str,
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    card = _get_owned_card(card_id, db, current_user)
    raw = await photo.read()
    save_card_image(card, raw=raw, content_type=photo.content_type, owner_id=vault_id(current_user))
    db.commit()
    db.refresh(card)
    return _to_out(card)


@router.get("/{card_id}/image")
def get_card_image(
    card_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    card = _get_owned_card(card_id, db, current_user)
    if not card.image_path:
        raise HTTPException(404, "Card image not found")
    path = settings.STORAGE_DIR / card.image_path
    if not path.is_file():
        raise HTTPException(404, "Card image not found")
    raw = crypto.decrypt_bytes(path.read_bytes())
    return Response(content=raw, media_type=card.image_mime or "image/jpeg")


@router.delete("/{card_id}/image", response_model=schemas.CardOut)
def delete_card_image(
    card_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    card = _get_owned_card(card_id, db, current_user)
    unlink_card_image(card)
    db.commit()
    db.refresh(card)
    return _to_out(card)


@router.delete("/{card_id}", status_code=204)
def delete_card(
    card_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    card = _get_owned_card(card_id, db, current_user)
    unlink_card_image(card)
    db.delete(card)
    db.commit()
