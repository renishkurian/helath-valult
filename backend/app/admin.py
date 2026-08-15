import calendar
import json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, Response, JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, security, crypto
from app.config import settings
from app.deps import vault_id, is_viewer
from app.templating import setup_templates

router = APIRouter(prefix="/admin", tags=["admin"])
templates = setup_templates()


def _pager_urls(path: str, pager: dict, **query) -> tuple[str | None, str | None]:
    from urllib.parse import urlencode

    def _url(page: int) -> str:
        params = {k: v for k, v in query.items() if v not in (None, "")}
        params["page"] = page
        return f"{path}?{urlencode(params)}"

    prev_url = _url(pager["page"] - 1) if pager.get("has_prev") else None
    next_url = _url(pager["page"] + 1) if pager.get("has_next") else None
    return prev_url, next_url


# ---------- Session auth helpers ----------
def get_session_user(request: Request, db: Session = Depends(get_db)) -> Optional[models.User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        return None
    from app.totp import is_blocked
    if is_blocked(user):
        request.session.clear()
        return None
    from app.login_guard import touch_last_seen
    touch_last_seen(user)
    return user


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
def _login_ctx(request: Request, error=None):
    from app.login_guard import recaptcha_public_key
    return {
        "request": request,
        "error": error,
        "recaptcha_site_key": recaptcha_public_key(),
    }


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse("/admin/modules", status_code=302)
    if request.session.get("totp_pending"):
        return RedirectResponse("/admin/login/2fa", status_code=302)
    if request.session.get("qr_email") or request.session.get("qr_payload"):
        return RedirectResponse("/admin/login/qr", status_code=302)
    return templates.TemplateResponse("login.html", _login_ctx(request))


@router.post("/login", response_class=HTMLResponse)
async def login_submit(request: Request, db: Session = Depends(get_db)):
    from app.login_guard import authenticate
    from app import totp as totp_util
    form = await request.form()
    email = str(form.get("email") or "")
    password = str(form.get("password") or "")
    token = str(form.get("g-recaptcha-response") or "")
    user, err = authenticate(
        db, request, email=email, password=password,
        recaptcha_token=token, check_recaptcha=True,
    )
    if err or not user:
        return templates.TemplateResponse("login.html", _login_ctx(request, err or "Incorrect email or password"), status_code=401)
    request.session.pop("totp_pending", None)
    request.session.pop("login_challenge_id", None)
    if totp_util.needs_step_up(user):
        from app.login_challenge import create_challenge, notify_devices
        from app.login_guard import client_ip, client_ua
        request.session.pop("user_id", None)
        request.session["totp_pending"] = security.create_totp_pending_token(user.id)
        challenge = create_challenge(db, user, client_ip(request), client_ua(request))
        request.session["login_challenge_id"] = challenge.id
        notify_devices(db, user, challenge)
        return RedirectResponse("/admin/login/2fa", status_code=302)
    request.session["user_id"] = user.id
    return RedirectResponse("/admin/modules", status_code=302)


def _clear_qr_session(request: Request) -> None:
    request.session.pop("qr_email", None)
    request.session.pop("qr_started", None)
    request.session.pop("qr_payload", None)
    if not request.session.get("totp_pending"):
        request.session.pop("login_challenge_id", None)


def _qr_ctx(request: Request, error=None, **extra):
    from app.login_guard import recaptcha_public_key
    ctx = {
        "request": request,
        "error": error,
        "email": request.session.get("qr_email") or extra.get("email") or "",
        "waiting": bool(request.session.get("qr_payload")),
        "qr_image": extra.pop("qr_image", None),
        "recaptcha_site_key": recaptcha_public_key(),
    }
    ctx.update(extra)
    return ctx


def _pending_qr(request: Request, db: Session):
    from app.login_challenge import CHALLENGE_MINUTES, get_challenge
    from app.totp import is_blocked
    if request.session.get("user_id"):
        return None, None, RedirectResponse("/admin/modules", status_code=302)
    if request.session.get("totp_pending"):
        return None, None, RedirectResponse("/admin/login/2fa", status_code=302)
    payload = request.session.get("qr_payload")
    email = request.session.get("qr_email")
    if not payload and not email:
        return None, None, None
    challenge = get_challenge(db, request.session.get("login_challenge_id"))
    if challenge and challenge.status == "approved":
        user = db.query(models.User).filter(models.User.id == challenge.user_id).first()
        if user and not is_blocked(user):
            _finish_web_login(request, db, user, reason="app_ok")
            _clear_qr_session(request)
            return None, None, RedirectResponse("/admin/modules", status_code=302)
        _clear_qr_session(request)
        return None, None, RedirectResponse("/admin/login", status_code=302)
    if challenge and challenge.status == "denied":
        _clear_qr_session(request)
        return None, None, templates.TemplateResponse(
            "login.html", _login_ctx(request, "That sign-in was denied on your phone."), status_code=401,
        )
    if challenge and challenge.status == "expired":
        _clear_qr_session(request)
        return None, None, templates.TemplateResponse(
            "login.html", _login_ctx(request, "The QR code timed out. Start again."), status_code=401,
        )
    started = int(request.session.get("qr_started") or 0)
    if started and (datetime.utcnow() - datetime.utcfromtimestamp(started)).total_seconds() > CHALLENGE_MINUTES * 60:
        _clear_qr_session(request)
        return None, None, templates.TemplateResponse(
            "login.html", _login_ctx(request, "The QR code timed out. Start again."), status_code=401,
        )
    return challenge, payload, None


def _two_factor_ctx(request: Request, user: models.User, error=None, **extra):
    from app import totp as totp_util
    ctx = {
        "request": request,
        "error": error,
        "email": user.email,
        "has_totp": totp_util.is_enabled(user),
        "app_approve": totp_util.app_approve_on(user),
        "pushed": extra.pop("pushed", 0),
        "challenge": extra.pop("challenge", None),
    }
    ctx.update(extra)
    return ctx


def _finish_web_login(request: Request, db: Session, user: models.User, reason: str = "ok"):
    from app.login_challenge import consume
    from app.login_guard import client_ip, client_ua, log_attempt, touch_last_seen
    consume(db, request.session.get("login_challenge_id"))
    if reason != "app_ok":
        log_attempt(
            db, email=user.email, ip=client_ip(request),
            user_agent=client_ua(request), success=True, reason=reason,
        )
    touch_last_seen(user)
    request.session.pop("totp_pending", None)
    request.session.pop("login_challenge_id", None)
    request.session["user_id"] = user.id


def _pending_2fa_user(request: Request, db: Session):
    from app import totp as totp_util
    from app.login_challenge import get_challenge
    if request.session.get("user_id"):
        return None, None, RedirectResponse("/admin/modules", status_code=302)
    user = totp_util.pending_user(db, request.session.get("totp_pending"))
    if not user or totp_util.is_blocked(user) or not totp_util.needs_step_up(user):
        request.session.pop("totp_pending", None)
        request.session.pop("login_challenge_id", None)
        return None, None, RedirectResponse("/admin/login", status_code=302)
    challenge = get_challenge(db, request.session.get("login_challenge_id"))
    if challenge and challenge.user_id != user.id:
        challenge = None
    if challenge and challenge.status == "approved":
        _finish_web_login(request, db, user, reason="app_ok")
        return None, None, RedirectResponse("/admin/modules", status_code=302)
    if challenge and challenge.status == "denied":
        request.session.pop("totp_pending", None)
        request.session.pop("login_challenge_id", None)
        return None, None, templates.TemplateResponse(
            "login.html", _login_ctx(request, "That sign-in was denied on your phone."), status_code=401,
        )
    if challenge and challenge.status == "expired":
        request.session.pop("totp_pending", None)
        request.session.pop("login_challenge_id", None)
        return None, None, templates.TemplateResponse(
            "login.html", _login_ctx(request, "The phone approval timed out. Sign in again."), status_code=401,
        )
    return user, challenge, None


@router.get("/login/2fa", response_class=HTMLResponse)
def login_2fa_form(request: Request, db: Session = Depends(get_db)):
    user, challenge, early = _pending_2fa_user(request, db)
    if early:
        return early
    return templates.TemplateResponse("login_2fa.html", _two_factor_ctx(request, user, challenge=challenge))


@router.get("/login/2fa/status")
def login_2fa_status(request: Request, db: Session = Depends(get_db)):
    user, challenge, early = _pending_2fa_user(request, db)
    if early:
        if isinstance(early, RedirectResponse) and early.headers.get("location", "").endswith("/admin/modules"):
            return {"status": "approved", "redirect": "/admin/modules"}
        if isinstance(early, RedirectResponse):
            return {"status": "expired", "redirect": "/admin/login"}
        return {"status": "denied", "redirect": "/admin/login"}
    from app import totp as totp_util
    return {"status": "pending", "has_totp": totp_util.is_enabled(user)}


@router.post("/login/2fa/resend")
def login_2fa_resend(request: Request, db: Session = Depends(get_db)):
    from app.login_challenge import notify_devices
    user, challenge, early = _pending_2fa_user(request, db)
    if early:
        return early
    pushed = notify_devices(db, user, challenge) if challenge else 0
    return templates.TemplateResponse(
        "login_2fa.html",
        _two_factor_ctx(request, user, challenge=challenge, pushed=pushed),
    )


@router.post("/login/2fa", response_class=HTMLResponse)
async def login_2fa_submit(request: Request, db: Session = Depends(get_db)):
    from app import totp as totp_util
    from app.login_guard import client_ip, client_ua, log_attempt, rate_limited
    user, challenge, early = _pending_2fa_user(request, db)
    if early:
        return early
    form = await request.form()
    code = str(form.get("code") or "")
    ip, ua = client_ip(request), client_ua(request)
    blocked, retry = rate_limited(db, user.email, ip)
    if blocked:
        log_attempt(db, email=user.email, ip=ip, user_agent=ua, success=False, reason="rate_limited")
        return templates.TemplateResponse(
            "login_2fa.html",
            _two_factor_ctx(request, user, f"Too many failed attempts. Try again in {retry} minute(s).", challenge=challenge),
            status_code=401,
        )
    if not totp_util.is_enabled(user):
        return templates.TemplateResponse(
            "login_2fa.html",
            _two_factor_ctx(request, user, "Approve this sign-in from the Vault app on your phone.", challenge=challenge),
            status_code=400,
        )
    if not totp_util.verify_code(user, code):
        log_attempt(db, email=user.email, ip=ip, user_agent=ua, success=False, reason="totp_bad")
        return templates.TemplateResponse(
            "login_2fa.html",
            _two_factor_ctx(request, user, "That code is not valid. Try the next one from your app.", challenge=challenge),
            status_code=401,
        )
    _finish_web_login(request, db, user, reason="ok")
    return RedirectResponse("/admin/modules", status_code=302)


@router.get("/login/qr", response_class=HTMLResponse)
def login_qr_form(request: Request, db: Session = Depends(get_db)):
    from app import totp as totp_util
    challenge, payload, early = _pending_qr(request, db)
    if early:
        return early
    if payload:
        return templates.TemplateResponse(
            "login_qr.html",
            _qr_ctx(request, waiting=True, qr_image=totp_util.qr_data_uri(payload)),
        )
    return templates.TemplateResponse("login_qr.html", _qr_ctx(request))


@router.post("/login/qr", response_class=HTMLResponse)
async def login_qr_submit(request: Request, db: Session = Depends(get_db)):
    import secrets
    from app import totp as totp_util
    from app.login_challenge import KIND_QR, create_challenge, qr_payload
    from app.login_guard import begin_qr_login, client_ip, client_ua
    if request.session.get("user_id"):
        return RedirectResponse("/admin/modules", status_code=302)
    form = await request.form()
    email = str(form.get("email") or "")
    token = str(form.get("g-recaptcha-response") or "")
    user, err = begin_qr_login(db, request, email=email, recaptcha_token=token)
    if err:
        return templates.TemplateResponse("login_qr.html", _qr_ctx(request, err, email=email), status_code=401)
    request.session.pop("totp_pending", None)
    request.session.pop("user_id", None)
    request.session["qr_email"] = (email or "").strip().lower()
    request.session["qr_started"] = int(datetime.utcnow().timestamp())
    if user:
        challenge = create_challenge(db, user, client_ip(request), client_ua(request), kind=KIND_QR)
        request.session["login_challenge_id"] = challenge.id
        payload = qr_payload(challenge.id)
    else:
        request.session.pop("login_challenge_id", None)
        payload = qr_payload(secrets.token_hex(16))
    request.session["qr_payload"] = payload
    return templates.TemplateResponse(
        "login_qr.html",
        _qr_ctx(request, waiting=True, qr_image=totp_util.qr_data_uri(payload)),
    )


@router.get("/login/qr/status")
def login_qr_status(request: Request, db: Session = Depends(get_db)):
    challenge, payload, early = _pending_qr(request, db)
    if early:
        if isinstance(early, RedirectResponse) and early.headers.get("location", "").endswith("/admin/modules"):
            return {"status": "approved", "redirect": "/admin/modules"}
        if isinstance(early, RedirectResponse):
            return {"status": "expired", "redirect": "/admin/login"}
        return {"status": "denied", "redirect": "/admin/login"}
    if not payload:
        return {"status": "expired", "redirect": "/admin/login/qr"}
    return {"status": "pending"}


@router.get("/login/qr/cancel")
def login_qr_cancel(request: Request):
    _clear_qr_session(request)
    return RedirectResponse("/admin/login", status_code=302)


def _security_ctx(request: Request, user: models.User, **extra):
    from app import totp as totp_util
    from app import crypto
    ctx = {
        "request": request, "session_user": user,
        "active_nav": "security", "active_module": "picker",
        "people": [], "active_person_id": None,
        "totp_on": totp_util.is_enabled(user),
        "app_approve": totp_util.app_approve_on(user),
        "setup_secret": None, "setup_url": None, "setup_qr": None,
    }
    if (not ctx["totp_on"]) and user.totp_secret_enc:
        secret = crypto.decrypt_text(user.totp_secret_enc)
        if secret:
            ctx["setup_secret"] = secret
            ctx["setup_url"] = totp_util.otpauth_url(user.email, secret)
            ctx["setup_qr"] = totp_util.qr_data_uri(ctx["setup_url"])
    ctx.update(extra)
    return ctx


@router.get("/security", response_class=HTMLResponse)
def security_page(request: Request, db: Session = Depends(get_db), saved: str = "", error: str = ""):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    return templates.TemplateResponse("security.html", _security_ctx(
        request, user, saved=saved or None, error=error or None,
    ))


@router.post("/security/setup", response_class=HTMLResponse)
def security_setup(request: Request, db: Session = Depends(get_db)):
    from app import totp as totp_util
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    if totp_util.is_enabled(user):
        return RedirectResponse("/admin/security", status_code=302)
    totp_util.begin_setup(user)
    db.commit()
    return RedirectResponse("/admin/security", status_code=302)


@router.post("/security/enable", response_class=HTMLResponse)
async def security_enable(request: Request, db: Session = Depends(get_db)):
    from app import totp as totp_util
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    form = await request.form()
    if not totp_util.verify_code(user, str(form.get("code") or "")):
        return templates.TemplateResponse("security.html", _security_ctx(
            request, user, error="That authenticator code is not valid. Wait for a new one and try again.",
        ), status_code=400)
    totp_util.enable(user)
    db.commit()
    return RedirectResponse("/admin/security?saved=on", status_code=302)


@router.post("/security/disable", response_class=HTMLResponse)
async def security_disable(request: Request, db: Session = Depends(get_db)):
    from app import totp as totp_util
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    form = await request.form()
    if totp_util.is_enabled(user) and not totp_util.verify_code(user, str(form.get("code") or "")):
        return templates.TemplateResponse("security.html", _security_ctx(
            request, user, error="Enter a current authenticator code to turn 2FA off.",
        ), status_code=400)
    totp_util.disable(user)
    db.commit()
    return RedirectResponse("/admin/security?saved=off", status_code=302)


@router.post("/security/cancel", response_class=HTMLResponse)
def security_cancel(request: Request, db: Session = Depends(get_db)):
    from app import totp as totp_util
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    if not totp_util.is_enabled(user):
        totp_util.disable(user)
        db.commit()
    return RedirectResponse("/admin/security", status_code=302)


@router.post("/security/app-approve", response_class=HTMLResponse)
async def security_app_approve(request: Request, db: Session = Depends(get_db)):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    form = await request.form()
    user.app_approve = str(form.get("enabled") or "") in ("1", "on", "true", "yes")
    db.commit()
    return RedirectResponse("/admin/security?saved=app-on" if user.app_approve else "/admin/security?saved=app-off", status_code=302)


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
    hospital_folders, insurance_count, unassigned_folders = [], 0, {}
    hospital_scoped_cats = [c.value for c in models.DocCategory if models.category_requires_hospital(c)]
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

        # Group hospital-scoped docs under matching hospital cards (by name).
        card_keys = {(c["hospital_name"] or "").strip().lower(): c for c in cards}
        per_hospital = {k: {cat: 0 for cat in hospital_scoped_cats} for k in card_keys}
        unassigned_folders = {cat: 0 for cat in hospital_scoped_cats}
        insurance_count = 0
        for d in documents:
            cat = d["category"]
            if cat == models.DocCategory.insurance.value:
                insurance_count += 1
                continue
            if cat not in unassigned_folders:
                continue
            key = (d.get("hospital_name") or "").strip().lower()
            if key and key in per_hospital:
                per_hospital[key][cat] += 1
            else:
                unassigned_folders[cat] += 1
        hospital_folders = [
            {"card": card, "counts": per_hospital[(card["hospital_name"] or "").strip().lower()]}
            for card in cards
        ]
        if not any(unassigned_folders.values()):
            unassigned_folders = {}

    return templates.TemplateResponse("dashboard.html", {
        "request": request, "session_user": user, "active_nav": "dashboard",
        "people": people, "active_person": active_person, "active_person_id": active_person.id if active_person else None,
        "cards": cards, "folder_counts": folder_counts, "recent_documents": recent_documents,
        "expiring_cards": expiring_cards,
        "hospital_folders": hospital_folders,
        "hospital_scoped_cats": hospital_scoped_cats,
        "insurance_count": insurance_count,
        "unassigned_folders": unassigned_folders,
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
def documents_page(
    request: Request,
    person: str,
    category: Optional[str] = None,
    hospital: Optional[str] = None,
    db: Session = Depends(get_db),
):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)

    active_person = db.query(models.Person).filter(models.Person.id == person, models.Person.user_id == vault_id(user)).first()
    if not active_person:
        return RedirectResponse("/admin", status_code=302)

    q = db.query(models.Document).filter(models.Document.person_id == active_person.id)
    if category:
        q = q.filter(models.Document.category == models.DocCategory(category))
    if hospital:
        q = q.filter(models.Document.hospital_name.ilike(hospital))
    docs = [doc_out(d) for d in q.order_by(models.Document.created_at.desc()).all()]

    card_rows = db.query(models.HospitalCard).filter(models.HospitalCard.person_id == active_person.id).all()
    hospitals = [c.hospital_name for c in card_rows]

    people = db.query(models.Person).filter(models.Person.user_id == vault_id(user)).all()
    return templates.TemplateResponse("documents.html", {
        "request": request, "session_user": user, "active_nav": "dashboard",
        "people": people, "active_person": active_person, "active_person_id": active_person.id,
        "documents": docs, "category": category, "hospital": hospital, "hospitals": hospitals,
        "hospital_scoped_cats": [c.value for c in models.DocCategory if models.category_requires_hospital(c)],
    })


@router.post("/documents/add")
async def documents_add(
    request: Request,
    person_id: str = Form(...), category: str = Form(...), title: str = Form(...),
    hospital_name: str = Form(""), doc_date: str = Form(""), notes: str = Form(""),
    expiry_date: str = Form(""), tags: str = Form(""),
    redirect_to: str = Form("dashboard"), redirect_category: str = Form(""),
    redirect_hospital: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)

    person = db.query(models.Person).filter(models.Person.id == person_id, models.Person.user_id == vault_id(user)).first()
    if person:
        cat = models.DocCategory(category)
        hosp = (hospital_name or "").strip() or None
        if models.category_requires_hospital(cat) and not hosp:
            return RedirectResponse(f"/admin?person={person_id}", status_code=302)
        if cat == models.DocCategory.insurance:
            hosp = None

        raw = await file.read()
        doc = models.Document(
            person_id=person.id, category=cat, title=title,
            hospital_name=hosp, doc_date=doc_date or None,
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
        qs = f"/admin/documents?person={person_id}"
        if redirect_category:
            qs += f"&category={redirect_category}"
        if redirect_hospital:
            from urllib.parse import quote
            qs += f"&hospital={quote(redirect_hospital)}"
        return RedirectResponse(qs, status_code=302)
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
    drive = status_dict(get_or_create(db, user), db)
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
    from app.drive_backup import get_or_create, oauth_creds, oauth_ready
    from app import gdrive
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    row = get_or_create(db, user)
    if not oauth_ready(db, row):
        return RedirectResponse("/admin/storage?err=client", status_code=302)
    client_id, _secret = oauth_creds(db, row)
    state = secrets.token_urlsafe(16)
    request.session["gdrive_oauth_state"] = state
    url = gdrive.auth_url(client_id, _drive_redirect_uri(request), state)
    return RedirectResponse(url, status_code=302)


@router.get("/storage/google/callback")
def storage_google_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    from app.drive_backup import get_or_create, oauth_creds, oauth_ready
    from app import gdrive
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    if error:
        return RedirectResponse("/admin/storage?err=denied", status_code=302)
    if not code or state != request.session.get("gdrive_oauth_state"):
        return RedirectResponse("/admin/storage?err=state", status_code=302)
    row = get_or_create(db, user)
    if not oauth_ready(db, row):
        return RedirectResponse("/admin/storage?err=client", status_code=302)
    client_id, secret = oauth_creds(db, row)
    try:
        tokens = gdrive.exchange_code(client_id, secret, code, _drive_redirect_uri(request))
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
    from app.routers.finance import inr
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    summary = fn.summary(db=db, current_user=user)
    return templates.TemplateResponse("finance_more.html", _fn_ctx(
        request, user, "fn_more", summary=summary, inr=inr,
    ))


@router.get("/finance/ai", response_class=HTMLResponse)
def finance_ai_page(request: Request, db: Session = Depends(get_db)):
    from app import ai_providers as ap
    from app.routers import finance as fn
    from app.routers.finance import inr
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    return templates.TemplateResponse("finance_ai.html", _fn_ctx(
        request, user, "fn_more",
        messages=fn.list_messages(status="pending", db=db, current_user=user),
        rules=fn.list_rules(db=db, current_user=user),
        categories=fn.list_categories(db=db, current_user=user),
        accounts=fn.list_accounts(db=db, current_user=user),
        ai_summary=ap.status_summary(db, user),
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
    """Compat: old form posts redirect into the shared AI module."""
    from app import ai_providers as ap
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    ap.create_provider(
        db, user,
        name=name, kind=kind, api_key=api_key or None, model=model or None,
        base_url=base_url or None, is_default=bool(is_default),
    )
    return RedirectResponse("/admin/ai/providers?ok=saved", status_code=302)


@router.post("/finance/ai/keys/{key_id}/delete")
def finance_ai_delete(key_id: str, request: Request, db: Session = Depends(get_db)):
    from app import ai_providers as ap
    user = _fn_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    ap.delete_provider(db, user, key_id)
    return RedirectResponse("/admin/ai/providers", status_code=302)


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


# ---------- Document Vault ----------
def _lk_ctx(request, user, active_nav, **extra):
    ctx = {
        "request": request, "session_user": user, "active_nav": active_nav,
        "active_module": "locker", "people": [], "active_person_id": None,
    }
    ctx.update(extra)
    return ctx


def _lk_user(request, db):
    return require_login(request, db)


@router.get("/locker", response_class=HTMLResponse)
def locker_home(
    request: Request,
    doc_type: str = "",
    q: str = "",
    expiring: str = "",
    db: Session = Depends(get_db),
):
    from app.routers import locker as lk
    user = _lk_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    summary = lk.locker_summary(db=db, current_user=user)
    items = lk.list_items(
        doc_type=doc_type or None, q=q or None, expiring=bool(expiring),
        db=db, current_user=user,
    )
    return templates.TemplateResponse("locker.html", _lk_ctx(
        request, user, "lk_expiring" if expiring else "lk_home",
        summary=summary, items=items,
        doc_type=doc_type, q=q, expiring=bool(expiring), types=lk.LOCKER_TYPES,
    ))


@router.get("/locker/add", response_class=HTMLResponse)
def locker_add_page(
    request: Request,
    doc_type: str = "other",
    db: Session = Depends(get_db),
):
    from app.routers import locker as lk
    user = _lk_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    return templates.TemplateResponse("locker_add.html", _lk_ctx(
        request, user, "lk_add", types=lk.LOCKER_TYPES, prefill_type=doc_type or "other",
    ))


@router.post("/locker/add")
async def locker_add(
    request: Request,
    title: str = Form(...),
    doc_type: str = Form("other"),
    custom_type: str = Form(""),
    holder_name: str = Form(""),
    issuer: str = Form(""),
    id_number: str = Form(""),
    issued_on: str = Form(""),
    expiry_date: str = Form(""),
    tags: str = Form(""),
    notes: str = Form(""),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    from app.routers import locker as lk
    user = _lk_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    await lk.create_item(
        title=title, doc_type=doc_type, custom_type=custom_type or None,
        holder_name=holder_name or None, issuer=issuer or None,
        id_number=id_number or None, issued_on=issued_on or None,
        expiry_date=expiry_date or None, tags=tags or None, notes=notes or None,
        files=files, db=db, current_user=user,
    )
    return RedirectResponse("/admin/locker", status_code=302)


@router.get("/locker/{item_id}", response_class=HTMLResponse)
def locker_item_page(item_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import locker as lk
    user = _lk_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    item = lk.get_item(item_id, db=db, current_user=user)
    files = lk.list_files(item_id, db=db, current_user=user)
    return templates.TemplateResponse("locker_item.html", _lk_ctx(
        request, user, "lk_home", item=item, files=files, types=lk.LOCKER_TYPES,
    ))


@router.post("/locker/{item_id}")
def locker_item_update(
    item_id: str,
    request: Request,
    title: str = Form(...),
    doc_type: str = Form("other"),
    custom_type: str = Form(""),
    holder_name: str = Form(""),
    issuer: str = Form(""),
    id_number: str = Form(""),
    issued_on: str = Form(""),
    expiry_date: str = Form(""),
    tags: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    from app.routers import locker as lk
    from app import schemas as sc
    user = _lk_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    lk.update_item(item_id, sc.LockerItemUpdate(
        title=title, doc_type=doc_type, custom_type=custom_type or None,
        holder_name=holder_name or None, issuer=issuer or None,
        id_number=id_number or None, issued_on=issued_on or None,
        expiry_date=expiry_date or None, tags=tags or None, notes=notes or None,
    ), db=db, current_user=user)
    return RedirectResponse(f"/admin/locker/{item_id}", status_code=302)


@router.get("/locker/{item_id}/download")
def locker_download(item_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import locker as lk
    user = _lk_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    return lk.download_item(item_id, db=db, current_user=user)


@router.get("/locker/{item_id}/files/{file_id}/download")
def locker_file_download(item_id: str, file_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import locker as lk
    user = _lk_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    return lk.download_file(item_id, file_id, db=db, current_user=user)


@router.post("/locker/{item_id}/delete")
def locker_delete(item_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import locker as lk
    user = _lk_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    lk.delete_item(item_id, db=db, current_user=user)
    return RedirectResponse("/admin/locker", status_code=302)


# ---------- URL Vault ----------
def _url_ctx(request, user, active_nav, **extra):
    ctx = {
        "request": request, "session_user": user, "active_nav": active_nav,
        "active_module": "urls", "people": [], "active_person_id": None,
    }
    ctx.update(extra)
    return ctx


def _url_user(request, db):
    return require_login(request, db)


@router.get("/urls", response_class=HTMLResponse)
def urls_home(
    request: Request,
    q: str = "",
    category_id: str = "",
    tag_id: str = "",
    favorite: str = "",
    db: Session = Depends(get_db),
):
    from app.routers import urls as uv
    user = _url_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    summary = uv.urls_summary(db=db, current_user=user)
    items = uv.list_items(
        q=q or None, category_id=category_id or None, tag_id=tag_id or None,
        favorite=bool(favorite), db=db, current_user=user,
    )
    nav = "url_fav" if favorite else "url_home"
    return templates.TemplateResponse("urls.html", _url_ctx(
        request, user, nav, summary=summary, items=items,
        q=q, category_id=category_id, tag_id=tag_id, favorite=bool(favorite),
    ))


@router.get("/urls/add", response_class=HTMLResponse)
def urls_add_page(
    request: Request,
    category_id: str = "",
    db: Session = Depends(get_db),
):
    from app.routers import urls as uv
    user = _url_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    summary = uv.urls_summary(db=db, current_user=user)
    return templates.TemplateResponse("url_add.html", _url_ctx(
        request, user, "url_add",
        categories=summary.categories, tags=summary.tags,
        prefill_category=category_id,
    ))


@router.post("/urls/add")
async def urls_add(request: Request, db: Session = Depends(get_db)):
    from app.routers import urls as uv
    from app import schemas as sc
    user = _url_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    form = await request.form()
    tag_ids = [t for t in form.getlist("tag_ids") if t]
    uv.create_item(sc.UrlItemIn(
        url=str(form.get("url") or ""),
        title=str(form.get("title") or "") or None,
        category_id=str(form.get("category_id") or "") or None,
        tag_ids=tag_ids,
        notes=str(form.get("notes") or "") or None,
        favorite=bool(form.get("favorite")),
        fetch_preview=True,
    ), db=db, current_user=user)
    return RedirectResponse("/admin/urls", status_code=302)


@router.get("/urls/manage", response_class=HTMLResponse)
def urls_manage_page(request: Request, db: Session = Depends(get_db)):
    from app.routers import urls as uv
    user = _url_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    summary = uv.urls_summary(db=db, current_user=user)
    return templates.TemplateResponse("urls_manage.html", _url_ctx(
        request, user, "url_manage",
        categories=summary.categories, tags=summary.tags,
    ))


@router.post("/urls/categories")
async def urls_category_add(request: Request, db: Session = Depends(get_db)):
    from app.routers import urls as uv
    from app import schemas as sc
    user = _url_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    form = await request.form()
    uv.create_category(sc.UrlCategoryIn(
        name=str(form.get("name") or ""),
        color=str(form.get("color") or "") or None,
    ), db=db, current_user=user)
    return RedirectResponse("/admin/urls/manage", status_code=302)


@router.post("/urls/categories/{category_id}")
async def urls_category_update(category_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import urls as uv
    from app import schemas as sc
    user = _url_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    form = await request.form()
    uv.update_category(category_id, sc.UrlCategoryIn(
        name=str(form.get("name") or ""),
        color=str(form.get("color") or "") or None,
    ), db=db, current_user=user)
    return RedirectResponse("/admin/urls/manage", status_code=302)


@router.post("/urls/categories/{category_id}/delete")
def urls_category_delete(category_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import urls as uv
    user = _url_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    uv.delete_category(category_id, db=db, current_user=user)
    return RedirectResponse("/admin/urls/manage", status_code=302)


@router.post("/urls/tags")
async def urls_tag_add(request: Request, db: Session = Depends(get_db)):
    from app.routers import urls as uv
    from app import schemas as sc
    user = _url_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    form = await request.form()
    uv.create_tag(sc.UrlTagIn(
        name=str(form.get("name") or ""),
        color=str(form.get("color") or "") or None,
    ), db=db, current_user=user)
    return RedirectResponse("/admin/urls/manage", status_code=302)


@router.post("/urls/tags/{tag_id}")
async def urls_tag_update(tag_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import urls as uv
    from app import schemas as sc
    user = _url_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    form = await request.form()
    uv.update_tag(tag_id, sc.UrlTagIn(
        name=str(form.get("name") or ""),
        color=str(form.get("color") or "") or None,
    ), db=db, current_user=user)
    return RedirectResponse("/admin/urls/manage", status_code=302)


@router.post("/urls/tags/{tag_id}/delete")
def urls_tag_delete(tag_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import urls as uv
    user = _url_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    uv.delete_tag(tag_id, db=db, current_user=user)
    return RedirectResponse("/admin/urls/manage", status_code=302)


@router.get("/urls/{item_id}", response_class=HTMLResponse)
def urls_item_page(item_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import urls as uv
    user = _url_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    item = uv.get_item(item_id, db=db, current_user=user)
    summary = uv.urls_summary(db=db, current_user=user)
    shares = uv.list_shares(item_id=item_id, db=db, current_user=user)
    return templates.TemplateResponse("url_item.html", _url_ctx(
        request, user, "url_home", item=item,
        categories=summary.categories, tags=summary.tags, shares=shares,
        selected_tag_ids={t.id for t in item.tags},
    ))


@router.post("/urls/{item_id}")
async def urls_item_update(item_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import urls as uv
    from app import schemas as sc
    user = _url_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    form = await request.form()
    tag_ids = [t for t in form.getlist("tag_ids") if t]
    uv.update_item(item_id, sc.UrlItemUpdate(
        url=str(form.get("url") or "") or None,
        title=str(form.get("title") or "") or None,
        category_id=str(form.get("category_id") or "") or None,
        tag_ids=tag_ids,
        notes=str(form.get("notes") or "") or None,
        favorite=bool(form.get("favorite")),
        fetch_preview=bool(form.get("fetch_preview")),
    ), db=db, current_user=user)
    return RedirectResponse(f"/admin/urls/{item_id}", status_code=302)


@router.post("/urls/{item_id}/preview")
def urls_item_preview(item_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import urls as uv
    user = _url_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    uv.refresh_preview(item_id, db=db, current_user=user)
    return RedirectResponse(f"/admin/urls/{item_id}", status_code=302)


@router.post("/urls/{item_id}/favorite")
def urls_item_favorite(item_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import urls as uv
    user = _url_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    uv.toggle_favorite(item_id, db=db, current_user=user)
    return RedirectResponse(f"/admin/urls/{item_id}", status_code=302)


@router.post("/urls/{item_id}/share")
def urls_item_share(
    item_id: str,
    request: Request,
    expires_in_hours: int = Form(168),
    db: Session = Depends(get_db),
):
    from app.routers import urls as uv
    from app import schemas as sc
    user = _url_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    uv.create_share(item_id, sc.UrlShareCreate(expires_in_hours=expires_in_hours), db=db, current_user=user)
    return RedirectResponse(f"/admin/urls/{item_id}", status_code=302)


@router.post("/urls/shares/{share_id}/revoke")
def urls_share_revoke(share_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import urls as uv
    user = _url_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    uv.revoke_share(share_id, db=db, current_user=user)
    referer = request.headers.get("referer") or "/admin/urls"
    return RedirectResponse(referer, status_code=302)


@router.post("/urls/{item_id}/delete")
def urls_item_delete(item_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import urls as uv
    user = _url_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    uv.delete_item(item_id, db=db, current_user=user)
    return RedirectResponse("/admin/urls", status_code=302)


# ---------- Shared AI providers ----------
def _ai_ctx(request, user, active_nav, **extra):
    ctx = {
        "request": request, "session_user": user, "active_nav": active_nav,
        "active_module": "ai", "people": [], "active_person_id": None,
    }
    ctx.update(extra)
    return ctx


@router.get("/ai", response_class=HTMLResponse)
def ai_home(request: Request, db: Session = Depends(get_db)):
    from app import ai_chat, ai_providers as ap
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    summary = ap.status_summary(db, user)
    boot = {
        "hasProvider": bool(summary.get("has_default")),
        "providerName": summary.get("default_name"),
        "providerKind": summary.get("default_kind"),
        "hints": ai_chat.suggestion_hints(db, user),
    }
    return templates.TemplateResponse("ai_ask.html", _ai_ctx(
        request, user, "ai_ask",
        summary=summary,
        boot=json.dumps(boot).replace("<", "\\u003c"),
    ))


@router.get("/ai/ask/threads")
def ai_ask_threads(request: Request, db: Session = Depends(get_db)):
    from app import ai_chat
    user = require_login(request, db)
    if not user:
        return JSONResponse({"detail": "Not signed in"}, status_code=401)
    return ai_chat.list_threads(db, user)


@router.get("/ai/ask/threads/{thread_id}")
def ai_ask_thread(thread_id: str, request: Request, db: Session = Depends(get_db)):
    from app import ai_chat
    user = require_login(request, db)
    if not user:
        return JSONResponse({"detail": "Not signed in"}, status_code=401)
    detail = ai_chat.thread_detail(db, user, thread_id)
    if not detail:
        return JSONResponse({"detail": "Chat not found"}, status_code=404)
    return detail


@router.post("/ai/ask/threads/{thread_id}/delete")
def ai_ask_thread_delete(thread_id: str, request: Request, db: Session = Depends(get_db)):
    from app import ai_chat
    user = require_login(request, db)
    if not user:
        return JSONResponse({"detail": "Not signed in"}, status_code=401)
    if not ai_chat.delete_thread(db, user, thread_id):
        return JSONResponse({"detail": "Chat not found"}, status_code=404)
    return {"ok": True}


@router.post("/ai/ask/send")
async def ai_ask_send(request: Request, db: Session = Depends(get_db)):
    from app import ai_chat
    user = require_login(request, db)
    if not user:
        return JSONResponse({"detail": "Not signed in"}, status_code=401)
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"detail": "Invalid JSON"}, status_code=400)
    message = (body.get("message") or "").strip()
    thread_id = body.get("thread_id") or None
    try:
        return ai_chat.ask(db, user, message, thread_id)
    except LookupError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    except ValueError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)


@router.post("/ai/ask/test")
def ai_ask_test_connection(request: Request, db: Session = Depends(get_db)):
    """Session-auth ping of the default Ask AI provider."""
    from app import ai_providers as ap
    user = require_login(request, db)
    if not user:
        return JSONResponse({"detail": "Not signed in"}, status_code=401)
    try:
        return ap.test_default_connection(db, user)
    except LookupError as exc:
        return JSONResponse({"detail": str(exc)}, status_code=400)
    except ValueError as exc:
        return JSONResponse({"detail": f"Connection failed: {exc}"}, status_code=400)
    except Exception as exc:
        return JSONResponse({"detail": f"Connection failed: {exc}"}, status_code=400)


@router.post("/ai/providers/test-default")
def ai_providers_test_default(request: Request, db: Session = Depends(get_db)):
    from app import ai_providers as ap
    from urllib.parse import quote
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    try:
        result = ap.test_default_connection(db, user)
        label = result.get("name") or "default"
        sample = f"{label}: {result.get('sample') or 'ok'}"
        return RedirectResponse(
            f"/admin/ai/providers?ok=tested&sample={quote(sample[:160])}",
            status_code=302,
        )
    except Exception as exc:
        return RedirectResponse(
            f"/admin/ai/providers?err={quote(str(exc)[:200])}",
            status_code=302,
        )


@router.get("/ai/providers", response_class=HTMLResponse)
def ai_providers_page(request: Request, db: Session = Depends(get_db)):
    from app import ai_providers as ap
    from app.routers import ai as ai_api
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    providers = ai_api.list_providers(db=db, current_user=user)
    return templates.TemplateResponse("ai.html", _ai_ctx(
        request, user, "ai_providers",
        providers=providers,
        summary=ap.status_summary(db, user),
    ))


@router.get("/ai/logs", response_class=HTMLResponse)
def ai_logs_page(
    request: Request,
    client: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
):
    from app import ai_usage
    from app.paging import paginate
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    client_key = (client or "").strip() or None
    if client_key and client_key not in ai_usage.CLIENT_LABELS:
        client_key = None
    total = ai_usage.count_logs(db, user, client=client_key)
    pager = paginate(page=page, per_page=50, total=total)
    rows = ai_usage.list_logs(
        db, user, limit=pager["per_page"], offset=pager["offset"], client=client_key,
    )
    logs = [ai_usage.log_out(r) for r in rows]
    stats = ai_usage.summary(db, user, days=30)
    pager_prev, pager_next = _pager_urls("/admin/ai/logs", pager, client=client_key)
    return templates.TemplateResponse("ai_logs.html", _ai_ctx(
        request, user, "ai_logs",
        logs=logs,
        stats=stats,
        client_filter=client_key or "",
        client_labels=ai_usage.CLIENT_LABELS,
        pager=pager,
        pager_prev=pager_prev,
        pager_next=pager_next,
    ))


@router.post("/ai/providers")
def ai_provider_add(
    request: Request,
    name: str = Form(...),
    kind: str = Form(...),
    api_key: str = Form(""),
    model: str = Form(""),
    base_url: str = Form(""),
    is_default: str = Form(""),
    db: Session = Depends(get_db),
):
    from app import ai_providers as ap
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    ap.create_provider(
        db, user,
        name=name, kind=kind, api_key=api_key or None, model=model or None,
        base_url=base_url or None, is_default=bool(is_default),
    )
    return RedirectResponse("/admin/ai/providers?ok=saved", status_code=302)


@router.post("/ai/providers/{provider_id}/delete")
def ai_provider_delete(provider_id: str, request: Request, db: Session = Depends(get_db)):
    from app import ai_providers as ap
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    ap.delete_provider(db, user, provider_id)
    return RedirectResponse("/admin/ai/providers", status_code=302)


@router.post("/ai/providers/{provider_id}/test")
def ai_provider_test(provider_id: str, request: Request, db: Session = Depends(get_db)):
    from app import ai_providers as ap
    from urllib.parse import quote
    user = require_login(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    try:
        sample = ap.test_provider_row(db, user, provider_id)
        return RedirectResponse(f"/admin/ai/providers?ok=tested&sample={quote(sample[:120])}", status_code=302)
    except Exception as exc:
        return RedirectResponse(f"/admin/ai/providers?err={quote(str(exc)[:160])}", status_code=302)


# ---------- Expense Analyser ----------
def _ea_ctx(request, user, active_nav, **extra):
    ctx = {
        "request": request, "session_user": user, "active_nav": active_nav,
        "active_module": "expense", "people": [], "active_person_id": None,
    }
    ctx.update(extra)
    return ctx


def _ea_user(request, db):
    return require_login(request, db)


def _ea_redirect_uri(request: Request) -> str:
    return str(request.base_url).rstrip("/") + "/admin/expense-analyser/google/callback"


@router.get("/expense-analyser", response_class=HTMLResponse)
def expense_analyser_home(
    request: Request,
    status: str = "",
    page: int = 1,
    db: Session = Depends(get_db),
):
    from app import expense_analyser as ea
    from app.paging import paginate
    from app.routers.finance import ensure_defaults, inr, list_accounts
    user = _ea_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    ensure_defaults(db, user)
    st = ea.status_dict(db, user)
    filter_status = status if status in ("pending", "missed", "matched", "posted", "ignored", "corrected") else ""
    open_statuses = ("pending", "missed", "matched", "corrected")
    if filter_status:
        total = ea.count_items(db, user, status=filter_status)
        pager = paginate(page=page, per_page=25, total=total)
        items = ea.list_items(
            db, user, status=filter_status,
            limit=pager["per_page"], offset=pager["offset"],
        )
    else:
        total = ea.count_items(db, user, statuses=open_statuses)
        pager = paginate(page=page, per_page=25, total=total)
        items = ea.list_items(
            db, user, statuses=open_statuses,
            limit=pager["per_page"], offset=pager["offset"],
        )
    accounts = list_accounts(db=db, current_user=user)
    cat_rows = (
        db.query(models.FinanceCategory)
        .filter(models.FinanceCategory.user_id == vault_id(user))
        .order_by(models.FinanceCategory.kind, models.FinanceCategory.name)
        .all()
    )
    ea_cats = [
        {
            "id": c.id,
            "name": c.name,
            "parent_id": c.parent_id or "",
            "kind": c.kind,
        }
        for c in cat_rows
    ]
    cat_picks: dict[str, dict[str, str]] = {}
    for item in items:
        kind = "income" if item.direction == "credit" else "expense"
        parent_id, sub_id = ea.match_category_ids(cat_rows, item.suggested_category, kind)
        cat_picks[item.id] = {"parent": parent_id, "sub": sub_id, "kind": kind}
    pager_prev, pager_next = _pager_urls(
        "/admin/expense-analyser", pager, status=filter_status or None,
    )
    return templates.TemplateResponse("expense_analyser.html", _ea_ctx(
        request, user, "ea_inbox",
        status=st, items=items, accounts=accounts,
        filter_status=filter_status, inr=inr,
        pager=pager, pager_prev=pager_prev, pager_next=pager_next,
        ea_cats=ea_cats, cat_picks=cat_picks,
    ))


@router.get("/expense-analyser/settings", response_class=HTMLResponse)
def expense_analyser_settings(request: Request, db: Session = Depends(get_db)):
    from app import expense_analyser as ea
    from app.routers import tracker as tr
    user = _ea_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    st = ea.status_dict(db, user)
    passwords = tr.list_passwords(db=db, current_user=user)
    return templates.TemplateResponse("expense_analyser_settings.html", _ea_ctx(
        request, user, "ea_settings",
        status=st, redirect_uri=_ea_redirect_uri(request),
        passwords=passwords, bank_labels=tr.BANK_LABELS,
        password_next="/admin/expense-analyser/settings",
    ))


@router.get("/expense-analyser/sync-log", response_class=HTMLResponse)
def expense_analyser_sync_log(
    request: Request,
    page: int = 1,
    db: Session = Depends(get_db),
):
    from app import expense_analyser as ea
    from app.paging import paginate
    user = _ea_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    st = ea.status_dict(db, user)
    total = ea.count_sync_logs(db, user)
    pager = paginate(page=page, per_page=40, total=total)
    sync_logs = ea.list_sync_logs(
        db, user, limit=pager["per_page"], offset=pager["offset"],
    )
    pager_prev, pager_next = _pager_urls("/admin/expense-analyser/sync-log", pager)
    return templates.TemplateResponse("expense_analyser_sync_log.html", _ea_ctx(
        request, user, "ea_sync_log",
        status=st, sync_logs=sync_logs,
        pager=pager, pager_prev=pager_prev, pager_next=pager_next,
    ))


@router.get("/expense-analyser/insights", response_class=HTMLResponse)
def expense_analyser_insights(
    request: Request,
    month: str = "",
    db: Session = Depends(get_db),
):
    from app import expense_analyser as ea
    from app.routers.finance import inr
    user = _ea_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    report = ea.insights(db, user, month or None)
    return templates.TemplateResponse("expense_analyser_insights.html", _ea_ctx(
        request, user, "ea_insights", report=report, inr=inr,
    ))


@router.get("/expense-analyser/statements", response_class=HTMLResponse)
def ea_statements(request: Request, status: str = "pending", db: Session = Depends(get_db)):
    from app import expense_analyser as ea
    from app.routers import tracker as tr
    from app.routers import finance as fn
    user = _ea_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    rows = tr.list_statements(status=status or "pending", category=None, q=None, db=db, current_user=user)
    passwords = tr.list_passwords(db=db, current_user=user)
    fn.ensure_defaults(db, user)
    accounts = fn.list_accounts(db=db, current_user=user)
    st = ea.status_dict(db, user)
    mail_pdfs = ea.list_mail_pdfs(db, user, limit=40)
    return templates.TemplateResponse("tracker_statements.html", _ea_ctx(
        request, user, "ea_statements", rows=rows, passwords=passwords,
        accounts=accounts, status=status or "pending", inr=fn.inr,
        ea_status=st, mail_pdfs=mail_pdfs, bank_labels=tr.BANK_LABELS,
        password_next="/admin/expense-analyser/statements",
    ))


@router.post("/expense-analyser/schedule")
async def expense_analyser_schedule(request: Request, db: Session = Depends(get_db)):
    from app import expense_analyser as ea
    user = _ea_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    form = await request.form()
    hour = int(str(form.get("hour") or "6") or "6")
    ea.save_schedule(db, user, enabled=bool(form.get("enabled")), hour=hour)
    return RedirectResponse("/admin/expense-analyser/settings?ok=schedule", status_code=302)


@router.get("/expense-analyser/google/connect")
def expense_analyser_google_connect(request: Request, db: Session = Depends(get_db)):
    import secrets
    from app import expense_analyser as ea, gmail
    from app.drive_backup import oauth_creds, oauth_ready
    user = _ea_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    if not oauth_ready(db):
        return RedirectResponse("/admin/expense-analyser/settings?err=client", status_code=302)
    client_id, _secret = oauth_creds(db)
    state = secrets.token_urlsafe(16)
    request.session["ea_gmail_oauth_state"] = state
    url = gmail.auth_url(client_id, _ea_redirect_uri(request), state)
    return RedirectResponse(url, status_code=302)


@router.get("/expense-analyser/google/callback")
def expense_analyser_google_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    db: Session = Depends(get_db),
):
    from app import expense_analyser as ea, gmail, crypto
    from app.drive_backup import oauth_creds, oauth_ready
    user = _ea_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    if error:
        return RedirectResponse("/admin/expense-analyser/settings?err=denied", status_code=302)
    if not code or state != request.session.get("ea_gmail_oauth_state"):
        return RedirectResponse("/admin/expense-analyser/settings?err=state", status_code=302)
    if not oauth_ready(db):
        return RedirectResponse("/admin/expense-analyser/settings?err=client", status_code=302)
    client_id, secret = oauth_creds(db)
    row = ea.get_or_create(db, user)
    try:
        tokens = gmail.exchange_code(client_id, secret, code, _ea_redirect_uri(request))
        refresh = tokens.get("refresh_token")
        access = tokens.get("access_token")
        if not refresh:
            return RedirectResponse("/admin/expense-analyser/settings?err=token", status_code=302)
        row.refresh_token_enc = crypto.encrypt_text(refresh)
        if access:
            row.connected_email = gmail.user_email(access)
        db.commit()
    except Exception:
        return RedirectResponse("/admin/expense-analyser/settings?err=token", status_code=302)
    request.session.pop("ea_gmail_oauth_state", None)
    return RedirectResponse("/admin/expense-analyser/settings?ok=connected", status_code=302)


@router.post("/expense-analyser/sync")
def expense_analyser_sync(request: Request, db: Session = Depends(get_db)):
    from app import expense_analyser as ea
    user = _ea_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    row = ea.get_or_create(db, user)
    if not row.refresh_token_enc:
        return RedirectResponse("/admin/expense-analyser/settings?err=client", status_code=302)
    started = ea.start_sync_background(vault_id(user), trigger="manual")
    if not started:
        return RedirectResponse("/admin/expense-analyser?ok=sync_busy", status_code=303)
    return RedirectResponse("/admin/expense-analyser?ok=sync_started", status_code=303)


@router.post("/expense-analyser/reconcile")
def expense_analyser_reconcile(request: Request, db: Session = Depends(get_db)):
    from app import expense_analyser as ea
    user = _ea_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    ea.reconnect_matches(db, user)
    return RedirectResponse("/admin/expense-analyser?ok=reconciled", status_code=302)


@router.post("/expense-analyser/retag")
async def expense_analyser_retag(request: Request, db: Session = Depends(get_db)):
    from app import expense_analyser as ea
    user = _ea_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    form = await request.form()
    force = str(form.get("force") or "") in ("1", "on", "true", "yes")
    started = ea.start_retag_background(
        vault_id(user), limit=ea._RETAG_AI_LIMIT, use_ai=True, force=force,
    )
    if not started:
        return RedirectResponse("/admin/expense-analyser?ok=retag_busy", status_code=303)
    return RedirectResponse(
        "/admin/expense-analyser?ok=retag_started" + ("&force=1" if force else ""),
        status_code=303,
    )


@router.post("/expense-analyser/retag-selected")
async def expense_analyser_retag_selected(request: Request, db: Session = Depends(get_db)):
    from app import expense_analyser as ea
    user = _ea_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    form = await request.form()
    raw_ids = form.getlist("item_id") if hasattr(form, "getlist") else []
    if not raw_ids:
        single = str(form.get("item_id") or "").strip()
        raw_ids = [single] if single else []
    ids = [str(v).strip() for v in raw_ids if str(v).strip()]
    if not ids:
        return RedirectResponse("/admin/expense-analyser?err=Select+at+least+one+item", status_code=303)
    started = ea.start_retag_background(
        vault_id(user), use_ai=True, item_ids=ids[: ea._RETAG_AI_LIMIT],
    )
    if not started:
        return RedirectResponse("/admin/expense-analyser?ok=retag_busy", status_code=303)
    return RedirectResponse(
        f"/admin/expense-analyser?ok=retag_started&count={min(len(ids), ea._RETAG_AI_LIMIT)}",
        status_code=303,
    )


@router.post("/expense-analyser/items/{item_id}/retag")
def expense_analyser_retag_item(item_id: str, request: Request, db: Session = Depends(get_db)):
    from app import expense_analyser as ea
    user = _ea_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    started = ea.start_retag_background(
        vault_id(user), use_ai=True, item_ids=[item_id],
    )
    if not started:
        return RedirectResponse("/admin/expense-analyser?ok=retag_busy", status_code=303)
    return RedirectResponse("/admin/expense-analyser?ok=retag_started&count=1", status_code=303)


@router.get("/expense-analyser/clear", response_class=HTMLResponse)
def expense_analyser_clear_page(request: Request, db: Session = Depends(get_db)):
    from app import expense_analyser as ea
    user = _ea_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    st = ea.status_dict(db, user)
    return templates.TemplateResponse(
        "expense_analyser_clear.html",
        _ea_ctx(request, user, "ea_inbox", status=st),
    )


@router.post("/expense-analyser/clear")
def expense_analyser_clear(request: Request, db: Session = Depends(get_db)):
    from app import expense_analyser as ea
    user = _ea_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    result = ea.clear_inbox(db, user)
    return RedirectResponse(
        f"/admin/expense-analyser?ok=cleared&deleted={result.get('deleted', 0)}",
        status_code=303,
    )


@router.post("/expense-analyser/disconnect")
def expense_analyser_disconnect(request: Request, db: Session = Depends(get_db)):
    from app import expense_analyser as ea
    user = _ea_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    ea.disconnect(db, user)
    return RedirectResponse("/admin/expense-analyser/settings", status_code=302)


@router.post("/expense-analyser/query")
async def expense_analyser_query(request: Request, db: Session = Depends(get_db)):
    from app import expense_analyser as ea
    user = _ea_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    form = await request.form()
    ea.save_query(db, user, str(form.get("sync_query") or ""))
    return RedirectResponse("/admin/expense-analyser/settings", status_code=302)


@router.post("/expense-analyser/items/{item_id}/post")
async def expense_analyser_post_item(item_id: str, request: Request, db: Session = Depends(get_db)):
    from app import expense_analyser as ea
    user = _ea_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    form = await request.form()
    try:
        ea.post_to_finance(
            db, user, item_id,
            account_id=str(form.get("account_id") or "") or None,
            category_id=str(form.get("category_id") or "") or None,
            subcategory_id=str(form.get("subcategory_id") or "") or None,
            new_category=str(form.get("new_category") or "").strip() or None,
            new_subcategory=str(form.get("new_subcategory") or "").strip() or None,
        )
    except (LookupError, RuntimeError) as exc:
        return RedirectResponse(f"/admin/expense-analyser?err={exc}", status_code=302)
    return RedirectResponse("/admin/expense-analyser?ok=posted", status_code=302)


@router.post("/expense-analyser/items/{item_id}/ignore")
def expense_analyser_ignore_item(item_id: str, request: Request, db: Session = Depends(get_db)):
    from app import expense_analyser as ea
    user = _ea_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    try:
        ea.ignore_item(db, user, item_id)
    except LookupError:
        pass
    return RedirectResponse("/admin/expense-analyser", status_code=302)


# ---------- Shopping List ----------
def _tr_ctx(request, user, active_nav, **extra):
    from app.routers.finance import inr
    ctx = {
        "request": request, "session_user": user, "active_nav": active_nav,
        "active_module": "tracker", "people": [], "active_person_id": None,
        "inr": inr,
    }
    ctx.update(extra)
    return ctx


def _tr_user(request, db):
    return require_login(request, db)


@router.get("/tracker", response_class=HTMLResponse)
def tracker_home(request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    summary = tr.tracker_summary(db=db, current_user=user)
    lists = tr.list_lists(completed=None, db=db, current_user=user)
    return templates.TemplateResponse("tracker_lists.html", _tr_ctx(
        request, user, "tr_lists", summary=summary, lists=lists,
    ))


@router.post("/tracker/lists")
def tracker_create_list(request: Request, name: str = Form(...), description: str = Form(""), db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    from app import schemas as sc
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    created = tr.create_list(sc.ShopListIn(name=name, description=description or None), db=db, current_user=user)
    return RedirectResponse(f"/admin/tracker/lists/{created.id}", status_code=302)


@router.get("/tracker/lists/{list_id}/live")
def tracker_list_live(list_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return JSONResponse({"error": "auth"}, status_code=401)
    lst = tr.get_list(list_id, db=db, current_user=user)
    return JSONResponse({
        "revision": lst.revision,
        "item_count": lst.item_count,
        "checked_count": lst.checked_count,
        "pending_count": lst.pending_count,
    })


@router.get("/tracker/lists/{list_id}", response_class=HTMLResponse)
def tracker_list_page(list_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    from app.grocery import catalog_payload
    import json
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    lst = tr.get_list(list_id, db=db, current_user=user)
    items = lst.items or []
    friends = tr.list_friends(db=db, current_user=user)
    catalog = catalog_payload()
    return templates.TemplateResponse("tracker_list.html", _tr_ctx(
        request, user, "tr_lists", lst=lst,
        pending=[i for i in items if i.status == "pending"],
        approved=[i for i in items if i.status != "pending"],
        friends=friends, groups=catalog["groups"],
        catalog_json=json.dumps(catalog, ensure_ascii=False),
        receipts=lst.receipts or [],
        revision=lst.revision,
    ))


@router.post("/tracker/lists/{list_id}/items")
def tracker_add_item(
    list_id: str, request: Request, name: str = Form(...),
    quantity: str = Form("1"), unit: str = Form(""), price: str = Form(""),
    emoji: str = Form(""), category: str = Form(""),
    db: Session = Depends(get_db),
):
    from app.routers import tracker as tr
    from app import schemas as sc
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    qty = float(quantity or 1)
    pr = float(price) if price.strip() else None
    tr.add_item(list_id, sc.ShopItemIn(
        name=name, quantity=qty, unit=unit or None, price=pr,
        emoji=emoji or None, category=category or None,
    ), db=db, current_user=user)
    return RedirectResponse(f"/admin/tracker/lists/{list_id}", status_code=302)


@router.post("/tracker/lists/{list_id}/items/{item_id}/toggle")
def tracker_toggle_item(list_id: str, item_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    tr.toggle_item(list_id, item_id, db=db, current_user=user)
    return RedirectResponse(f"/admin/tracker/lists/{list_id}", status_code=302)


@router.post("/tracker/lists/{list_id}/items/{item_id}/approve")
def tracker_approve_item(list_id: str, item_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    tr.approve_item(list_id, item_id, db=db, current_user=user)
    return RedirectResponse(f"/admin/tracker/lists/{list_id}", status_code=302)


@router.post("/tracker/lists/{list_id}/items/{item_id}/reject")
def tracker_reject_item(list_id: str, item_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    tr.reject_item(list_id, item_id, db=db, current_user=user)
    return RedirectResponse(f"/admin/tracker/lists/{list_id}", status_code=302)


@router.post("/tracker/lists/{list_id}/items/{item_id}/delete")
def tracker_delete_item(list_id: str, item_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    tr.delete_item(list_id, item_id, db=db, current_user=user)
    return RedirectResponse(f"/admin/tracker/lists/{list_id}", status_code=302)


@router.post("/tracker/lists/{list_id}/items/{item_id}/edit")
def tracker_edit_item(
    list_id: str, item_id: str, request: Request,
    name: str = Form(...), quantity: str = Form("1"), unit: str = Form(""), price: str = Form(""),
    db: Session = Depends(get_db),
):
    from app.routers import tracker as tr
    from app import schemas as sc
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    qty = float(quantity or 1)
    pr = float(price) if str(price).strip() else None
    tr.update_item(list_id, item_id, sc.ShopItemUpdate(
        name=name, quantity=qty, unit=unit or None, price=pr,
    ), db=db, current_user=user)
    return RedirectResponse(f"/admin/tracker/lists/{list_id}", status_code=302)


@router.post("/tracker/lists/{list_id}/share")
def tracker_share_list(list_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    share = tr.share_list(list_id, request, db=db, current_user=user)
    return RedirectResponse(f"/admin/tracker/lists/{list_id}?share={share.token}", status_code=302)


@router.post("/tracker/lists/{list_id}/receipts")
async def tracker_upload_receipt(
    list_id: str, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db),
):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    if not file.filename:
        return RedirectResponse(f"/admin/tracker/lists/{list_id}?err=Pick+a+photo+or+PDF", status_code=302)
    raw = await file.read()
    try:
        tr.save_receipt(db, user, list_id, raw, file.content_type, file.filename)
    except HTTPException as exc:
        from urllib.parse import quote
        return RedirectResponse(f"/admin/tracker/lists/{list_id}?err={quote(str(exc.detail))}", status_code=302)
    return RedirectResponse(f"/admin/tracker/lists/{list_id}?ok=1", status_code=302)


@router.get("/tracker/lists/{list_id}/receipts/{receipt_id}/image")
def tracker_receipt_image(list_id: str, receipt_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    return tr.get_receipt_image(list_id, receipt_id, db=db, current_user=user)


@router.post("/tracker/lists/{list_id}/receipts/{receipt_id}/delete")
def tracker_delete_receipt(list_id: str, receipt_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    tr.delete_receipt(list_id, receipt_id, db=db, current_user=user)
    return RedirectResponse(f"/admin/tracker/lists/{list_id}?ok=1", status_code=302)


@router.post("/tracker/lists/{list_id}/whatsapp")
def tracker_whatsapp_list(list_id: str, request: Request, db: Session = Depends(get_db)):
    from urllib.parse import quote
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    share = tr.share_list(list_id, request, db=db, current_user=user)
    lst = tr.get_list(list_id, db=db, current_user=user)
    lines = [lst.name, share.url, ""]
    for item in (lst.items or []):
        if item.status == "pending":
            continue
        bit = item.name
        if item.quantity:
            bit += f" {item.quantity:g}"
            if item.unit:
                bit += f" {item.unit}"
        if item.checked:
            bit += " ✓"
        lines.append(bit)
    return RedirectResponse("https://wa.me/?text=" + quote("\n".join(lines)), status_code=303)


@router.post("/tracker/lists/{list_id}/complete")
def tracker_complete_list(list_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    from app import schemas as sc
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    lst = tr.get_list(list_id, db=db, current_user=user)
    tr.update_list(list_id, sc.ShopListUpdate(completed=not lst.completed), db=db, current_user=user)
    return RedirectResponse(f"/admin/tracker/lists/{list_id}", status_code=302)


@router.post("/tracker/lists/{list_id}/delete")
def tracker_delete_list(list_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    tr.delete_list(list_id, db=db, current_user=user)
    return RedirectResponse("/admin/tracker?ok=trashed", status_code=302)


@router.get("/tracker/trash", response_class=HTMLResponse)
def tracker_trash_page(request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    items = tr.list_trash(db=db, current_user=user)
    return templates.TemplateResponse("tracker_trash.html", _tr_ctx(
        request, user, "tr_trash", lists=items,
    ))


@router.post("/tracker/trash/empty")
def tracker_trash_empty(request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    tr.empty_trash(db=db, current_user=user)
    return RedirectResponse("/admin/tracker/trash", status_code=302)


@router.post("/tracker/lists/{list_id}/restore")
def tracker_restore_list(list_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    tr.restore_list(list_id, db=db, current_user=user)
    return RedirectResponse("/admin/tracker?ok=restored", status_code=302)


@router.post("/tracker/lists/{list_id}/permanent")
def tracker_permanent_delete_list(list_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    tr.permanent_delete_list(list_id, db=db, current_user=user)
    return RedirectResponse("/admin/tracker/trash", status_code=302)


@router.post("/tracker/lists/{list_id}/send")
def tracker_send_list(list_id: str, request: Request, email: str = Form(...), message: str = Form(""), db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    from app import schemas as sc
    from fastapi import HTTPException
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    try:
        tr.send_list(list_id, sc.ShopSendIn(email=email, message=message or None), db=db, current_user=user)
    except HTTPException as exc:
        return RedirectResponse(f"/admin/tracker/lists/{list_id}?err={exc.detail}", status_code=302)
    return RedirectResponse(f"/admin/tracker/lists/{list_id}?ok=sent", status_code=302)


@router.get("/tracker/statements", response_class=HTMLResponse)
def tracker_statements(request: Request, status: str = "pending"):
    qs = f"?status={status}" if status and status != "pending" else ""
    return RedirectResponse(f"/admin/expense-analyser/statements{qs}", status_code=302)


@router.post("/expense-analyser/statements/upload")
@router.post("/tracker/statements/upload")
async def tracker_upload_statement(request: Request, file: UploadFile = File(...), password: str = Form(""), identifier: str = Form(""), db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    from fastapi import HTTPException
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    try:
        result = await tr.upload_statement(file=file, password=password, identifier=identifier, db=db, current_user=user)
    except HTTPException as exc:
        return RedirectResponse(f"/admin/expense-analyser/statements?err={exc.detail}", status_code=302)
    return RedirectResponse(
        f"/admin/expense-analyser/statements?ok=1&created={result.get('created', 0)}&skipped={result.get('skipped', 0)}",
        status_code=302,
    )


@router.post("/expense-analyser/statements/post-all")
@router.post("/tracker/statements/post-all")
def tracker_post_all(request: Request, account_id: str = Form(""), db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    rows = tr.list_statements(status="pending", category=None, q=None, db=db, current_user=user)
    for row in rows:
        try:
            tr.post_statement_txn(db, user, row.id, account_id or None)
        except (LookupError, RuntimeError):
            continue
    return RedirectResponse("/admin/expense-analyser/statements?ok=posted", status_code=302)


@router.post("/expense-analyser/statements/{txn_id}/post")
@router.post("/tracker/statements/{txn_id}/post")
def tracker_post_statement(txn_id: str, request: Request, account_id: str = Form(""), db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    try:
        tr.post_statement_txn(db, user, txn_id, account_id or None)
    except (LookupError, RuntimeError) as exc:
        return RedirectResponse(f"/admin/expense-analyser/statements?err={exc}", status_code=302)
    return RedirectResponse("/admin/expense-analyser/statements?ok=posted", status_code=302)


@router.post("/expense-analyser/statements/{txn_id}/ignore")
@router.post("/tracker/statements/{txn_id}/ignore")
def tracker_ignore_statement(txn_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    tr.ignore_one(txn_id, db=db, current_user=user)
    return RedirectResponse("/admin/expense-analyser/statements", status_code=302)


@router.post("/expense-analyser/passwords")
@router.post("/tracker/passwords")
async def tracker_save_password(request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    from app import schemas as sc
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    form = await request.form()
    identifier = str(form.get("identifier") or "").strip()
    password = str(form.get("password") or "")
    account_type = str(form.get("account_type") or "bank")
    last_4_digits = str(form.get("last_4_digits") or "")
    nxt = str(form.get("next") or "/admin/expense-analyser/statements")
    if nxt not in ("/admin/expense-analyser/statements", "/admin/expense-analyser/settings"):
        nxt = "/admin/expense-analyser/statements"
    if not identifier or not password:
        return RedirectResponse(f"{nxt}?err=Bank+name+and+password+are+required", status_code=302)
    tr.save_password(sc.ShopPdfPasswordIn(
        identifier=identifier, password=password, account_type=account_type,
        last_4_digits=last_4_digits or None,
    ), db=db, current_user=user)
    return RedirectResponse(f"{nxt}?ok=password", status_code=302)


@router.post("/expense-analyser/passwords/{password_id}/delete")
@router.post("/tracker/passwords/{password_id}/delete")
def tracker_delete_password(password_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    tr.delete_password(password_id, db=db, current_user=user)
    nxt = request.query_params.get("next") or "/admin/expense-analyser/statements"
    if nxt not in ("/admin/expense-analyser/statements", "/admin/expense-analyser/settings"):
        nxt = "/admin/expense-analyser/statements"
    return RedirectResponse(nxt, status_code=302)


@router.post("/expense-analyser/statements/from-mail")
def ea_import_pdfs_from_mail(request: Request, db: Session = Depends(get_db)):
    from app import expense_analyser as ea
    user = _ea_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    row = ea.get_or_create(db, user)
    if not row.refresh_token_enc:
        return RedirectResponse("/admin/expense-analyser/settings?err=gmail", status_code=302)
    started = ea.start_pdf_import_background(vault_id(user))
    if not started:
        return RedirectResponse("/admin/expense-analyser/statements?ok=sync_busy", status_code=303)
    return RedirectResponse("/admin/expense-analyser/statements?ok=pdf_started", status_code=303)


@router.post("/expense-analyser/mail-pdfs/{pdf_id}/ignore")
def ea_ignore_mail_pdf(pdf_id: str, request: Request, db: Session = Depends(get_db)):
    from app import expense_analyser as ea
    user = _ea_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    try:
        ea.ignore_mail_pdf(db, user, pdf_id)
    except LookupError:
        pass
    return RedirectResponse("/admin/expense-analyser/statements", status_code=302)


def _ea_mail_pdf_response(pdf_id: str, request: Request, db: Session, *, inline: bool):
    from app import expense_analyser as ea
    from urllib.parse import quote

    user = _ea_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    try:
        data, filename = ea.fetch_mail_pdf_bytes(db, user, pdf_id)
    except LookupError:
        return RedirectResponse("/admin/expense-analyser/statements?err=PDF+not+found", status_code=302)
    except RuntimeError as exc:
        return RedirectResponse(
            f"/admin/expense-analyser/statements?err={quote(str(exc))}",
            status_code=302,
        )
    safe = filename.replace('"', "")
    disposition = "inline" if inline else "attachment"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{safe}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/expense-analyser/mail-pdfs/{pdf_id}/view")
def ea_view_mail_pdf(pdf_id: str, request: Request, db: Session = Depends(get_db)):
    return _ea_mail_pdf_response(pdf_id, request, db, inline=True)


@router.get("/expense-analyser/mail-pdfs/{pdf_id}/download")
def ea_download_mail_pdf(pdf_id: str, request: Request, db: Session = Depends(get_db)):
    return _ea_mail_pdf_response(pdf_id, request, db, inline=False)


@router.get("/tracker/friends", response_class=HTMLResponse)
def tracker_friends(request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    friends = tr.list_friends(db=db, current_user=user)
    return templates.TemplateResponse("tracker_friends.html", _tr_ctx(
        request, user, "tr_friends", friends=friends,
    ))


@router.post("/tracker/friends")
def tracker_add_friend(
    request: Request, name: str = Form(...), email: str = Form(""),
    phone: str = Form(""), relation: str = Form(""),
    db: Session = Depends(get_db),
):
    from app.routers import tracker as tr
    from app import schemas as sc
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    tr.add_friend(sc.ShopContactIn(
        name=name, email=email or None, phone=phone or None, relation=relation or None,
    ), db=db, current_user=user)
    return RedirectResponse("/admin/tracker/friends?ok=1", status_code=302)


@router.post("/tracker/friends/{contact_id}/delete")
def tracker_delete_friend(contact_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    tr.delete_friend(contact_id, db=db, current_user=user)
    return RedirectResponse("/admin/tracker/friends", status_code=302)


@router.get("/tracker/more", response_class=HTMLResponse)
def tracker_more(request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    summary = tr.tracker_summary(db=db, current_user=user)
    inbox = tr.inbox(db=db, current_user=user)
    sent = tr.sent(db=db, current_user=user)
    return templates.TemplateResponse("tracker_more.html", _tr_ctx(
        request, user, "tr_more", summary=summary, inbox=inbox, sent=sent,
    ))


@router.post("/tracker/inbox/{send_id}/accept")
def tracker_accept_send(send_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    lst = tr.accept_send(send_id, db=db, current_user=user)
    return RedirectResponse(f"/admin/tracker/lists/{lst.id}", status_code=302)


@router.post("/tracker/inbox/{send_id}/reject")
def tracker_reject_send(send_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    tr.reject_send(send_id, db=db, current_user=user)
    return RedirectResponse("/admin/tracker/more", status_code=302)


@router.post("/tracker/sent/{send_id}/recall")
def tracker_recall_send(send_id: str, request: Request, db: Session = Depends(get_db)):
    from app.routers import tracker as tr
    user = _tr_user(request, db)
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    tr.recall_send(send_id, db=db, current_user=user)
    return RedirectResponse("/admin/tracker/more", status_code=302)
