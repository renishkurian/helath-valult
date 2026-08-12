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
        "file_size": doc.file_size or 0, "created_at": doc.created_at,
        "notes": crypto.decrypt_text(doc.notes_enc),
    }


# ---------- Login / logout ----------
@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/admin", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
def login_submit(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user or not security.verify_password(password, user.hashed_password):
        return templates.TemplateResponse("login.html", {"request": request, "error": "Incorrect email or password"})
    request.session["user_id"] = user.id
    return RedirectResponse("/admin", status_code=302)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/admin/login", status_code=302)


# ---------- Dashboard ----------
@router.get("", response_class=HTMLResponse)
def dashboard(request: Request, person: Optional[str] = None, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)

    people = db.query(models.Person).filter(models.Person.user_id == user.id).all()
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
    people = db.query(models.Person).filter(models.Person.user_id == user.id).all()
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
        user_id=user.id, name=name, relation=models.Relation(relation),
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
    p = db.query(models.Person).filter(models.Person.id == person_id, models.Person.user_id == user.id).first()
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
    person = db.query(models.Person).filter(models.Person.id == person_id, models.Person.user_id == user.id).first()
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
        .filter(models.HospitalCard.id == card_id, models.Person.user_id == user.id).first()
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

    active_person = db.query(models.Person).filter(models.Person.id == person, models.Person.user_id == user.id).first()
    if not active_person:
        return RedirectResponse("/admin", status_code=302)

    q = db.query(models.Document).filter(models.Document.person_id == active_person.id)
    if category:
        q = q.filter(models.Document.category == models.DocCategory(category))
    docs = [doc_out(d) for d in q.order_by(models.Document.created_at.desc()).all()]

    people = db.query(models.Person).filter(models.Person.user_id == user.id).all()
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
    redirect_to: str = Form("dashboard"), redirect_category: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)

    person = db.query(models.Person).filter(models.Person.id == person_id, models.Person.user_id == user.id).first()
    if person:
        raw = await file.read()
        doc = models.Document(
            person_id=person.id, category=models.DocCategory(category), title=title,
            hospital_name=hospital_name or None, doc_date=doc_date or None,
            file_type=file.content_type, file_size=len(raw),
            notes_enc=crypto.encrypt_text(notes or None), file_path="",
        )
        db.add(doc)
        db.flush()

        person_dir = settings.STORAGE_DIR / user.id / person.id
        person_dir.mkdir(parents=True, exist_ok=True)
        enc_path = person_dir / f"{doc.id}.enc"
        enc_path.write_bytes(crypto.encrypt_bytes(raw))
        doc.file_path = str(enc_path.relative_to(settings.STORAGE_DIR))
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
        .filter(models.Document.id == document_id, models.Person.user_id == user.id).first()
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
        .filter(models.Document.id == document_id, models.Person.user_id == user.id).first()
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
@router.get("/reminders", response_class=HTMLResponse)
def reminders_page(request: Request, person: Optional[str] = None, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)

    people = db.query(models.Person).filter(models.Person.user_id == user.id).all()
    active_person = next((p for p in people if p.id == person), None) or (people[0] if people else None)
    person_names = {p.id: p.name for p in people}

    reminders = (
        db.query(models.Reminder).join(models.Person)
        .filter(models.Person.user_id == user.id)
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
    person = db.query(models.Person).filter(models.Person.id == person_id, models.Person.user_id == user.id).first()
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
        .filter(models.Reminder.id == reminder_id, models.Person.user_id == user.id).first()
    )
    person_id = r.person_id if r else None
    if r:
        db.delete(r)
        db.commit()
    return RedirectResponse(f"/admin/reminders?person={person_id}" if person_id else "/admin/reminders", status_code=302)
