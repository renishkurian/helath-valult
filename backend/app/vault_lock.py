"""Per-module vault locks — Password, Document, and Health vaults.

When a lock is on, opening that area requires the account authenticator
code and/or an email one-time code (same mail path as Vault Send OTP).
Unlock lasts UNLOCK_MINUTES in the web session (or a short JWT for the API).
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app import models, security
from app import mailer
from app import totp as totp_util

LOCKABLE = ("passwords", "locker", "health")
LOCK_LABELS = {
    "passwords": "Password Vault",
    "locker": "Document Vault",
    "health": "Health documents",
}
# Web paths that require an unlock when the module lock is on.
LOCK_ADMIN_PREFIXES: dict[str, tuple[str, ...]] = {
    "passwords": ("/admin/passwords",),
    "locker": ("/admin/locker",),
    "health": (
        "/admin/documents",
        "/admin/cards",
        "/admin/upload",
        "/admin/trash",
        "/admin/search",
        "/admin/shares",
        "/admin/care",
        "/admin/doctors",
        "/admin/reminders",
        "/admin/labs",
    ),
}
LOCK_API_PREFIXES: dict[str, tuple[str, ...]] = {
    "passwords": ("/vault",),
    "locker": ("/locker",),
    "health": ("/documents", "/cards", "/labs", "/share", "/reminders", "/health"),
}

UNLOCK_MINUTES = 15
EMAIL_OTP_MINUTES = 10
FLAG_ATTR = {
    "passwords": "lock_passwords",
    "locker": "lock_locker",
    "health": "lock_health",
}


def normalize_module(module: str | None) -> str | None:
    key = (module or "").strip().lower()
    return key if key in LOCKABLE else None


def is_locked(user: models.User | None, module: str) -> bool:
    key = normalize_module(module)
    if not user or not key:
        return False
    return bool(getattr(user, FLAG_ATTR[key], False))


def any_locked(user: models.User | None) -> bool:
    return any(is_locked(user, m) for m in LOCKABLE)


def can_use_locks(user: models.User, db: Session | None = None) -> bool:
    """Need authenticator and/or working outbound mail to unlock later."""
    if totp_util.is_enabled(user):
        return True
    return mailer.mail_ready(db)


def unlock_methods(user: models.User, db: Session | None = None) -> dict:
    return {
        "authenticator": totp_util.is_enabled(user),
        "email": mailer.mail_ready(db),
    }


def module_for_admin_path(path: str) -> str | None:
    for module, prefixes in LOCK_ADMIN_PREFIXES.items():
        for p in prefixes:
            if path == p or path.startswith(p + "/"):
                return module
    return None


def module_for_api_path(path: str) -> str | None:
    if path.startswith("/vault/public"):
        return None
    for module, prefixes in LOCK_API_PREFIXES.items():
        for p in prefixes:
            if path == p or path.startswith(p + "/"):
                return module
    return None


def _unlock_map(request: Request) -> dict:
    raw = request.session.get("vault_unlock") or {}
    if not isinstance(raw, dict):
        return {}
    now = time.time()
    clean = {}
    for k, exp in raw.items():
        if k not in LOCKABLE:
            continue
        try:
            if float(exp) > now:
                clean[k] = float(exp)
        except (TypeError, ValueError):
            continue
    request.session["vault_unlock"] = clean
    return clean


def is_unlocked(request: Request, module: str) -> bool:
    key = normalize_module(module)
    if not key:
        return True
    return key in _unlock_map(request)


def mark_unlocked(request: Request, module: str) -> float:
    key = normalize_module(module)
    if not key:
        raise ValueError("Unknown module")
    exp = time.time() + UNLOCK_MINUTES * 60
    data = _unlock_map(request)
    data[key] = exp
    request.session["vault_unlock"] = data
    return exp


def clear_unlock(request: Request, module: str | None = None) -> None:
    if module is None:
        request.session.pop("vault_unlock", None)
        return
    key = normalize_module(module)
    if not key:
        return
    data = _unlock_map(request)
    data.pop(key, None)
    request.session["vault_unlock"] = data


def set_lock(user: models.User, module: str, enabled: bool) -> None:
    key = normalize_module(module)
    if not key:
        raise ValueError("Unknown module")
    setattr(user, FLAG_ATTR[key], bool(enabled))


def create_unlock_token(user_id: str, module: str) -> str:
    key = normalize_module(module)
    if not key:
        raise ValueError("Unknown module")
    expire = datetime.utcnow() + timedelta(minutes=UNLOCK_MINUTES)
    return _jwt_unlock(user_id, key, expire)


def _jwt_unlock(user_id: str, module: str, expire: datetime) -> str:
    from jose import jwt
    from app.config import settings
    return jwt.encode(
        {"sub": user_id, "type": "vault_unlock", "mod": module, "exp": expire},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )


def verify_unlock_token(token: str | None, user_id: str, module: str) -> bool:
    key = normalize_module(module)
    if not token or not key:
        return False
    try:
        payload = security.decode_token(token)
    except ValueError:
        return False
    return (
        payload.get("type") == "vault_unlock"
        and payload.get("sub") == user_id
        and payload.get("mod") == key
    )


def _hash_otp(code: str) -> str:
    return hashlib.sha256(f"vault-lock:{code.strip()}".encode("utf-8")).hexdigest()


def issue_email_otp(request: Request, user: models.User, module: str, db: Session) -> bool:
    key = normalize_module(module)
    if not key or not mailer.mail_ready(db):
        return False
    code = f"{secrets.randbelow(1_000_000):06d}"
    request.session["vault_lock_email_otp"] = {
        "module": key,
        "hash": _hash_otp(code),
        "exp": time.time() + EMAIL_OTP_MINUTES * 60,
    }
    ok = mailer.send_email(
        user.email,
        f"Vault unlock code — {LOCK_LABELS[key]}",
        (
            f"Your one-time code to unlock {LOCK_LABELS[key]} is:\n\n"
            f"  {code}\n\n"
            f"It expires in {EMAIL_OTP_MINUTES} minutes. "
            f"If you did not request this, ignore this email.\n"
        ),
        db=db,
    )
    if not ok:
        request.session.pop("vault_lock_email_otp", None)
    return ok


def verify_email_otp(request: Request, module: str, code: str) -> bool:
    key = normalize_module(module)
    raw = request.session.get("vault_lock_email_otp") or {}
    if not key or not isinstance(raw, dict):
        return False
    if raw.get("module") != key:
        return False
    try:
        if float(raw.get("exp") or 0) < time.time():
            request.session.pop("vault_lock_email_otp", None)
            return False
    except (TypeError, ValueError):
        return False
    want = str(raw.get("hash") or "")
    got = _hash_otp(code or "")
    if not want or not hmac.compare_digest(want, got):
        return False
    request.session.pop("vault_lock_email_otp", None)
    return True


def verify_unlock_code(
    request: Request,
    user: models.User,
    module: str,
    code: str,
    *,
    db: Session | None = None,
    method: str = "auto",
) -> bool:
    """Accept authenticator and/or email OTP depending on method."""
    key = normalize_module(module)
    code = (code or "").strip()
    if not key or not code:
        return False
    method = (method or "auto").strip().lower()
    if method in ("auto", "totp", "authenticator") and totp_util.is_enabled(user):
        if totp_util.verify_code(user, code):
            return True
    if method in ("auto", "email"):
        if verify_email_otp(request, key, code):
            return True
    return False


def unlock_redirect(module: str, next_url: str = "") -> RedirectResponse:
    key = normalize_module(module) or "passwords"
    dest = next_url if (next_url or "").startswith("/admin/") and "://" not in next_url else ""
    q = f"module={quote(key)}"
    if dest:
        q += f"&next={quote(dest)}"
    return RedirectResponse(f"/admin/security/unlock?{q}", status_code=302)


def gate_admin_request(request: Request, user: models.User) -> RedirectResponse | None:
    """If this admin path is locked and not unlocked, redirect to unlock UI."""
    path = request.url.path
    if path.startswith("/admin/security"):
        return None
    module = module_for_admin_path(path)
    if not module or not is_locked(user, module):
        return None
    if is_unlocked(request, module):
        return None
    return unlock_redirect(module, path + (("?" + request.url.query) if request.url.query else ""))


def require_api_unlock(
    request: Request,
    user: models.User,
    module: str,
    db: Session | None = None,
) -> None:
    """Raise 423 if API module is locked and no valid unlock token is present."""
    key = normalize_module(module)
    if not key or not is_locked(user, key):
        return
    token = request.headers.get("X-Vault-Unlock") or request.headers.get("x-vault-unlock")
    if verify_unlock_token(token, user.id, key):
        return
    raise HTTPException(
        status_code=423,
        detail={
            "code": "vault_locked",
            "module": key,
            "label": LOCK_LABELS[key],
            "message": f"{LOCK_LABELS[key]} is locked. Verify with authenticator or email OTP.",
            "methods": unlock_methods(user, db),
        },
    )


def issue_api_email_otp(db: Session, user: models.User, module: str) -> bool:
    key = normalize_module(module)
    if not key or not mailer.mail_ready(db):
        return False
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.query(models.VaultLockEmailOtp).filter(
        models.VaultLockEmailOtp.user_id == user.id,
        models.VaultLockEmailOtp.module == key,
    ).delete(synchronize_session=False)
    db.add(models.VaultLockEmailOtp(
        user_id=user.id,
        module=key,
        code_hash=_hash_otp(code),
        expires_at=datetime.utcnow() + timedelta(minutes=EMAIL_OTP_MINUTES),
    ))
    db.commit()
    ok = mailer.send_email(
        user.email,
        f"Vault unlock code — {LOCK_LABELS[key]}",
        (
            f"Your one-time code to unlock {LOCK_LABELS[key]} is:\n\n"
            f"  {code}\n\n"
            f"It expires in {EMAIL_OTP_MINUTES} minutes. "
            f"If you did not request this, ignore this email.\n"
        ),
        db=db,
    )
    if not ok:
        db.query(models.VaultLockEmailOtp).filter(
            models.VaultLockEmailOtp.user_id == user.id,
            models.VaultLockEmailOtp.module == key,
        ).delete(synchronize_session=False)
        db.commit()
    return ok


def verify_api_email_otp(db: Session, user: models.User, module: str, code: str) -> bool:
    key = normalize_module(module)
    if not key:
        return False
    row = (
        db.query(models.VaultLockEmailOtp)
        .filter(
            models.VaultLockEmailOtp.user_id == user.id,
            models.VaultLockEmailOtp.module == key,
        )
        .order_by(models.VaultLockEmailOtp.created_at.desc())
        .first()
    )
    if not row or row.expires_at < datetime.utcnow():
        return False
    if not hmac.compare_digest(row.code_hash, _hash_otp(code or "")):
        return False
    db.delete(row)
    db.commit()
    return True


def verify_api_unlock_code(
    db: Session,
    user: models.User,
    module: str,
    code: str,
    *,
    method: str = "auto",
) -> bool:
    key = normalize_module(module)
    code = (code or "").strip()
    if not key or not code:
        return False
    method = (method or "auto").strip().lower()
    if method in ("auto", "totp", "authenticator") and totp_util.is_enabled(user):
        if totp_util.verify_code(user, code):
            return True
    if method in ("auto", "email"):
        if verify_api_email_otp(db, user, key, code):
            return True
    return False
