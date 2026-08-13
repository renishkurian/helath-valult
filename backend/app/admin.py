import calendar
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, security, crypto
from app.config import settings
from app.deps import vault_id, is_viewer

router = APIRouter(prefix="/admin", tags=["admin"])
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


# ---------- Session auth helpers ----------
def get_session_user(request: Request, db: Session = Depends(get_db)) -> Optional[models.User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.query(models.User).filter(models.User.id == user_id).first()


def require_login(request: Request, db: Session) -> Optional[models.User]:
    """Returns the user, or None if not logged in (caller should redirect)."""
    return get_session_user(request, db)


def card_out(card: models.HospitalCard) -> dict:
    return {
        "id": card.id, "hospital_name": card.hospital_name, "ward": card.ward,
        "blood_group": card.blood_group, "valid_from": card.valid_from, "valid_till": card.valid_till,
        "patient_id": crypto.decrypt_text(card.patient_id_enc), "notes": crypto.decrypt_text(card.notes_enc),
    }


def doc_out(doc: models.Document) -> dict:
    return {
        "id": doc.id, "category": doc.category.value, "title": doc.title,
        "hospital_name": doc.hospital_name, "doc_date": doc.doc_date,
        "expiry_date": doc.expiry_date, "tags": doc.tags,
        "file_size": doc.file_size or 0, "created_at": doc.created_at,
        "notes": crypto.decrypt_text(doc.notes_enc),
    }


# ---------- Login / logout ----------
@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/admin/modules", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user or not security.verify_password(password, user.hashed_password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Incorrect email or password"})
    request.session["user_id"] = user.id
    return RedirectResponse("/admin/modules", status_code=302)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=302)


