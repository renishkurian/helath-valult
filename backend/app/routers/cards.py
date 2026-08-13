from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, crypto
from app.deps import get_current_user, get_owned_person, require_owner, vault_id

router = APIRouter(prefix="/cards", tags=["cards"])


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
        created_at=card.created_at,
    )


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

    card = models.HospitalCard(
        person_id=body.person_id,
        hospital_name=body.hospital_name,
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
                title=f"{body.hospital_name} card expires",
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
    for field, value in data.items():
        setattr(card, field, value)
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
    db.delete(card)
    db.commit()
