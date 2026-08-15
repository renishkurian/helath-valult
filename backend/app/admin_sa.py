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
    blocked = db.query(func.count(models.User.id)).filter(models.User.blocked.is_(True)).scalar() or 0
    return {
        "total": total, "online": online, "failed_24h": failed_24h,
        "owners": owners, "totp_on": totp_on, "blocked": blocked,
    }


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
    from app.server_settings import login_max_attempts, recaptcha_ready
    return templates.TemplateResponse("sa_home.html", _sa_ctx(
        request, user, "sa_home",
        stats=_stats(db),
        recent_fails=recent_fails,
        recent_users=recent_users,
        max_attempts=login_max_attempts(db),
        recaptcha_on=recaptcha_ready(db),
        online_window=settings.ONLINE_WINDOW_MINUTES,
    ))


@router.get("/users", response_class=HTMLResponse)
def sa_users(request: Request, q: str = "", role: str = "", cleared: str = "", notice: str = "", who: str = "", db: Session = Depends(get_db)):
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
        cleared=cleared or None, notice=notice or None, who=who or None,
    ))


@router.get("/users/{user_id}/modules", response_class=HTMLResponse)
def sa_user_modules(user_id: str, request: Request, db: Session = Depends(get_db)):
    from app import modules as mod

    user = _sa_user(request, db)
    if not user:
        return _deny(require_login(request, db))
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        return RedirectResponse("/admin/sa/users", status_code=302)
    # Edit vault owner's list (viewers inherit)
    owner = target
    if target.role == models.UserRole.viewer.value and target.vault_owner_id:
        owner = db.query(models.User).filter(models.User.id == target.vault_owner_id).first() or target
    current = mod.parse_enabled_modules(owner.enabled_modules)
    enabled = set(current) if current is not None else set(mod.DEFAULT_MODULE_KEYS)
    return templates.TemplateResponse("sa_user_modules.html", _sa_ctx(
        request, user, "sa_users",
        target=target, owner=owner,
        module_keys=mod.DEFAULT_MODULE_KEYS,
        module_labels=mod.MODULE_LABELS,
        enabled=enabled,
        all_enabled=(current is None),
    ))


@router.post("/users/{user_id}/modules")
async def sa_user_modules_save(user_id: str, request: Request, db: Session = Depends(get_db)):
    from app import modules as mod

    user = _sa_user(request, db)
    if not user:
        return _deny(require_login(request, db))
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        return RedirectResponse("/admin/sa/users", status_code=302)
    owner = target
    if target.role == models.UserRole.viewer.value and target.vault_owner_id:
        owner = db.query(models.User).filter(models.User.id == target.vault_owner_id).first() or target
    if owner.role == models.UserRole.superadmin.value:
        return RedirectResponse(f"/admin/sa/users/{owner.id}/modules?notice=sa", status_code=302)
    form = await request.form()
    if form.get("all_modules"):
        owner.enabled_modules = None
    else:
        chosen = [k for k in mod.DEFAULT_MODULE_KEYS if form.get(f"mod_{k}")]
        owner.enabled_modules = mod.serialize_enabled_modules(chosen or list(mod.DEFAULT_MODULE_KEYS))
    db.commit()
    return RedirectResponse(
        f"/admin/sa/users?notice=modules&who={quote(owner.email)}",
        status_code=302,
    )


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


@router.post("/users/{user_id}/disable-app-approve")
def sa_disable_app_approve(user_id: str, request: Request, db: Session = Depends(get_db)):
    from app.login_guard import client_ip, log_attempt
    user = _sa_user(request, db)
    if not user:
        return _deny(require_login(request, db))
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        return RedirectResponse("/admin/sa/users", status_code=302)
    target.app_approve = False
    db.query(models.LoginChallenge).filter(
        models.LoginChallenge.user_id == target.id,
        models.LoginChallenge.status == "pending",
    ).update({"status": "expired"}, synchronize_session=False)
    db.commit()
    log_attempt(
        db, email=target.email, ip=client_ip(request),
        user_agent=f"app approval cleared by {user.email}",
        success=True, reason="sa_app_off",
    )
    return RedirectResponse(f"/admin/sa/users?notice=app-off&who={quote(target.email)}", status_code=302)