# ---------- Dashboard ----------
@router.get("/modules", response_class=HTMLResponse)
def modules_home(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    return templates.TemplateResponse("modules.html", {
        "request": request, "session_user": user, "active_nav": "modules", "active_module": "picker",
        "people": [], "active_person_id": None,
    })


@router.get("", response_class=HTMLResponse)
def dashboard(request: Request, person: Optional[str] = None, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)

    people = db.query(models.Person).filter(models.Person.user_id == vault_id(user)).all()
    active_person = None
    if person:
        active_person = next((p for p in people if p.id == person), None)
    if not active_person:
        active_person = next((p for p in people if p.relation == models.Relation.self_), people[0] if people else None)

    cards, documents, folder_counts, recent_documents, expiring_cards = [], [], {}, [], []
    if active_person:
        card_rows = db.query(models.HospitalCard).filter(models.HospitalCard.person_id == active_person.id).all()
        cards = [card_out(c) for c in card_rows]

        today = datetime.utcnow().date()
        for c in cards:
            if c["valid_till"]:
                try:
                    till = datetime.strptime(c["valid_till"], "%Y-%m-%d").date()
                    if 0 <= (till - today).days <= 30:
                        expiring_cards.append(c)
                except ValueError:
                    pass

        doc_rows = db.query(models.Document).filter(models.Document.person_id == active_person.id).all()
        documents = [doc_out(d) for d in doc_rows]
        folder_counts = {cat.value: 0 for cat in models.DocCategory}
        for d in documents:
            folder_counts[d["category"]] = folder_counts.get(d["category"], 0) + 1
        recent_documents = sorted(documents, key=lambda d: d["created_at"], reverse=True)[:8]

    return templates.TemplateResponse("dashboard.html", {
        "request": request, "session_user": user, "active_nav": "dashboard",
        "people": people, "active_person": active_person, "active_person_id": active_person.id if active_person else None,
        "cards": cards, "folder_counts": folder_counts, "recent_documents": recent_documents,
        "expiring_cards": expiring_cards,
    })


# ---------- Family ----------
@router.get("/family", response_class=HTMLResponse)
def family_page(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    people = db.query(models.Person).filter(models.Person.user_id == vault_id(user)).all()
    return templates.TemplateResponse("family.html", {
        "request": request, "session_user": user, "active_nav": "family", "people": people,
        "active_person_id": None,
    })


@router.post("/family/add")
def family_add(
    request: Request,
    name: str = Form(...), relation: str = Form("other"), blood_group: str = Form(""),
    db: Session = Depends(get_db)
):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    initials = "".join([p[0].upper() for p in name.split()[:2]]) or "FM"
    person = models.Person(
        user_id=vault_id(user), name=name, relation=models.Relation(relation),
        blood_group=blood_group or None, avatar_initials=initials,
    )
    db.add(person)
    db.commit()
    return RedirectResponse("/admin/family", status_code=302)


@router.post("/people/{person_id}/delete")
def people_delete(request: Request, person_id: str, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    p = db.query(models.Person).filter(models.Person.id == person_id, models.Person.user_id == vault_id(user)).first()
    if p and p.relation != models.Relation.self_:
        db.delete(p)
        db.commit()
    return RedirectResponse("/admin/family", status_code=302)


# ---------- Cards ----------
@router.post("/cards/add")
def cards_add(
    request: Request,
    person_id: str = Form(...), hospital_name: str = Form(...),
    ward: str = Form(""), blood_group: str = Form(""),
    valid_from: str = Form(""), valid_till: str = Form(""),
    patient_id: str = Form(""), notes: str = Form(""),
    db: Session = Depends(get_db)
):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    person = db.query(models.Person).filter(models.Person.id == person_id, models.Person.user_id == vault_id(user)).first()
    if person:
        card = models.HospitalCard(
            person_id=person.id, hospital_name=hospital_name, ward=ward or None, blood_group=blood_group or None,
            valid_from=valid_from or None, valid_till=valid_till or None,
            patient_id_enc=crypto.encrypt_text(patient_id or None), notes_enc=crypto.encrypt_text(notes or None),
        )
        db.add(card)
        db.commit()
    return RedirectResponse(f"/admin?person={person_id}", status_code=302)


@router.post("/cards/{card_id}/delete")
def cards_delete(request: Request, card_id: str, person_id: str = Form(...), db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    card = (
        db.query(models.HospitalCard).join(models.Person)
        .filter(models.HospitalCard.id == card_id, models.Person.user_id == vault_id(user)).first()
    )
    if card:
        db.delete(card)
        db.commit()
    return RedirectResponse(f"/admin?person={person_id}", status_code=302)


# ---------- Documents ----------
@router.get("/documents", response_class=HTMLResponse)
def documents_page(request: Request, person: str, category: Optional[str] = None, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)

    active_person = db.query(models.Person).filter(models.Person.id == person, models.Person.user_id == vault_id(user)).first()
    if not active_person:
        return RedirectResponse("/admin", status_code=302)

    q = db.query(models.Document).filter(models.Document.person_id == active_person.id)
    if category:
        q = q.filter(models.Document.category == models.DocCategory(category))
    docs = [doc_out(d) for d in q.order_by(models.Document.created_at.desc()).all()]

    people = db.query(models.Person).filter(models.Person.user_id == vault_id(user)).all()
    return templates.TemplateResponse("documents.html", {
        "request": request, "session_user": user, "active_nav": "dashboard",
        "people": people, "active_person": active_person, "active_person_id": active_person.id,
        "documents": docs, "category": category,
    })


@router.post("/documents/add")
async def documents_add(
    request: Request,
    person_id: str = Form(...), category: str = Form(...), title: str = Form(...),
    hospital_name: str = Form(""), doc_date: str = Form(""), notes: str = Form(""),
    expiry_date: str = Form(""), tags: str = Form(""),
    redirect_to: str = Form("dashboard"), redirect_category: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)

    person = db.query(models.Person).filter(models.Person.id == person_id, models.Person.user_id == vault_id(user)).first()
    if person:
        raw = await file.read()
        doc = models.Document(
            person_id=person.id, category=models.DocCategory(category), title=title,
            hospital_name=hospital_name or None, doc_date=doc_date or None,
            expiry_date=expiry_date or None, tags=tags or None,
            file_type=file.content_type, file_size=len(raw),
            notes_enc=crypto.encrypt_text(notes or None), file_path="",
        )
        db.add(doc)
        db.flush()

        person_dir = settings.STORAGE_DIR / vault_id(user) / person.id
        person_dir.mkdir(parents=True, exist_ok=True)
        enc_path = person_dir / f"{doc.id}.enc"
        enc_path.write_bytes(crypto.encrypt_bytes(raw))
        doc.file_path = str(enc_path.relative_to(settings.STORAGE_DIR))

        if expiry_date:
            from datetime import datetime, timedelta
            try:
                remind_at = datetime.strptime(expiry_date, "%Y-%m-%d") - timedelta(days=7)
                remind_at = remind_at.replace(hour=9, minute=0, second=0, microsecond=0)
                if remind_at < datetime.utcnow():
                    remind_at = datetime.utcnow() + timedelta(minutes=5)
            except ValueError:
                remind_at = datetime.utcnow() + timedelta(days=1)
            db.add(models.Reminder(
                person_id=person.id, document_id=doc.id, title=f"{title} expires",
                description=f"Renew/replace before {expiry_date}", remind_at=remind_at,
                repeat_rule=models.RepeatRule.none,
            ))

        db.commit()

    if redirect_to == "folder":
        return RedirectResponse(f"/admin/documents?person={person_id}&category={redirect_category}", status_code=302)
    return RedirectResponse(f"/admin?person={person_id}", status_code=302)


@router.get("/documents/{document_id}/download")
def documents_download(request: Request, document_id: str, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    doc = (
        db.query(models.Document).join(models.Person)
        .filter(models.Document.id == document_id, models.Person.user_id == vault_id(user)).first()
    )
    if not doc:
        return RedirectResponse("/admin", status_code=302)
    enc_path = settings.STORAGE_DIR / doc.file_path
    plain = crypto.decrypt_bytes(enc_path.read_bytes())
    return Response(
        content=plain, media_type=doc.file_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{doc.title}"'},
    )


@router.post("/documents/{document_id}/delete")
def documents_delete(
    request: Request, document_id: str,
    person_id: str = Form(...), category: str = Form(""),
    db: Session = Depends(get_db),
):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    doc = (
        db.query(models.Document).join(models.Person)
        .filter(models.Document.id == document_id, models.Person.user_id == vault_id(user)).first()
    )
    if doc:
        enc_path = settings.STORAGE_DIR / doc.file_path
        if enc_path.exists():
            enc_path.unlink()
        db.delete(doc)
        db.commit()
    if category:
        return RedirectResponse(f"/admin/documents?person={person_id}&category={category}", status_code=302)
    return RedirectResponse(f"/admin?person={person_id}", status_code=302)


# ---------- Reminders ----------
@router.get("/activity", response_class=HTMLResponse)
def activity_page(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)

    people = db.query(models.Person).filter(models.Person.user_id == vault_id(user)).all()
    active_person = people[0] if people else None

    entries = (
        db.query(models.AuditLog)
        .join(models.Document, models.AuditLog.document_id == models.Document.id, isouter=True)
        .join(models.Person, models.Document.person_id == models.Person.id, isouter=True)
        .filter((models.Person.user_id == vault_id(user)) | (models.AuditLog.document_id.is_(None)))
        .order_by(models.AuditLog.created_at.desc())
        .limit(200)
        .all()
    )
    doc_titles = {d.id: d.title for d in db.query(models.Document).join(models.Person).filter(models.Person.user_id == vault_id(user)).all()}

    share_links = (
        db.query(models.ShareLink)
        .filter(models.ShareLink.created_by == user.id)
        .order_by(models.ShareLink.created_at.desc())
        .all()
    )

    return templates.TemplateResponse("activity.html", {
        "request": request, "session_user": user, "active_nav": "activity",
        "people": people, "active_person": active_person,
        "active_person_id": active_person.id if active_person else None,
        "entries": entries, "doc_titles": doc_titles, "share_links": share_links,
    })


@router.post("/activity/share/{link_id}/revoke")
def revoke_share_link_admin(request: Request, link_id: str, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    link = db.query(models.ShareLink).filter(
        models.ShareLink.id == link_id, models.ShareLink.created_by == user.id
    ).first()
    if link:
        link.revoked = True
        db.commit()
    return RedirectResponse("/admin/activity", status_code=302)


@router.get("/shares", response_class=HTMLResponse)
def shares_page(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    people = db.query(models.Person).filter(models.Person.user_id == vault_id(user)).all()
    links = (
        db.query(models.ShareLink)
        .join(models.Document)
        .join(models.Person)
        .filter(models.Person.user_id == vault_id(user))
        .order_by(models.ShareLink.created_at.desc())
        .all()
    )
    items = []
    for link in links:
        accesses = sorted(link.accesses, key=lambda a: a.created_at or datetime.min, reverse=True)
        items.append({
            "link": link,
            "title": link.document.title if link.document else "—",
            "accesses": accesses,
            "downloads": sum(1 for a in accesses if a.action == "download"),
        })
    return templates.TemplateResponse("shares.html", {
        "request": request, "session_user": user, "active_nav": "shares",
        "people": people, "active_person": people[0] if people else None,
        "active_person_id": people[0].id if people else None,
        "items": items,
    })


@router.post("/shares/{link_id}/revoke")
def shares_revoke(request: Request, link_id: str, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    link = (
        db.query(models.ShareLink)
        .join(models.Document).join(models.Person)
        .filter(models.ShareLink.id == link_id, models.Person.user_id == vault_id(user))
        .first()
    )
    if link:
        link.revoked = True
        db.commit()
    return RedirectResponse("/admin/shares", status_code=302)


@router.get("/reminders", response_class=HTMLResponse)
def reminders_page(request: Request, person: Optional[str] = None, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)

    people = db.query(models.Person).filter(models.Person.user_id == vault_id(user)).all()
    active_person = next((p for p in people if p.id == person), None) or (people[0] if people else None)
    person_names = {p.id: p.name for p in people}

    reminders = (
        db.query(models.Reminder).join(models.Person)
        .filter(models.Person.user_id == vault_id(user))
        .order_by(models.Reminder.remind_at.asc()).all()
    )

    return templates.TemplateResponse("reminders.html", {
        "request": request, "session_user": user, "active_nav": "reminders",
        "people": people, "active_person": active_person, "active_person_id": active_person.id if active_person else None,
        "reminders": reminders, "person_names": person_names,
    })


@router.post("/reminders/add")
def reminders_add(
    request: Request,
    person_id: str = Form(...), title: str = Form(...), remind_at: str = Form(...),
    repeat_rule: str = Form("none"), description: str = Form(""),
    db: Session = Depends(get_db),
):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    person = db.query(models.Person).filter(models.Person.id == person_id, models.Person.user_id == vault_id(user)).first()
    if person:
        reminder = models.Reminder(
            person_id=person.id, title=title, description=description or None,
            remind_at=datetime.fromisoformat(remind_at), repeat_rule=models.RepeatRule(repeat_rule),
        )
        db.add(reminder)
        db.commit()
    return RedirectResponse(f"/admin/reminders?person={person_id}", status_code=302)


@router.post("/reminders/{reminder_id}/delete")
def reminders_delete(request: Request, reminder_id: str, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    r = (
        db.query(models.Reminder).join(models.Person)
        .filter(models.Reminder.id == reminder_id, models.Person.user_id == vault_id(user)).first()
    )
    person_id = r.person_id if r else None
    if r:
        db.delete(r)
        db.commit()
    return RedirectResponse(f"/admin/reminders?person={person_id}" if person_id else "/admin/reminders", status_code=302)


def _admin_person(request, db, person: Optional[str]):
    user = require_login(request, db)
    if not user:
        return None, None, None, None
    people = db.query(models.Person).filter(models.Person.user_id == vault_id(user)).all()
    active = next((p for p in people if p.id == person), None) or (people[0] if people else None)
    return user, people, active, (active.id if active else None)


@router.get("/care", response_class=HTMLResponse)
def care_page(request: Request, person: Optional[str] = None, db: Session = Depends(get_db)):
    user, people, active, pid = _admin_person(request, db, person)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    meds = vax = visits = claims = growth = uhids = timeline = []
    doctors = db.query(models.Doctor).filter(models.Doctor.user_id == vault_id(user)).all()
    if active:
        meds = db.query(models.Medicine).filter(models.Medicine.person_id == active.id).all()
        vax = db.query(models.VaccinationRecord).filter(models.VaccinationRecord.person_id == active.id).all()
        visits = db.query(models.Visit).filter(models.Visit.person_id == active.id).all()
        claims = db.query(models.Claim).filter(models.Claim.person_id == active.id).all()
        growth = db.query(models.GrowthReading).filter(models.GrowthReading.person_id == active.id).all()
        uhids = db.query(models.HospitalUhid).filter(models.HospitalUhid.person_id == active.id).all()
    ice_url = f"{request.base_url}ice/{active.ice_token}" if active and active.ice_token else None
    return templates.TemplateResponse("care.html", {
        "request": request, "session_user": user, "active_nav": "care",
        "people": people, "active_person": active, "active_person_id": pid,
        "meds": meds, "vax": vax, "visits": visits, "claims": claims, "growth": growth,
        "uhids": uhids, "doctors": doctors, "ice_url": ice_url,
    })


@router.post("/care/person")
def care_update_person(
    request: Request, person_id: str = Form(...),
    allergies: str = Form(""), conditions: str = Form(""),
    emergency_name: str = Form(""), emergency_phone: str = Form(""),
    abha_id: str = Form(""), ayushman_id: str = Form(""), blood_group: str = Form(""),
    db: Session = Depends(get_db),
):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    p = db.query(models.Person).filter(models.Person.id == person_id, models.Person.user_id == vault_id(user)).first()
    if p:
        p.allergies = allergies or None
        p.conditions = conditions or None
        p.emergency_name = emergency_name or None
        p.emergency_phone = emergency_phone or None
        p.abha_id = abha_id or None
        p.ayushman_id = ayushman_id or None
        p.blood_group = blood_group or p.blood_group
        if not p.ice_token:
            import secrets
            p.ice_token = secrets.token_urlsafe(18)
        db.commit()
    return RedirectResponse(f"/admin/care?person={person_id}", status_code=302)


@router.post("/care/medicine")
def care_add_med(request: Request, person_id: str = Form(...), name: str = Form(...), dose: str = Form(""), timing: str = Form(""), remaining: str = Form(""), refill_at: str = Form(""), db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    db.add(models.Medicine(person_id=person_id, name=name, dose=dose or None, timing=timing or None, remaining=int(remaining) if remaining.strip().isdigit() else None, refill_at=refill_at or None))
    db.commit()
    return RedirectResponse(f"/admin/care?person={person_id}", status_code=302)


@router.post("/care/vaccine")
def care_add_vax(request: Request, person_id: str = Form(...), vaccine_name: str = Form(...), given_on: str = Form(""), next_due: str = Form(""), db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    db.add(models.VaccinationRecord(person_id=person_id, vaccine_name=vaccine_name, given_on=given_on or None, next_due=next_due or None))
    db.commit()
    return RedirectResponse(f"/admin/care?person={person_id}", status_code=302)


@router.post("/care/visit")
def care_add_visit(request: Request, person_id: str = Form(...), hospital_name: str = Form(""), doctor_name: str = Form(""), visit_date: str = Form(""), reason: str = Form(""), db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    db.add(models.Visit(person_id=person_id, hospital_name=hospital_name or None, doctor_name=doctor_name or None, visit_date=visit_date or None, reason=reason or None))
    db.commit()
    return RedirectResponse(f"/admin/care?person={person_id}", status_code=302)


@router.post("/care/claim")
def care_add_claim(request: Request, person_id: str = Form(...), insurer: str = Form(""), amount: str = Form(""), status: str = Form("draft"), claim_number: str = Form(""), db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    db.add(models.Claim(person_id=person_id, insurer=insurer or None, amount=amount or None, status=status, claim_number=claim_number or None))
    db.commit()
    return RedirectResponse(f"/admin/care?person={person_id}", status_code=302)


@router.post("/care/growth")
def care_add_growth(request: Request, person_id: str = Form(...), measured_at: str = Form(...), height_cm: str = Form(""), weight_kg: str = Form(""), db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    db.add(models.GrowthReading(person_id=person_id, measured_at=measured_at, height_cm=height_cm or None, weight_kg=weight_kg or None))
    db.commit()
    return RedirectResponse(f"/admin/care?person={person_id}", status_code=302)


@router.post("/care/uhid")
def care_add_uhid(request: Request, person_id: str = Form(...), hospital_name: str = Form(...), uhid: str = Form(...), db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    db.add(models.HospitalUhid(person_id=person_id, hospital_name=hospital_name, uhid=uhid))
    db.commit()
    return RedirectResponse(f"/admin/care?person={person_id}", status_code=302)


@router.post("/care/doctor")
def care_add_doctor(request: Request, name: str = Form(...), specialty: str = Form(""), hospital_name: str = Form(""), phone: str = Form(""), person: str = Form(""), db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    db.add(models.Doctor(user_id=vault_id(user), name=name, specialty=specialty or None, hospital_name=hospital_name or None, phone=phone or None))
    db.commit()
    return RedirectResponse(f"/admin/care?person={person}" if person else "/admin/care", status_code=302)


@router.get("/storage", response_class=HTMLResponse)
def storage_page(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    people = db.query(models.Person).filter(models.Person.user_id == vault_id(user)).all()
    root = settings.STORAGE_DIR / vault_id(user)
    total = count = 0
    if root.exists():
        for p in root.rglob("*"):
            if p.is_file():
                total += p.stat().st_size
                count += 1
    from app.drive_backup import get_or_create, status_dict
    drive = status_dict(get_or_create(db, user))
    redirect_uri = str(request.base_url).rstrip("/") + "/admin/storage/google/callback"
    return templates.TemplateResponse("storage.html", {
        "request": request, "session_user": user, "active_nav": "storage",
        "people": people, "active_person": people[0] if people else None,
        "active_person_id": people[0].id if people else None,
        "bytes_used": total, "file_count": count,
        "backup_dir": str(settings.BACKUP_DIR) if settings.BACKUP_DIR else None,
        "drive": drive, "redirect_uri": redirect_uri,
        "ok": request.query_params.get("ok"), "err": request.query_params.get("err"),
    })


@router.post("/storage/snapshot")
def storage_snapshot(request: Request, db: Session = Depends(get_db)):
    from app.routers.backup import snapshot_to_disk
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    if settings.BACKUP_DIR:
        snapshot_to_disk(None, db, user)
    return RedirectResponse("/admin/storage", status_code=302)


def _drive_redirect_uri(request: Request) -> str:
    return str(request.base_url).rstrip("/") + "/admin/storage/google/callback"


@router.post("/storage/google")
def storage_google_save(
    request: Request,
    client_id: str = Form(""),
    client_secret: str = Form(""),
    password: str = Form(""),
    hour: str = Form("3"),
    keep_days: str = Form("14"),
    enabled: str = Form(""),
    db: Session = Depends(get_db),
):
    from app.drive_backup import get_or_create
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    row = get_or_create(db, user)
    if client_id.strip():
        row.client_id = client_id.strip()
    if client_secret.strip():
        row.client_secret_enc = crypto.encrypt_text(client_secret.strip())
    if password.strip():
        row.password_enc = crypto.encrypt_text(password.strip())
    row.hour = max(0, min(23, int(hour or 3)))
    row.keep_days = max(3, min(90, int(keep_days or 14)))
    row.enabled = bool(enabled) and bool(row.refresh_token_enc) and bool(row.password_enc)
    db.commit()
    return RedirectResponse("/admin/storage", status_code=302)


@router.get("/storage/google/connect")
def storage_google_connect(request: Request, db: Session = Depends(get_db)):
    import secrets
    from app.drive_backup import get_or_create
    from app import gdrive
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    row = get_or_create(db, user)
    if not row.client_id or not row.client_secret_enc:
        return RedirectResponse("/admin/storage?err=client", status_code=302)
    state = secrets.token_urlsafe(16)
    request.session["gdrive_oauth_state"] = state
    secret = crypto.decrypt_text(row.client_secret_enc) or ""
    url = gdrive.auth_url(row.client_id, _drive_redirect_uri(request), state)
    _ = secret
    return RedirectResponse(url, status_code=302)


@router.get("/storage/google/callback")
def storage_google_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    from app.drive_backup import get_or_create
    from app import gdrive
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    if error:
        return RedirectResponse("/admin/storage?err=denied", status_code=302)
    if not code or state != request.session.get("gdrive_oauth_state"):
        return RedirectResponse("/admin/storage?err=state", status_code=302)
    row = get_or_create(db, user)
    secret = crypto.decrypt_text(row.client_secret_enc) or ""
    try:
        tokens = gdrive.exchange_code(row.client_id or "", secret, code, _drive_redirect_uri(request))
        refresh = tokens.get("refresh_token")
        access = tokens.get("access_token")
        if not refresh:
            return RedirectResponse("/admin/storage?err=token", status_code=302)
        row.refresh_token_enc = crypto.encrypt_text(refresh)
        if access:
            row.connected_email = gdrive.user_email(access)
            row.folder_id = gdrive.ensure_folder(access, row.folder_id)
        db.commit()
    except Exception:
        return RedirectResponse("/admin/storage?err=token", status_code=302)
    request.session.pop("gdrive_oauth_state", None)
    return RedirectResponse("/admin/storage?ok=connected", status_code=302)


@router.post("/storage/google/run")
def storage_google_run(request: Request, db: Session = Depends(get_db)):
    from app.drive_backup import run_backup
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    try:
        run_backup(db, user)
        return RedirectResponse("/admin/storage?ok=backedup", status_code=302)
    except Exception:
        return RedirectResponse("/admin/storage?err=run", status_code=302)


@router.post("/storage/google/disconnect")
def storage_google_disconnect(request: Request, db: Session = Depends(get_db)):
    from app.drive_backup import get_or_create
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    row = get_or_create(db, user)
    row.refresh_token_enc = None
    row.folder_id = None
    row.connected_email = None
    row.enabled = False
    db.commit()
    return RedirectResponse("/admin/storage", status_code=302)


# ---------- Password Vault ----------
def _pw_ctx(request, user, active_nav, **extra):
    ctx = {
        "request": request, "session_user": user, "active_nav": active_nav,
        "active_module": "passwords", "people": [], "active_person_id": None,
    }
    ctx.update(extra)
    return ctx


@router.get("/passwords", response_class=HTMLResponse)
def passwords_page(
    request: Request,
    q: Optional[str] = None,
    item_type: Optional[str] = None,
    folder_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    from app.routers.vault import list_folders, list_items
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    folders = list_folders(db=db, current_user=user)
    items = list_items(q=q, item_type=item_type, folder_id=folder_id, favorite=False, db=db, current_user=user)
    return templates.TemplateResponse("passwords.html", _pw_ctx(
        request, user, "pw_vault", folders=folders, items=items,
        q=q or "", item_type=item_type or "", folder_id=folder_id or "",
    ))


@router.post("/passwords/folder")
def passwords_add_folder(request: Request, name: str = Form(...), db: Session = Depends(get_db)):
    from app.routers.vault import create_folder
    from app import schemas as sc
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    create_folder(sc.VaultFolderIn(name=name), db=db, current_user=user)
    return RedirectResponse("/admin/passwords", status_code=302)


@router.post("/passwords/add")
def passwords_add(
    request: Request,
    name: str = Form(...),
    item_type: str = Form("login"),
    username: str = Form(""),
    password: str = Form(""),
    uris: str = Form(""),
    totp_secret: str = Form(""),
    notes: str = Form(""),
    folder_id: str = Form(""),
    cardholder_name: str = Form(""),
    card_number: str = Form(""),
    card_brand: str = Form(""),
    card_exp_month: str = Form(""),
    card_exp_year: str = Form(""),
    card_cvv: str = Form(""),
    first_name: str = Form(""),
    last_name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    db: Session = Depends(get_db),
):
    from app.routers.vault import create_item
    from app import schemas as sc
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    uri_list = [u.strip() for u in uris.replace("\n", ",").split(",") if u.strip()]
    create_item(sc.VaultItemIn(
        name=name, item_type=item_type, username=username or None, password=password or None,
        uris=uri_list, totp_secret=totp_secret or None, notes=notes or None,
        folder_id=folder_id or None, cardholder_name=cardholder_name or None,
        card_number=card_number or None, card_brand=card_brand or None,
        card_exp_month=card_exp_month or None, card_exp_year=card_exp_year or None,
        card_cvv=card_cvv or None, first_name=first_name or None, last_name=last_name or None,
        email=email or None, phone=phone or None,
    ), db=db, current_user=user)
    return RedirectResponse("/admin/passwords", status_code=302)


@router.get("/passwords/generator", response_class=HTMLResponse)
def passwords_generator(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    return templates.TemplateResponse("password_generator.html", _pw_ctx(request, user, "pw_generator", result=None))


@router.post("/passwords/generator", response_class=HTMLResponse)
def passwords_generator_run(
    request: Request,
    kind: str = Form("password"),
    length: int = Form(16),
    word_count: int = Form(4),
    uppercase: Optional[str] = Form(None),
    lowercase: Optional[str] = Form(None),
    numbers: Optional[str] = Form(None),
    symbols: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    from app.routers.vault import generate_password
    from app import schemas as sc
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    result = generate_password(sc.VaultGenerateIn(
        kind=kind, length=length, word_count=word_count,
        uppercase=uppercase is not None, lowercase=lowercase is not None,
        numbers=numbers is not None, symbols=symbols is not None,
    ), current_user=user)
    return templates.TemplateResponse("password_generator.html", _pw_ctx(request, user, "pw_generator", result=result))


@router.get("/passwords/health", response_class=HTMLResponse)
def passwords_health_page(request: Request, db: Session = Depends(get_db)):
    from app.routers.vault import password_health
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    report = password_health(db=db, current_user=user)
    return templates.TemplateResponse("password_health.html", _pw_ctx(request, user, "pw_health", report=report))


@router.get("/passwords/sends", response_class=HTMLResponse)
def passwords_sends_page(request: Request, db: Session = Depends(get_db)):
    from app.routers.vault import list_sends, list_items
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    sends = list_sends(db=db, current_user=user)
    items = list_items(q=None, item_type="login", folder_id=None, favorite=False, db=db, current_user=user)
    return templates.TemplateResponse("password_sends.html", _pw_ctx(
        request, user, "pw_sends", sends=sends, items=items,
        public_base=str(request.base_url).rstrip("/"),
    ))


@router.post("/passwords/sends")
def passwords_send_create(
    request: Request,
    name: str = Form(...),
    send_type: str = Form("text"),
    text: str = Form(""),
    item_id: str = Form(""),
    pin: str = Form(""),
    expires_in_hours: int = Form(48),
    db: Session = Depends(get_db),
):
    from app.routers.vault import create_send
    from app import schemas as sc
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    create_send(sc.VaultSendCreate(
        name=name, send_type=send_type, text=text or None, item_id=item_id or None,
        pin=pin or None, expires_in_hours=expires_in_hours,
    ), db=db, current_user=user)
    return RedirectResponse("/admin/passwords/sends", status_code=302)


@router.post("/passwords/sends/{send_id}/revoke")
def passwords_send_revoke(send_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers.vault import revoke_send
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    revoke_send(send_id, db=db, current_user=user)
    return RedirectResponse("/admin/passwords/sends", status_code=302)


@router.get("/passwords/trash", response_class=HTMLResponse)
def passwords_trash_page(request: Request, db: Session = Depends(get_db)):
    from app.routers.vault import list_trash
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    items = list_trash(db=db, current_user=user)
    return templates.TemplateResponse("password_trash.html", _pw_ctx(request, user, "pw_trash", items=items))


@router.post("/passwords/trash/empty")
def passwords_trash_empty(request: Request, db: Session = Depends(get_db)):
    from app.routers.vault import empty_trash
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    empty_trash(db=db, current_user=user)
    return RedirectResponse("/admin/passwords/trash", status_code=302)


@router.get("/passwords/{item_id}", response_class=HTMLResponse)
def password_item_page(item_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers.vault import get_item, item_totp, item_history, list_folders
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    item = get_item(item_id, db=db, current_user=user)
    totp = None
    if item.has_totp:
        totp = item_totp(item_id, db=db, current_user=user)
    history = item_history(item_id, db=db, current_user=user)
    folders = list_folders(db=db, current_user=user)
    return templates.TemplateResponse("password_item.html", _pw_ctx(
        request, user, "pw_vault", item=item, totp=totp, history=history, folders=folders,
    ))


@router.post("/passwords/{item_id}")
def password_item_save(
    item_id: str,
    request: Request,
    name: str = Form(...),
    username: str = Form(""),
    password: str = Form(""),
    uris: str = Form(""),
    totp_secret: str = Form(""),
    notes: str = Form(""),
    folder_id: str = Form(""),
    favorite: Optional[str] = Form(None),
    cardholder_name: str = Form(""),
    card_number: str = Form(""),
    card_brand: str = Form(""),
    card_exp_month: str = Form(""),
    card_exp_year: str = Form(""),
    card_cvv: str = Form(""),
    first_name: str = Form(""),
    last_name: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    db: Session = Depends(get_db),
):
    from app.routers.vault import update_item
    from app import schemas as sc
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    uri_list = [u.strip() for u in uris.replace("\n", ",").split(",") if u.strip()]
    update_item(item_id, sc.VaultItemUpdate(
        name=name, username=username, password=password or None, uris=uri_list,
        totp_secret=totp_secret or None, notes=notes or None, folder_id=folder_id or None,
        favorite=favorite is not None, cardholder_name=cardholder_name or None,
        card_number=card_number or None, card_brand=card_brand or None,
        card_exp_month=card_exp_month or None, card_exp_year=card_exp_year or None,
        card_cvv=card_cvv or None, first_name=first_name or None, last_name=last_name or None,
        email=email or None, phone=phone or None,
    ), db=db, current_user=user)
    return RedirectResponse(f"/admin/passwords/{item_id}", status_code=302)


@router.post("/passwords/{item_id}/delete")
def password_item_delete(item_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers.vault import trash_item
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    trash_item(item_id, db=db, current_user=user)
    return RedirectResponse("/admin/passwords", status_code=302)


@router.post("/passwords/{item_id}/restore")
def password_item_restore(item_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers.vault import restore_item
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    restore_item(item_id, db=db, current_user=user)
    return RedirectResponse("/admin/passwords", status_code=302)


@router.post("/passwords/{item_id}/permanent")
def password_item_permanent(item_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers.vault import delete_item_forever
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    delete_item_forever(item_id, db=db, current_user=user)
    return RedirectResponse("/admin/passwords/trash", status_code=302)


# ---------- Money Manager ----------
def _fn_ctx(request, user, active_nav, **extra):
    ctx = {
        "request": request, "session_user": user, "active_nav": active_nav,
        "active_module": "finance", "people": [], "active_person_id": None,
    }
    ctx.update(extra)
    return ctx


def _fn_user(request, db):
    user = require_login(request, db)
    if not user:
        return None
    from app.routers.finance import ensure_defaults
    ensure_defaults(db, user)
    return user


@router.get("/finance", response_class=HTMLResponse)
def finance_trans(
    request: Request,
    month: Optional[str] = None,
    view: str = "daily",
    q: Optional[str] = None,
    db: Session = Depends(get_db),
):
    from app.routers.finance import month_ledger, inr
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    ym = month or datetime.utcnow().strftime("%Y-%m")
    ledger = month_ledger(db, user, ym, q=q, notes_only=(view == "note"))
    return templates.TemplateResponse("finance_trans.html", _fn_ctx(
        request, user, "fn_trans", ledger=ledger, view=view, q=q or "", inr=inr,
    ))


@router.get("/finance/add", response_class=HTMLResponse)
def finance_add_page(
    request: Request,
    txn_type: str = "expense",
    account_id: str = "",
    db: Session = Depends(get_db),
):
    from app.routers import finance as fn
    from app.routers.finance import inr
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    accounts = fn.list_accounts(db=db, current_user=user)
    categories = fn.list_categories(db=db, current_user=user)
    if txn_type not in ("income", "expense", "transfer"):
        txn_type = "expense"
    cats_json = json.dumps([
        {
            "id": str(c.id), "name": c.name, "kind": c.kind,
            "parent_id": str(c.parent_id) if c.parent_id else None,
            "account_id": str(c.account_id) if c.account_id else None,
        }
        for c in categories
    ])
    accts_json = json.dumps([
        {"id": str(a.id), "name": a.name, "account_type": a.account_type} for a in accounts
    ])
    return templates.TemplateResponse("finance_add.html", _fn_ctx(
        request, user, "fn_trans", accounts=accounts, categories=categories,
        txn_type=txn_type, today=datetime.utcnow().strftime("%Y-%m-%d"),
        now=datetime.utcnow().strftime("%H:%M"), inr=inr,
        prefill_account_id=account_id or None, cats_json=cats_json, accts_json=accts_json,
    ))


@router.post("/finance/add")
def finance_add(
    request: Request,
    txn_type: str = Form("expense"),
    account_id: str = Form(...),
    to_account_id: str = Form(""),
    category_id: str = Form(""),
    amount: str = Form(...),
    txn_date: str = Form(...),
    txn_time: str = Form(""),
    payee: str = Form(""),
    notes: str = Form(""),
    description: str = Form(""),
    payment_method: str = Form(""),
    frequency: str = Form(""),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    from app.routers.finance import create_transaction, save_txn_image
    from app import schemas as sc
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    txn = create_transaction(sc.FinanceTxnIn(
        account_id=account_id, to_account_id=to_account_id or None,
        category_id=category_id or None, txn_type=txn_type, amount=float(amount or 0),
        txn_date=txn_date, txn_time=txn_time or None, payee=payee or None,
        notes=notes or None, description=description or None,
        payment_method=payment_method or None, frequency=frequency or None,
    ), db=db, current_user=user)
    if image and image.filename:
        raw = image.file.read()
        if raw:
            save_txn_image(db, user, txn.id, raw, image.content_type)
    return RedirectResponse("/admin/finance", status_code=302)


@router.get("/finance/transactions/{txn_id}/image")
def finance_txn_image(txn_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers.finance import get_transaction_image
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    return get_transaction_image(txn_id, db=db, current_user=user)


@router.post("/finance/transactions/{txn_id}/delete")
def finance_delete_txn(txn_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers.finance import delete_transaction
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    delete_transaction(txn_id, db=db, current_user=user)
    return RedirectResponse("/admin/finance", status_code=302)


@router.get("/finance/stats", response_class=HTMLResponse)
def finance_stats(
    request: Request,
    month: Optional[str] = None,
    kind: str = "expense",
    db: Session = Depends(get_db),
):
    from app.routers import finance as fn
    from app.routers.finance import inr, _shift_month
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    ym = month or datetime.utcnow().strftime("%Y-%m")
    report = fn.reports(year_month=ym, kind=kind, db=db, current_user=user)
    circ = 2 * 3.14159265 * 40
    offset = 0.0
    slices = []
    for row in report["rows"]:
        length = circ * (row["pct"] / 100)
        slices.append({**row, "dash": f"{length:.2f} {circ:.2f}", "offset": f"{-offset:.2f}"})
        offset += length
    label = datetime.strptime(ym + "-01", "%Y-%m-%d").strftime("%b %Y")
    return templates.TemplateResponse("finance_stats.html", _fn_ctx(
        request, user, "fn_stats", report=report, slices=slices, inr=inr,
        year_month=ym, kind=kind, label=label, prev=_shift_month(ym, -1), next=_shift_month(ym, 1),
    ))


@router.get("/finance/accounts", response_class=HTMLResponse)
def finance_accounts(request: Request, db: Session = Depends(get_db)):
    from app.routers import finance as fn
    from app.routers.finance import inr
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    accounts = fn.list_accounts(db=db, current_user=user)
    summary = fn.summary(db=db, current_user=user)
    groups = {}
    labels = {"cash": "Cash", "bank": "Accounts", "credit_card": "Card", "loan": "Loan", "wallet": "Wallet", "investment": "Investment", "other": "Other"}
    for a in accounts:
        groups.setdefault(a.account_type, []).append(a)
    return templates.TemplateResponse("finance_accounts.html", _fn_ctx(
        request, user, "fn_accounts", accounts=accounts, groups=groups, labels=labels,
        summary=summary, inr=inr,
    ))


@router.post("/finance/accounts/add")
def finance_account_add(
    request: Request,
    name: str = Form(...),
    account_type: str = Form("cash"),
    opening_balance: str = Form("0"),
    credit_limit: str = Form(""),
    db: Session = Depends(get_db),
):
    from app.routers.finance import create_account
    from app import schemas as sc
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    create_account(sc.FinanceAccountIn(
        name=name, account_type=account_type,
        opening_balance=float(opening_balance or 0),
        credit_limit=float(credit_limit) if credit_limit.strip() else None,
    ), db=db, current_user=user)
    return RedirectResponse("/admin/finance/accounts", status_code=302)


@router.post("/finance/accounts/{account_id}/delete")
def finance_account_delete(account_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers.finance import delete_account
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    delete_account(account_id, db=db, current_user=user)
    return RedirectResponse("/admin/finance/accounts", status_code=302)


@router.get("/finance/accounts/{account_id}", response_class=HTMLResponse)
def finance_account_detail(
    account_id: str,
    request: Request,
    month: Optional[str] = None,
    db: Session = Depends(get_db),
):
    from app.routers import finance as fn
    from app.routers.finance import inr, _shift_month
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    accounts = fn.list_accounts(db=db, current_user=user)
    account = next((a for a in accounts if a.id == account_id), None)
    if not account:
        return RedirectResponse("/admin/finance/accounts", status_code=302)
    ym = month or datetime.utcnow().strftime("%Y-%m")
    try:
        y, m = [int(p) for p in ym.split("-")]
        datetime(y, m, 1)
    except ValueError:
        y, m = datetime.utcnow().year, datetime.utcnow().month
        ym = f"{y:04d}-{m:02d}"
    last = calendar.monthrange(y, m)[1]
    txns = fn.list_transactions(year_month=ym, account_id=account_id, db=db, current_user=user)
    days: dict[str, dict] = {}
    deposit = withdrawal = 0.0
    for t in txns:
        incoming = t.txn_type == "income" or (t.txn_type == "transfer" and t.to_account_id == account_id)
        if incoming:
            deposit += t.amount
        else:
            withdrawal += t.amount
        bucket = days.setdefault(t.txn_date, {"date": t.txn_date, "income": 0.0, "expense": 0.0, "txns": []})
        if incoming:
            bucket["income"] += t.amount
        else:
            bucket["expense"] += t.amount
        bucket["txns"].append({"txn": t, "incoming": incoming})
    day_list = []
    for date in sorted(days.keys(), reverse=True):
        bucket = days[date]
        try:
            dt = datetime.strptime(date, "%Y-%m-%d")
            bucket["daynum"] = dt.strftime("%d")
            bucket["weekday"] = dt.strftime("%a")
            bucket["month"] = dt.strftime("%m.%Y")
        except ValueError:
            bucket["daynum"], bucket["weekday"], bucket["month"] = date, "", ""
        day_list.append(bucket)
    return templates.TemplateResponse("finance_account_detail.html", _fn_ctx(
        request, user, "fn_accounts", account=account, inr=inr, days=day_list,
        year_month=ym, label=datetime(y, m, 1).strftime("%b %Y"),
        prev=_shift_month(ym, -1), next=_shift_month(ym, 1),
        prev_year=f"{y - 1:04d}-{m:02d}", next_year=f"{y + 1:04d}-{m:02d}",
        range_start=f"01.{m:02d}.{str(y)[2:]}", range_end=f"{last:02d}.{m:02d}.{str(y)[2:]}",
        deposit=deposit, withdrawal=withdrawal, total=deposit - withdrawal,
    ))


@router.get("/finance/more", response_class=HTMLResponse)
def finance_more(request: Request, db: Session = Depends(get_db)):
    from app.routers import finance as fn
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    summary = fn.summary(db=db, current_user=user)
    return templates.TemplateResponse("finance_more.html", _fn_ctx(request, user, "fn_more", summary=summary))


@router.get("/finance/ai", response_class=HTMLResponse)
def finance_ai_page(request: Request, db: Session = Depends(get_db)):
    from app.routers import finance as fn
    from app.routers.finance import inr
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    return templates.TemplateResponse("finance_ai.html", _fn_ctx(
        request, user, "fn_more",
        keys=fn.list_ai_keys(db=db, current_user=user),
        messages=fn.list_messages(status="pending", db=db, current_user=user),
        rules=fn.list_rules(db=db, current_user=user),
        categories=fn.list_categories(db=db, current_user=user),
        accounts=fn.list_accounts(db=db, current_user=user),
        inr=inr,
    ))


@router.post("/finance/ai/keys")
def finance_ai_add(
    request: Request,
    name: str = Form(...),
    kind: str = Form(...),
    api_key: str = Form(""),
    model: str = Form(""),
    base_url: str = Form(""),
    is_default: str = Form(""),
    db: Session = Depends(get_db),
):
    from app.routers.finance import create_ai_key
    from app import schemas as sc
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    create_ai_key(sc.FinanceAiKeyIn(
        name=name, kind=kind, api_key=api_key or None, model=model or None,
        base_url=base_url or None, is_default=bool(is_default),
    ), db=db, current_user=user)
    return RedirectResponse("/admin/finance/ai", status_code=302)


@router.post("/finance/ai/keys/{key_id}/delete")
def finance_ai_delete(key_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers.finance import delete_ai_key
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    delete_ai_key(key_id, db=db, current_user=user)
    return RedirectResponse("/admin/finance/ai", status_code=302)


@router.post("/finance/ai/ingest")
def finance_ai_ingest(
    request: Request,
    text: str = Form(...),
    account_id: str = Form(""),
    auto_accept: str = Form(""),
    db: Session = Depends(get_db),
):
    from app.routers.finance import ingest_messages
    from app import schemas as sc
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    ingest_messages(sc.FinanceMessageIn(
        text=text, account_id=account_id or None, auto_accept=bool(auto_accept),
    ), db=db, current_user=user)
    return RedirectResponse("/admin/finance/ai", status_code=302)


@router.post("/finance/ai/messages/{message_id}/accept")
def finance_msg_accept(message_id: str, request: Request, account_id: str = Form(""), db: Session = Depends(get_db)):
    from app.routers.finance import accept_message
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    accept_message(message_id, account_id=account_id or None, db=db, current_user=user)
    return RedirectResponse("/admin/finance/ai", status_code=302)


@router.post("/finance/ai/messages/{message_id}/ignore")
def finance_msg_ignore(message_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers.finance import ignore_message
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    ignore_message(message_id, db=db, current_user=user)
    return RedirectResponse("/admin/finance/ai", status_code=302)


@router.post("/finance/ai/rules")
def finance_rule_add(
    request: Request,
    match_text: str = Form(...),
    category_id: str = Form(""),
    txn_type: str = Form(""),
    payee: str = Form(""),
    db: Session = Depends(get_db),
):
    from app.routers.finance import create_rule
    from app import schemas as sc
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    create_rule(sc.FinanceRuleIn(
        match_text=match_text, category_id=category_id or None,
        txn_type=txn_type or None, payee=payee or None,
    ), db=db, current_user=user)
    return RedirectResponse("/admin/finance/ai", status_code=302)


@router.post("/finance/ai/rules/{rule_id}/delete")
def finance_rule_delete(rule_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers.finance import delete_rule
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    delete_rule(rule_id, db=db, current_user=user)
    return RedirectResponse("/admin/finance/ai", status_code=302)


@router.get("/finance/categories", response_class=HTMLResponse)
def finance_categories(request: Request, db: Session = Depends(get_db)):
    from app.routers import finance as fn
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    return templates.TemplateResponse("finance_categories.html", _fn_ctx(
        request, user, "fn_more",
        categories=fn.list_categories(db=db, current_user=user),
        accounts=fn.list_accounts(db=db, current_user=user),
    ))


@router.post("/finance/categories")
def finance_category_add(
    request: Request,
    name: str = Form(...),
    kind: str = Form("expense"),
    account_id: str = Form(""),
    parent_id: str = Form(""),
    db: Session = Depends(get_db),
):
    from app.routers.finance import create_category
    from app import schemas as sc
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    create_category(
        sc.FinanceCategoryIn(
            name=name, kind=kind, account_id=account_id or None, parent_id=parent_id or None,
        ),
        db=db, current_user=user,
    )
    return RedirectResponse("/admin/finance/categories", status_code=302)


@router.post("/finance/categories/{category_id}/delete")
def finance_category_delete(category_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers.finance import delete_category
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    delete_category(category_id, db=db, current_user=user)
    return RedirectResponse("/admin/finance/categories", status_code=302)


@router.get("/finance/plan", response_class=HTMLResponse)
def finance_plan(request: Request, month: Optional[str] = None, db: Session = Depends(get_db)):
    from app.routers import finance as fn
    from app.routers.finance import inr
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    ym = month or datetime.utcnow().strftime("%Y-%m")
    return templates.TemplateResponse("finance_plan.html", _fn_ctx(
        request, user, "fn_more", year_month=ym, inr=inr,
        budgets=fn.list_budgets(year_month=ym, db=db, current_user=user),
        recurring=fn.list_recurring(db=db, current_user=user),
        categories=fn.list_categories(db=db, current_user=user),
        accounts=fn.list_accounts(db=db, current_user=user),
    ))


@router.post("/finance/plan/budget")
def finance_budget_add(
    request: Request, category_id: str = Form(...), year_month: str = Form(...), amount: str = Form(...),
    db: Session = Depends(get_db),
):
    from app.routers.finance import create_budget
    from app import schemas as sc
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    create_budget(sc.FinanceBudgetIn(category_id=category_id, year_month=year_month, amount=float(amount or 0)), db=db, current_user=user)
    return RedirectResponse(f"/admin/finance/plan?month={year_month}", status_code=302)


@router.post("/finance/plan/recurring")
def finance_recurring_add(
    request: Request, account_id: str = Form(...), category_id: str = Form(""), txn_type: str = Form("expense"),
    amount: str = Form(...), payee: str = Form(""), frequency: str = Form("monthly"), next_due: str = Form(...),
    db: Session = Depends(get_db),
):
    from app.routers.finance import create_recurring
    from app import schemas as sc
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    create_recurring(sc.FinanceRecurringIn(
        account_id=account_id, category_id=category_id or None, txn_type=txn_type,
        amount=float(amount or 0), payee=payee or None, frequency=frequency, next_due=next_due,
    ), db=db, current_user=user)
    return RedirectResponse("/admin/finance/plan", status_code=302)


@router.post("/finance/plan/recurring/{rid}/pay")
def finance_recurring_pay(rid: str, request: Request, db: Session = Depends(get_db)):
    from app.routers.finance import pay_recurring
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    pay_recurring(rid, db=db, current_user=user)
    return RedirectResponse("/admin/finance/plan", status_code=302)


@router.get("/finance/recurring", response_class=HTMLResponse)
def finance_recurring_page(
    request: Request,
    status: str = "pending",
    kind: str = "",
    db: Session = Depends(get_db),
):
    from app.routers import finance as fn
    from app.routers.finance import inr
    from app.emi import EMI_KINDS
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    st = status if status in ("pending", "completed", "overdue") else None
    rows = fn.list_emis(status=st, kind=kind or None, db=db, current_user=user)
    return templates.TemplateResponse("finance_recurring.html", _fn_ctx(
        request, user, "fn_more", emis=rows, inr=inr, status=status or "pending",
        kind=kind, kinds=EMI_KINDS,
        accounts=fn.list_accounts(db=db, current_user=user),
        today=datetime.utcnow().strftime("%Y-%m-%d"),
        end_default=(datetime.utcnow().replace(year=datetime.utcnow().year + 1)).strftime("%Y-%m-%d"),
    ))


@router.post("/finance/recurring")
def finance_recurring_create(
    request: Request,
    name: str = Form(...),
    kind: str = Form("emi"),
    account_id: str = Form(...),
    amount: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    day_of_month: str = Form(""),
    notify_days: str = Form("2"),
    auto_post: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    from app.routers.finance import create_emi
    from app import schemas as sc
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    day = int(day_of_month) if day_of_month.strip().isdigit() else None
    create_emi(sc.FinanceEmiIn(
        name=name, kind=kind, account_id=account_id, amount=float(amount or 0),
        start_date=start_date, end_date=end_date, day_of_month=day,
        notify_days=int(notify_days or 2), auto_post=bool(auto_post),
        notes=notes or None,
    ), db=db, current_user=user)
    return RedirectResponse("/admin/finance/recurring", status_code=302)


@router.post("/finance/recurring/{emi_id}/post")
def finance_recurring_post(emi_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers.finance import post_emi_now
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    try:
        post_emi_now(emi_id, db=db, current_user=user)
    except Exception:
        pass
    return RedirectResponse("/admin/finance/recurring", status_code=302)


@router.post("/finance/recurring/{emi_id}/pause")
def finance_recurring_pause(emi_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers.finance import pause_emi
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    pause_emi(emi_id, db=db, current_user=user)
    return RedirectResponse("/admin/finance/recurring", status_code=302)


@router.post("/finance/recurring/{emi_id}/delete")
def finance_recurring_delete(emi_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers.finance import delete_emi
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    delete_emi(emi_id, db=db, current_user=user)
    return RedirectResponse("/admin/finance/recurring", status_code=302)
