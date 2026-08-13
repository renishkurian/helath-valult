from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.deps import get_current_user, get_owned_person, require_owner, vault_id

router = APIRouter(tags=["health"])


def _vax_out(row: models.VaccinationRecord) -> schemas.VaccinationOut:
    overdue = False
    if row.next_due:
        try:
            overdue = datetime.strptime(row.next_due, "%Y-%m-%d").date() < datetime.utcnow().date()
        except ValueError:
            overdue = False
    return schemas.VaccinationOut(
        id=row.id, person_id=row.person_id, document_id=row.document_id,
        vaccine_name=row.vaccine_name, dose_number=row.dose_number,
        given_on=row.given_on, next_due=row.next_due, notes=row.notes,
        overdue=overdue, created_at=row.created_at,
    )


# ---------- Medicines ----------
@router.get("/medicines", response_model=list[schemas.MedicineOut])
def list_medicines(person_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    get_owned_person(person_id, db, current_user)
    return db.query(models.Medicine).filter(models.Medicine.person_id == person_id).order_by(models.Medicine.created_at.desc()).all()


@router.post("/medicines", response_model=schemas.MedicineOut, status_code=201)
def add_medicine(body: schemas.MedicineIn, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    get_owned_person(body.person_id, db, current_user)
    row = models.Medicine(**body.model_dump())
    db.add(row)
    if body.refill_at:
        try:
            remind = datetime.strptime(body.refill_at, "%Y-%m-%d")
            db.add(models.Reminder(
                person_id=body.person_id, document_id=body.document_id,
                title=f"Refill {body.name}", description=body.dose,
                remind_at=remind.replace(hour=9, minute=0, second=0, microsecond=0),
                repeat_rule=models.RepeatRule.none,
            ))
        except ValueError:
            pass
    db.commit()
    db.refresh(row)
    return row


@router.delete("/medicines/{item_id}", status_code=204)
def delete_medicine(item_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    row = db.query(models.Medicine).filter(models.Medicine.id == item_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    get_owned_person(row.person_id, db, current_user)
    db.delete(row)
    db.commit()


# ---------- Vaccinations ----------
@router.get("/vaccinations", response_model=list[schemas.VaccinationOut])
def list_vaccinations(person_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    get_owned_person(person_id, db, current_user)
    rows = db.query(models.VaccinationRecord).filter(models.VaccinationRecord.person_id == person_id).order_by(models.VaccinationRecord.next_due.asc()).all()
    return [_vax_out(r) for r in rows]


@router.post("/vaccinations", response_model=schemas.VaccinationOut, status_code=201)
def add_vaccination(body: schemas.VaccinationIn, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    get_owned_person(body.person_id, db, current_user)
    row = models.VaccinationRecord(**body.model_dump())
    db.add(row)
    if body.next_due:
        try:
            remind = datetime.strptime(body.next_due, "%Y-%m-%d")
            db.add(models.Reminder(
                person_id=body.person_id, title=f"{body.vaccine_name} due",
                remind_at=remind.replace(hour=9, minute=0, second=0, microsecond=0),
                repeat_rule=models.RepeatRule.none,
            ))
        except ValueError:
            pass
    db.commit()
    db.refresh(row)
    return _vax_out(row)


@router.delete("/vaccinations/{item_id}", status_code=204)
def delete_vaccination(item_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    row = db.query(models.VaccinationRecord).filter(models.VaccinationRecord.id == item_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    get_owned_person(row.person_id, db, current_user)
    db.delete(row)
    db.commit()


# ---------- Visits ----------
@router.get("/visits", response_model=list[schemas.VisitOut])
def list_visits(person_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    get_owned_person(person_id, db, current_user)
    return db.query(models.Visit).filter(models.Visit.person_id == person_id).order_by(models.Visit.visit_date.desc()).all()


@router.post("/visits", response_model=schemas.VisitOut, status_code=201)
def add_visit(body: schemas.VisitIn, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    get_owned_person(body.person_id, db, current_user)
    row = models.Visit(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/visits/{item_id}", status_code=204)
def delete_visit(item_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    row = db.query(models.Visit).filter(models.Visit.id == item_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    get_owned_person(row.person_id, db, current_user)
    db.delete(row)
    db.commit()


# ---------- Claims ----------
@router.get("/claims", response_model=list[schemas.ClaimOut])
def list_claims(person_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    get_owned_person(person_id, db, current_user)
    return db.query(models.Claim).filter(models.Claim.person_id == person_id).order_by(models.Claim.created_at.desc()).all()


@router.post("/claims", response_model=schemas.ClaimOut, status_code=201)
def add_claim(body: schemas.ClaimIn, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    get_owned_person(body.person_id, db, current_user)
    row = models.Claim(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.patch("/claims/{item_id}", response_model=schemas.ClaimOut)
def update_claim(item_id: str, body: schemas.ClaimIn, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    row = db.query(models.Claim).filter(models.Claim.id == item_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    get_owned_person(row.person_id, db, current_user)
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@router.get("/claims/spend", response_model=schemas.SpendOut)
def yearly_spend(person_id: str, year: Optional[int] = None, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    get_owned_person(person_id, db, current_user)
    year = year or datetime.utcnow().year
    prefix = str(year)

    def _num(v) -> float:
        try:
            return float(str(v).replace(",", "").strip())
        except (TypeError, ValueError):
            return 0.0

    bills = 0.0
    for d in db.query(models.Document).filter(
        models.Document.person_id == person_id,
        models.Document.category == models.DocCategory.bill,
    ).all():
        stamp = d.doc_date or (d.created_at.isoformat() if d.created_at else "")
        if stamp.startswith(prefix):
            bills += _num(d.amount)

    claims = 0.0
    for c in db.query(models.Claim).filter(models.Claim.person_id == person_id).all():
        stamp = c.submitted_on or (c.created_at.isoformat() if c.created_at else "")
        if stamp.startswith(prefix):
            claims += _num(c.amount)
    return schemas.SpendOut(year=year, bills=round(bills, 2), claims=round(claims, 2), total=round(bills + claims, 2))


# ---------- Doctors ----------
@router.get("/doctors", response_model=list[schemas.DoctorOut])
def list_doctors(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    return db.query(models.Doctor).filter(models.Doctor.user_id == vault_id(current_user)).order_by(models.Doctor.name.asc()).all()


@router.post("/doctors", response_model=schemas.DoctorOut, status_code=201)
def add_doctor(body: schemas.DoctorIn, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    row = models.Doctor(user_id=vault_id(current_user), **body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/doctors/{item_id}", status_code=204)
def delete_doctor(item_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    row = db.query(models.Doctor).filter(models.Doctor.id == item_id, models.Doctor.user_id == vault_id(current_user)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(row)
    db.commit()


# ---------- Growth ----------
@router.get("/growth", response_model=list[schemas.GrowthOut])
def list_growth(person_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    get_owned_person(person_id, db, current_user)
    return db.query(models.GrowthReading).filter(models.GrowthReading.person_id == person_id).order_by(models.GrowthReading.measured_at.asc()).all()


@router.post("/growth", response_model=schemas.GrowthOut, status_code=201)
def add_growth(body: schemas.GrowthIn, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    get_owned_person(body.person_id, db, current_user)
    row = models.GrowthReading(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/growth/{item_id}", status_code=204)
def delete_growth(item_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    row = db.query(models.GrowthReading).filter(models.GrowthReading.id == item_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    get_owned_person(row.person_id, db, current_user)
    db.delete(row)
    db.commit()


# ---------- UHID ----------
@router.get("/uhids", response_model=list[schemas.UhidOut])
def list_uhids(person_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    get_owned_person(person_id, db, current_user)
    return db.query(models.HospitalUhid).filter(models.HospitalUhid.person_id == person_id).all()


@router.post("/uhids", response_model=schemas.UhidOut, status_code=201)
def add_uhid(body: schemas.UhidIn, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    get_owned_person(body.person_id, db, current_user)
    row = models.HospitalUhid(**body.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/uhids/{item_id}", status_code=204)
def delete_uhid(item_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    row = db.query(models.HospitalUhid).filter(models.HospitalUhid.id == item_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    get_owned_person(row.person_id, db, current_user)
    db.delete(row)
    db.commit()


# ---------- Timeline ----------
@router.get("/timeline", response_model=list[schemas.TimelineItem])
def timeline(person_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    get_owned_person(person_id, db, current_user)
    items: list[schemas.TimelineItem] = []
    for d in db.query(models.Document).filter(models.Document.person_id == person_id).all():
        items.append(schemas.TimelineItem(
            kind="document", at=d.doc_date or (d.created_at.isoformat() if d.created_at else ""),
            title=d.title, detail=d.hospital_name, ref_id=d.id,
        ))
    for v in db.query(models.Visit).filter(models.Visit.person_id == person_id).all():
        items.append(schemas.TimelineItem(
            kind="visit", at=v.visit_date or "", title=v.reason or "Visit",
            detail=v.hospital_name, ref_id=v.id,
        ))
    for x in db.query(models.VaccinationRecord).filter(models.VaccinationRecord.person_id == person_id).all():
        items.append(schemas.TimelineItem(
            kind="vaccination", at=x.given_on or "", title=x.vaccine_name,
            detail=f"dose {x.dose_number}", ref_id=x.id,
        ))
    for g in db.query(models.GrowthReading).filter(models.GrowthReading.person_id == person_id).all():
        items.append(schemas.TimelineItem(
            kind="growth", at=g.measured_at, title="Height / weight",
            detail=" / ".join(p for p in [g.height_cm and f"{g.height_cm} cm", g.weight_kg and f"{g.weight_kg} kg"] if p),
            ref_id=g.id,
        ))
    items.sort(key=lambda i: i.at or "", reverse=True)
    return items[:200]
