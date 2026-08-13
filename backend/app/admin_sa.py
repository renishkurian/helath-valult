"""Super Admin HTML: users, online presence, failed logins, and signup."""
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app import models
from app.accounts import AccountExists, create_vault_user
from app.admin import require_login, templates
from app.config import settings
from app.database import get_db
from app.deps import is_superadmin
from app.login_guard import is_online, online_since

router = APIRouter(prefix="/admin/sa", tags=["superadmin"])


def _sa_user(request: Request, db: Session) -> Optional[models.User]:
    user = require_login(request, db)
    if not user or not is_superadmin(user):
        return None
    return user


def _sa_ctx(request, user, active_nav, **extra):
    ctx = {
        "request": request, "session_user": user, "active_nav": active_nav,
        "active_module": "superadmin", "people": [], "active_person_id": None,
        "is_online": is_online,
    }
    ctx.update(extra)
    return ctx


def _deny(user: Optional[models.User]) -> RedirectResponse:
    if not user:
        return RedirectResponse("/admin/login", status_code=302)
    return RedirectResponse("/admin/modules", status_code=302)


def _stats(db: Session) -> dict:
    since = online_since()
    day_ago = datetime.utcnow() - timedelta(hours=24)
    total = db.query(func.count(models.User.id)).scalar() or 0
    online = db.query(func.count(models.User.id)).filter(models.User.last_seen_at >= since).scalar() or 0
    failed_24h = db.query(func.count(models.LoginAttempt.id)).filter(
        models.LoginAttempt.success.is_(False),
        models.LoginAttempt.created_at >= day_ago,
    ).scalar() or 0
    owners = db.query(func.count(models.User.id)).filter(models.User.role == models.UserRole.owner.value).scalar() or 0
    totp_on = db.query(func.count(models.User.id)).filter(models.User.totp_enabled.is_(True)).scalar() or 0
    return {"total": total, "online": online, "failed_24h": failed_24h, "owners": owners, "totp_on": totp_on}


@router.get("", response_class=HTMLResponse)
def sa_home(request: Request, db: Session = Depends(get_db)):
    user = _sa_user(request, db)
    if not user:
        return _deny(require_login(request, db))
    recent_fails = (
        db.query(models.LoginAttempt)
        .filter(models.LoginAttempt.success.is_(False))
        .order_by(models.LoginAttempt.created_at.desc())
        .limit(8)
        .all()
    )
    recent_users = db.query(models.User).order_by(models.User.created_at.desc()).limit(6).all()
    return templates.TemplateResponse("sa_home.html", _sa_ctx(
        request, user, "sa_home",
        stats=_stats(db),
        recent_fails=recent_fails,
        recent_users=recent_users,
        lockout_minutes=settings.LOGIN_LOCKOUT_MINUTES,
        max_attempts=settings.LOGIN_MAX_ATTEMPTS,
        recaptcha_on=bool(settings.RECAPTCHA_SITE_KEY and settings.RECAPTCHA_SECRET),
        online_window=settings.ONLINE_WINDOW_MINUTES,
    ))


@router.get("/users", response_class=HTMLResponse)
def sa_users(request: Request, q: str = "", role: str = "", cleared: str = "", db: Session = Depends(get_db)):
    user = _sa_user(request, db)
    if not user:
        return _deny(require_login(request, db))
    query = db.query(models.User)
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(models.User.email.ilike(like), models.User.full_name.ilike(like)))
    if role in (models.UserRole.owner.value, models.UserRole.viewer.value, models.UserRole.superadmin.value):
        query = query.filter(models.User.role == role)
    rows = query.order_by(models.User.created_at.desc()).limit(500).all()
    return templates.TemplateResponse("sa_users.html", _sa_ctx(
        request, user, "sa_users", users=rows, q=q, role=role, stats=_stats(db),
        cleared=cleared or None,
    ))


@router.post("/users/{user_id}/disable-2fa")
def sa_disable_2fa(user_id: str, request: Request, db: Session = Depends(get_db)):
    from app import totp as totp_util
    from app.login_guard import client_ip, client_ua, log_attempt
    user = _sa_user(request, db)
    if not user:
        return _deny(require_login(request, db))
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        return RedirectResponse("/admin/sa/users", status_code=302)
    totp_util.disable(target)
    db.commit()
    log_attempt(
        db, email=target.email, ip=client_ip(request),
        user_agent=f"2FA cleared by {user.email}",
        success=True, reason="sa_2fa_off",
    )
    return RedirectResponse(f"/admin/sa/users?cleared={quote(target.email)}", status_code=302)


@router.get("/online", response_class=HTMLResponse)
def sa_online(request: Request, db: Session = Depends(get_db)):
    user = _sa_user(request, db)
    if not user:
        return _deny(require_login(request, db))
    rows = (
        db.query(models.User)
        .filter(models.User.last_seen_at >= online_since())
        .order_by(models.User.last_seen_at.desc())
        .all()
    )
    return templates.TemplateResponse("sa_online.html", _sa_ctx(
        request, user, "sa_online", users=rows, stats=_stats(db),
        online_window=settings.ONLINE_WINDOW_MINUTES,
    ))


@router.get("/logins", response_class=HTMLResponse)
def sa_logins(request: Request, q: str = "", outcome: str = "failed", db: Session = Depends(get_db)):
    user = _sa_user(request, db)
    if not user:
        return _deny(require_login(request, db))
    query = db.query(models.LoginAttempt)
    if outcome == "failed":
        query = query.filter(models.LoginAttempt.success.is_(False))
    elif outcome == "ok":
        query = query.filter(models.LoginAttempt.success.is_(True))
    if q.strip():
        like = f"%{q.strip()}%"
        query = query.filter(or_(
            models.LoginAttempt.email.ilike(like),
            models.LoginAttempt.ip.ilike(like),
        ))
    rows = query.order_by(models.LoginAttempt.created_at.desc()).limit(300).all()
    return templates.TemplateResponse("sa_logins.html", _sa_ctx(
        request, user, "sa_logins", attempts=rows, q=q, outcome=outcome, stats=_stats(db),
    ))


@router.get("/signup", response_class=HTMLResponse)
def sa_signup_form(request: Request, db: Session = Depends(get_db), created: str = "", error: str = ""):
    user = _sa_user(request, db)
    if not user:
        return _deny(require_login(request, db))
    return templates.TemplateResponse("sa_signup.html", _sa_ctx(
        request, user, "sa_signup", created=created, error=error or None,
    ))


@router.post("/signup", response_class=HTMLResponse)
async def sa_signup_submit(request: Request, db: Session = Depends(get_db)):
    user = _sa_user(request, db)
    if not user:
        return _deny(require_login(request, db))
    form = await request.form()
    email = str(form.get("email") or "")
    password = str(form.get("password") or "")
    full_name = str(form.get("full_name") or "")
    role = str(form.get("role") or models.UserRole.owner.value)
    if role not in (models.UserRole.owner.value, models.UserRole.superadmin.value):
        role = models.UserRole.owner.value
    try:
        created = create_vault_user(db, email=email, password=password, full_name=full_name, role=role)
    except AccountExists:
        return templates.TemplateResponse("sa_signup.html", _sa_ctx(
            request, user, "sa_signup", error="An account with this email already exists.", created="",
        ), status_code=409)
    except ValueError as exc:
        return templates.TemplateResponse("sa_signup.html", _sa_ctx(
            request, user, "sa_signup", error=str(exc), created="",
        ), status_code=400)
    return RedirectResponse(f"/admin/sa/signup?created={quote(created.email)}", status_code=302)