@router.post("/users/{user_id}/block")
def sa_block_user(user_id: str, request: Request, db: Session = Depends(get_db)):
    from app.login_guard import client_ip, log_attempt
    user = _sa_user(request, db)
    if not user:
        return _deny(require_login(request, db))
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        return RedirectResponse("/admin/sa/users", status_code=302)
    if target.id == user.id:
        return RedirectResponse("/admin/sa/users?notice=self", status_code=302)
    target.blocked = True
    db.query(models.LoginChallenge).filter(
        models.LoginChallenge.user_id == target.id,
        models.LoginChallenge.status == "pending",
    ).update({"status": "expired"}, synchronize_session=False)
    db.commit()
    log_attempt(
        db, email=target.email, ip=client_ip(request),
        user_agent=f"blocked by {user.email}",
        success=False, reason="sa_blocked",
    )
    return RedirectResponse(f"/admin/sa/users?notice=blocked&who={quote(target.email)}", status_code=302)


@router.post("/users/{user_id}/unblock")
def sa_unblock_user(user_id: str, request: Request, db: Session = Depends(get_db)):
    from app.login_guard import client_ip, log_attempt
    user = _sa_user(request, db)
    if not user:
        return _deny(require_login(request, db))
    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        return RedirectResponse("/admin/sa/users", status_code=302)
    target.blocked = False
    db.commit()
    log_attempt(
        db, email=target.email, ip=client_ip(request),
        user_agent=f"unblocked by {user.email}",
        success=True, reason="sa_unblocked",
    )
    return RedirectResponse(f"/admin/sa/users?notice=unblocked&who={quote(target.email)}", status_code=302)


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


@router.get("/settings", response_class=HTMLResponse)
def sa_settings(request: Request, db: Session = Depends(get_db), saved: str = "", err: str = ""):
    from app.drive_backup import oauth_ready
    from app.server_settings import (
        FCM_SERVICE_ACCOUNT_KEY, GOOGLE_CLIENT_ID_KEY, GOOGLE_CLIENT_SECRET_KEY,
        LOGIN_LOCKOUT_MINUTES_KEY, LOGIN_MAX_ATTEMPTS_KEY,
        fcm_service_account, get_plain, get_secret,
        login_lockout_minutes, login_max_attempts, rate_limit_enabled,
        recaptcha_ready, recaptcha_secret, recaptcha_site_key, recaptcha_wanted,
    )
    user = _sa_user(request, db)
    if not user:
        return _deny(require_login(request, db))
    redirect_uri = str(request.base_url).rstrip("/") + "/admin/storage/google/callback"
    gmail_redirect_uri = str(request.base_url).rstrip("/") + "/admin/expense-analyser/google/callback"
    fcm = fcm_service_account(db)
    return templates.TemplateResponse("sa_settings.html", _sa_ctx(
        request, user, "sa_settings",
        google_client_id=get_plain(db, GOOGLE_CLIENT_ID_KEY),
        google_has_secret=bool(get_secret(db, GOOGLE_CLIENT_SECRET_KEY) or (settings.GOOGLE_CLIENT_SECRET or "").strip()),
        google_ready=oauth_ready(db),
        redirect_uri=redirect_uri,
        gmail_redirect_uri=gmail_redirect_uri,
        saved=saved or None,
        err=err or None,
        env_fallback=bool((settings.GOOGLE_CLIENT_ID or "").strip() and (settings.GOOGLE_CLIENT_SECRET or "").strip()),
        fcm_ready=bool(fcm),
        fcm_has_secret=bool(get_secret(db, FCM_SERVICE_ACCOUNT_KEY) or fcm),
        fcm_project=(fcm or {}).get("project_id") or "",
        fcm_email=(fcm or {}).get("client_email") or "",
        fcm_env_fallback=bool((settings.FCM_SERVICE_ACCOUNT_JSON or "").strip()) and not get_secret(db, FCM_SERVICE_ACCOUNT_KEY),
        recaptcha_site_key=recaptcha_site_key(db),
        recaptcha_has_secret=bool(recaptcha_secret(db)),
        recaptcha_wanted=recaptcha_wanted(db),
        recaptcha_ready=recaptcha_ready(db),
        recaptcha_env_fallback=bool((settings.RECAPTCHA_SITE_KEY or "").strip() and (settings.RECAPTCHA_SECRET or "").strip()),
        rate_limit_on=rate_limit_enabled(db),
        login_max_attempts=login_max_attempts(db),
        login_lockout_minutes=login_lockout_minutes(db),
        rate_limit_env_fallback=not get_plain(db, LOGIN_MAX_ATTEMPTS_KEY) and not get_plain(db, LOGIN_LOCKOUT_MINUTES_KEY),
    ))


