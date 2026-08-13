import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.deps import get_current_user, get_owned_person, require_owner, vault_id, apply_person_visibility

router = APIRouter(prefix="/people", tags=["people"])


@router.get("", response_model=list[schemas.PersonOut])
def list_people(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    q = db.query(models.Person).filter(models.Person.user_id == vault_id(current_user))
    q = apply_person_visibility(q, db, current_user)
    return q.all()


@router.post("", response_model=schemas.PersonOut, status_code=201)
def add_family_member(
    body: schemas.PersonCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    initials = "".join([p[0].upper() for p in body.name.split()[:2]]) or "FM"
    person = models.Person(
        user_id=vault_id(current_user),
        name=body.name,
        relation=body.relation,
        dob=body.dob,
        blood_group=body.blood_group,
        avatar_initials=initials,
        allergies=body.allergies,
        conditions=body.conditions,
        emergency_name=body.emergency_name,
        emergency_phone=body.emergency_phone,
        abha_id=body.abha_id,
        ayushman_id=body.ayushman_id,
    )
    person.ice_token = secrets.token_urlsafe(18)
    db.add(person)
    db.commit()
    db.refresh(person)
    return person


@router.patch("/{person_id}", response_model=schemas.PersonOut)
def update_person(
    person_id: str,
    body: schemas.PersonUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    person = get_owned_person(person_id, db, current_user)
    for field, value in body.dict(exclude_unset=True).items():
        setattr(person, field, value)
    db.commit()
    db.refresh(person)
    return person


@router.delete("/{person_id}", status_code=204)
def delete_person(
    person_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    person = get_owned_person(person_id, db, current_user)
    if person.relation == models.Relation.self_:
        raise HTTPException(status_code=400, detail="Cannot delete your own profile")
    db.delete(person)
    db.commit()


@router.post("/{person_id}/ice", response_model=schemas.PersonOut)
def enable_ice(
    person_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    person = get_owned_person(person_id, db, current_user)
    if not person.ice_token:
        person.ice_token = secrets.token_urlsafe(18)
        db.commit()
        db.refresh(person)
    return person