@router.post("/settings/google")
async def sa_settings_google(request: Request, db: Session = Depends(get_db)):
    from app.server_settings import GOOGLE_CLIENT_ID_KEY, GOOGLE_CLIENT_SECRET_KEY, put_plain, put_secret
    user = _sa_user(request, db)
    if not user:
        return _deny(require_login(request, db))
    form = await request.form()
    put_plain(db, GOOGLE_CLIENT_ID_KEY, str(form.get("client_id") or ""))
    put_secret(db, GOOGLE_CLIENT_SECRET_KEY, str(form.get("client_secret") or ""))
    db.commit()
    return RedirectResponse("/admin/sa/settings?saved=google", status_code=302)


@router.post("/settings/fcm")
async def sa_settings_fcm(request: Request, db: Session = Depends(get_db)):
    from app.server_settings import FCM_SERVICE_ACCOUNT_KEY, parse_service_account, put_secret
    user = _sa_user(request, db)
    if not user:
        return _deny(require_login(request, db))
    form = await request.form()
    raw = str(form.get("service_account") or "").strip()
    upload = form.get("service_account_file")
    filename = getattr(upload, "filename", None) or ""
    if filename and hasattr(upload, "read"):
        content = await upload.read()
        if content:
            raw = content.decode("utf-8", errors="replace").strip()
    if not raw:
        return RedirectResponse("/admin/sa/settings", status_code=302)
    if not parse_service_account(raw):
        return RedirectResponse("/admin/sa/settings?err=fcm", status_code=302)
    put_secret(db, FCM_SERVICE_ACCOUNT_KEY, raw)
    db.commit()
    return RedirectResponse("/admin/sa/settings?saved=fcm", status_code=302)


@router.post("/settings/recaptcha")
async def sa_settings_recaptcha(request: Request, db: Session = Depends(get_db)):
    from app.server_settings import (
        RECAPTCHA_ENABLED_KEY, RECAPTCHA_SECRET_KEY, RECAPTCHA_SITE_KEY_KEY,
        put_plain, put_secret, recaptcha_ready,
    )
    user = _sa_user(request, db)
    if not user:
        return _deny(require_login(request, db))
    form = await request.form()
    put_plain(db, RECAPTCHA_SITE_KEY_KEY, str(form.get("site_key") or ""))
    put_secret(db, RECAPTCHA_SECRET_KEY, str(form.get("secret") or ""))
    put_plain(db, RECAPTCHA_ENABLED_KEY, "1" if form.get("enabled") else "0")
    db.commit()
    if form.get("enabled") and not recaptcha_ready(db):
        return RedirectResponse("/admin/sa/settings?saved=recaptcha&err=recaptcha", status_code=302)
    return RedirectResponse("/admin/sa/settings?saved=recaptcha", status_code=302)


@router.post("/settings/lockout")
async def sa_settings_lockout(request: Request, db: Session = Depends(get_db)):
    from app.server_settings import (
        LOGIN_ATTEMPTS_MAX, LOGIN_ATTEMPTS_MIN, LOGIN_LOCKOUT_MAX, LOGIN_LOCKOUT_MIN,
        LOGIN_LOCKOUT_MINUTES_KEY, LOGIN_MAX_ATTEMPTS_KEY, LOGIN_RATE_LIMIT_ENABLED_KEY,
        clamp_int, put_plain,
    )
    user = _sa_user(request, db)
    if not user:
        return _deny(require_login(request, db))
    form = await request.form()
    put_plain(db, LOGIN_RATE_LIMIT_ENABLED_KEY, "1" if form.get("enabled") else "0")
    put_plain(db, LOGIN_MAX_ATTEMPTS_KEY, str(clamp_int(
        form.get("max_attempts"), settings.LOGIN_MAX_ATTEMPTS,
        LOGIN_ATTEMPTS_MIN, LOGIN_ATTEMPTS_MAX,
    )))
    put_plain(db, LOGIN_LOCKOUT_MINUTES_KEY, str(clamp_int(
        form.get("lockout_minutes"), settings.LOGIN_LOCKOUT_MINUTES,
        LOGIN_LOCKOUT_MIN, LOGIN_LOCKOUT_MAX,
    )))
    db.commit()
    return RedirectResponse("/admin/sa/settings?saved=lockout", status_code=302)
