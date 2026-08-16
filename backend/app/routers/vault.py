"""Password Vault — Bitwarden-style items, generator, TOTP, health, Send."""
from __future__ import annotations

import json
import math
import secrets
import string
import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app import models, schemas, crypto, security
from app.deps import require_enabled_module, get_current_user, require_owner, vault_id
from app.templating import setup_templates

router = APIRouter(prefix="/vault", tags=["vault"], dependencies=[Depends(require_enabled_module("passwords"))])
# Token links must stay anonymous — do not attach module/auth deps here.
public_router = APIRouter(prefix="/vault", tags=["vault"])
templates = setup_templates()

_ALLOWED_TYPES = {t.value for t in models.VaultItemType}
_COMMON = {
    "password", "password1", "password123", "123456", "12345678", "123456789",
    "qwerty", "abc123", "letmein", "welcome", "admin", "iloveyou", "monkey",
    "dragon", "master", "login", "passw0rd", "changeme",
}
_WORDS = (
    "able acid also area army away baby ball band bank base bath bear beat "
    "bell best bird blue boat body book born both burn busy call calm camp "
    "card care case city club coat cold come cook cool copy corn cost dark "
    "data deal deep desk door down draw drop dust each east easy edge else "
    "even ever face fact fall farm fast fear feel file fill film find fire "
    "fish five flat flow food foot form four free from full game gate give "
    "glad gold gone good gray grow half hall hand hard have head hear heat "
    "help here high hill hold home hope hour idea iron item join just keep "
    "kind king know lake land last late lead left life lift like line list "
    "live load long look lost love made mail main make many mark meet mile "
    "milk mind mine miss moon more most move much must name near need news "
    "next nice nine none nose note open over page park part pass path pick "
    "pink plan play plus pond port post pull push rain read real rest rich "
    "ride ring rise road rock roll room rose rule safe sail same sand save "
    "seat seed seem self sell send ship shop show side sign silk sing size "
    "skin slip slow snow soft soil some song sort star stay step stop such "
    "sure take talk tall team tell tent term test than that them then they "
    "thin this thus tide time tiny told tone tool town tree trip true turn "
    "type unit upon used user very view wait walk wall want warm wash wave "
    "weak week well west what when wide wife wild will wind wine wing wire "
    "wise wish with wood word work yard year your zero zone"
).split()


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    if request.client:
        return (request.client.host or "")[:64]
    return None


def _uris_load(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return [str(u) for u in data if u]
    except json.JSONDecodeError:
        pass
    return [u.strip() for u in raw.split(",") if u.strip()]


def _uris_dump(uris: list[str] | None) -> str | None:
    if not uris:
        return None
    cleaned = [u.strip() for u in uris if u and u.strip()]
    return json.dumps(cleaned) if cleaned else None


def _to_out(item: models.VaultItem, *, active_send_count: int = 0) -> schemas.VaultItemOut:
    totp = crypto.decrypt_text(item.totp_secret_enc)
    return schemas.VaultItemOut(
        id=item.id,
        folder_id=item.folder_id,
        item_type=item.item_type,
        name=item.name,
        favorite=bool(item.favorite),
        username=item.username,
        password=crypto.decrypt_text(item.password_enc),
        totp_secret=totp,
        has_totp=bool(totp),
        uris=_uris_load(item.uris),
        notes=crypto.decrypt_text(item.notes_enc),
        cardholder_name=item.cardholder_name,
        card_brand=item.card_brand,
        card_number=crypto.decrypt_text(item.card_number_enc),
        card_exp_month=item.card_exp_month,
        card_exp_year=item.card_exp_year,
        card_cvv=crypto.decrypt_text(item.card_cvv_enc),
        identity_title=item.identity_title,
        first_name=item.first_name,
        middle_name=item.middle_name,
        last_name=item.last_name,
        email=item.email,
        phone=item.phone,
        address1=item.address1,
        address2=item.address2,
        city=item.city,
        state=item.state,
        postal_code=item.postal_code,
        country=item.country,
        ssn=crypto.decrypt_text(item.ssn_enc),
        license_number=crypto.decrypt_text(item.license_number_enc),
        passport_number=crypto.decrypt_text(item.passport_number_enc),
        password_changed_at=item.password_changed_at,
        deleted_at=item.deleted_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
        active_send_count=max(0, int(active_send_count or 0)),
    )


def _owned_item(
    item_id: str,
    db: Session,
    user: models.User,
    *,
    include_deleted: bool = False,
) -> models.VaultItem:
    q = db.query(models.VaultItem).filter(
        models.VaultItem.id == item_id,
        models.VaultItem.user_id == vault_id(user),
    )
    item = q.first()
    if not item or (item.deleted_at and not include_deleted):
        raise HTTPException(status_code=404, detail="Item not found")
    return item


def _owned_folder(folder_id: str | None, db: Session, user: models.User) -> str | None:
    if not folder_id:
        return None
    folder = db.query(models.VaultFolder).filter(
        models.VaultFolder.id == folder_id,
        models.VaultFolder.user_id == vault_id(user),
    ).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    return folder.id


def _score(password: str) -> int:
    if not password:
        return 0
    if password.lower() in _COMMON or len(password) < 8:
        return 0
    classes = 0
    classes += any(c.islower() for c in password)
    classes += any(c.isupper() for c in password)
    classes += any(c.isdigit() for c in password)
    classes += any(c in string.punctuation for c in password)
    entropy = len(password) * math.log2(max(classes * 10, 2))
    if entropy < 28:
        return 1
    if entropy < 36:
        return 2
    if entropy < 60:
        return 3
    return 4


def _is_weak(password: str | None) -> bool:
    if not password:
        return True
    return _score(password) <= 1


def _is_old(item: models.VaultItem) -> bool:
    stamp = item.password_changed_at or item.created_at
    if not stamp:
        return False
    return stamp < datetime.utcnow() - timedelta(days=365)


# ---------- Folders ----------
@router.get("/folders", response_model=list[schemas.VaultFolderOut])
def list_folders(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    vid = vault_id(current_user)
    folders = db.query(models.VaultFolder).filter(models.VaultFolder.user_id == vid).order_by(models.VaultFolder.name).all()
    out = []
    for f in folders:
        count = db.query(models.VaultItem).filter(
            models.VaultItem.folder_id == f.id,
            models.VaultItem.deleted_at.is_(None),
        ).count()
        out.append(schemas.VaultFolderOut(id=f.id, name=f.name, item_count=count, created_at=f.created_at))
    return out


@router.post("/folders", response_model=schemas.VaultFolderOut, status_code=201)
def create_folder(
    body: schemas.VaultFolderIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    folder = models.VaultFolder(user_id=vault_id(current_user), name=body.name.strip())
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return schemas.VaultFolderOut(id=folder.id, name=folder.name, item_count=0, created_at=folder.created_at)


@router.patch("/folders/{folder_id}", response_model=schemas.VaultFolderOut)
def rename_folder(
    folder_id: str,
    body: schemas.VaultFolderIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    folder = db.query(models.VaultFolder).filter(
        models.VaultFolder.id == folder_id,
        models.VaultFolder.user_id == vault_id(current_user),
    ).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    folder.name = body.name.strip()
    db.commit()
    db.refresh(folder)
    count = db.query(models.VaultItem).filter(
        models.VaultItem.folder_id == folder.id, models.VaultItem.deleted_at.is_(None)
    ).count()
    return schemas.VaultFolderOut(id=folder.id, name=folder.name, item_count=count, created_at=folder.created_at)


@router.delete("/folders/{folder_id}", status_code=204)
def delete_folder(
    folder_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    folder = db.query(models.VaultFolder).filter(
        models.VaultFolder.id == folder_id,
        models.VaultFolder.user_id == vault_id(current_user),
    ).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    db.query(models.VaultItem).filter(models.VaultItem.folder_id == folder.id).update({"folder_id": None})
    db.delete(folder)
    db.commit()


# ---------- Generator / health / trash (static paths first) ----------
@router.post("/generate", response_model=schemas.VaultGenerateOut)
def generate_password(
    body: schemas.VaultGenerateIn,
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    if body.kind == "passphrase":
        words = [secrets.choice(_WORDS) for _ in range(body.word_count)]
        if body.uppercase:
            words[0] = words[0].capitalize()
        if body.numbers:
            words.append(str(secrets.randbelow(90) + 10))
        value = (body.separator or "-").join(words)
        return schemas.VaultGenerateOut(value=value, score=_score(value), length=len(value))

    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    symbols = "!@#$%^&*-_=+"
    if body.avoid_ambiguous:
        lower = lower.replace("l", "").replace("o", "")
        upper = upper.replace("I", "").replace("O", "")
        digits = digits.replace("0", "").replace("1", "")
    pools = []
    if body.lowercase:
        pools.append(lower)
    if body.uppercase:
        pools.append(upper)
    if body.numbers:
        pools.append(digits)
    if body.symbols:
        pools.append(symbols)
    if not pools:
        pools = [lower, upper, digits]
    alphabet = "".join(pools)
    chars = [secrets.choice(p) for p in pools]
    chars += [secrets.choice(alphabet) for _ in range(max(0, body.length - len(chars)))]
    secrets.SystemRandom().shuffle(chars)
    value = "".join(chars[: body.length])
    return schemas.VaultGenerateOut(value=value, score=_score(value), length=len(value))


@router.get("/health", response_model=schemas.VaultHealthOut)
def password_health(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    items = (
        db.query(models.VaultItem)
        .filter(
            models.VaultItem.user_id == vault_id(current_user),
            models.VaultItem.deleted_at.is_(None),
            models.VaultItem.item_type == models.VaultItemType.login.value,
        )
        .all()
    )
    weak, reused, no_totp, old = [], [], [], []
    by_password: dict[str, list[models.VaultItem]] = {}
    for item in items:
        pw = crypto.decrypt_text(item.password_enc) or ""
        if _is_weak(pw):
            weak.append(schemas.VaultHealthIssue(item_id=item.id, name=item.name, username=item.username, reason="weak"))
        if not item.totp_secret_enc:
            no_totp.append(schemas.VaultHealthIssue(item_id=item.id, name=item.name, username=item.username, reason="no_totp"))
        if _is_old(item):
            old.append(schemas.VaultHealthIssue(item_id=item.id, name=item.name, username=item.username, reason="old"))
        if pw:
            by_password.setdefault(pw, []).append(item)
    for group in by_password.values():
        if len(group) < 2:
            continue
        for item in group:
            reused.append(schemas.VaultHealthIssue(
                item_id=item.id, name=item.name, username=item.username, reason="reused"
            ))
    return schemas.VaultHealthOut(
        weak=weak, reused=reused, no_totp=no_totp, old=old, total_logins=len(items)
    )


@router.get("/trash", response_model=list[schemas.VaultItemOut])
def list_trash(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    rows = (
        db.query(models.VaultItem)
        .filter(models.VaultItem.user_id == vault_id(current_user), models.VaultItem.deleted_at.isnot(None))
        .order_by(models.VaultItem.deleted_at.desc())
        .all()
    )
    return [_to_out(r) for r in rows]


@router.post("/trash/empty", status_code=204)
def empty_trash(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    rows = db.query(models.VaultItem).filter(
        models.VaultItem.user_id == vault_id(current_user),
        models.VaultItem.deleted_at.isnot(None),
    ).all()
    for row in rows:
        db.delete(row)
    db.commit()


# ---------- Sends ----------
def _send_is_active(row: models.VaultSend, *, now: datetime | None = None) -> bool:
    """True when a share can still be opened (not revoked / expired / maxed out)."""
    if row.revoked:
        return False
    stamp = now or datetime.utcnow()
    if row.expires_at and row.expires_at < stamp:
        return False
    if row.max_views is not None and (row.view_count or 0) >= row.max_views:
        return False
    return True


def _active_send_counts(user_id: str, db: Session) -> dict[str, int]:
    """Map vault item_id → count of still-open Send links for that login."""
    rows = (
        db.query(models.VaultSend)
        .filter(
            models.VaultSend.user_id == user_id,
            models.VaultSend.revoked.is_(False),
        )
        .all()
    )
    now = datetime.utcnow()
    counts: dict[str, int] = {}
    for row in rows:
        if not _send_is_active(row, now=now):
            continue
        item_id = _payload(row).get("item_id")
        if isinstance(item_id, str) and item_id.strip():
            key = item_id.strip()
            counts[key] = counts.get(key, 0) + 1
    return counts


def _send_out(row: models.VaultSend) -> schemas.VaultSendOut:
    data = _payload(row)
    item_id = data.get("item_id") if isinstance(data.get("item_id"), str) else None
    return schemas.VaultSendOut(
        id=row.id,
        token=row.token,
        name=row.name,
        send_type=row.send_type,
        expires_at=row.expires_at,
        max_views=row.max_views,
        view_count=row.view_count or 0,
        revoked=bool(row.revoked),
        has_pin=bool(row.pin_hash),
        item_id=item_id,
        requires_totp=bool(data.get("require_totp") and data.get("totp_secret")),
        requires_grant=bool(data.get("require_grant")),
        requires_email_otp=bool(data.get("require_email_otp")),
        created_at=row.created_at,
    )


def _load_valid_send(token: str, db: Session) -> models.VaultSend:
    row = db.query(models.VaultSend).filter(models.VaultSend.token == token).first()
    if not row or row.revoked:
        raise HTTPException(status_code=404, detail="Send not found")
    if row.expires_at and row.expires_at < datetime.utcnow():
        raise HTTPException(status_code=410, detail="This send has expired")
    if row.max_views is not None and (row.view_count or 0) >= row.max_views:
        raise HTTPException(status_code=410, detail="This send has reached its view limit")
    return row


_SEND_GONE = {
    "This send has reached its view limit": {
        "title": "view limit reached",
        "eyebrow": "Send · one-time link",
        "heading": "This link has reached its view limit",
        "body": (
            "Shared links can only be opened a set number of times. "
            "That limit's been used, so the vault door has sealed — "
            "the content isn't recoverable, even by us."
        ),
        "tag": "Sealed · nothing recoverable",
    },
    "This send has expired": {
        "title": "link expired",
        "eyebrow": "Send · timed link",
        "heading": "This link has expired",
        "body": (
            "This send passed its expiry time, so the vault door has sealed. "
            "Ask the sender for a fresh link if you still need access."
        ),
        "tag": "Sealed · nothing recoverable",
    },
    "Send not found": {
        "title": "send not found",
        "eyebrow": "Send · unavailable",
        "heading": "This send is no longer available",
        "body": (
            "The link may have been revoked or never existed. "
            "Ask the sender for a new one if you still need access."
        ),
        "tag": "Sealed · nothing recoverable",
    },
}


def _send_gone_page(request: Request, exc: HTTPException) -> HTMLResponse:
    """Styled sealed-door page for public send HTML routes."""
    detail = str(exc.detail)
    copy = _SEND_GONE.get(detail) or {
        "title": "unavailable",
        "eyebrow": "Send · unavailable",
        "heading": detail,
        "body": "This send can't be opened. Ask the sender for a new link if you still need access.",
        "tag": "Sealed · nothing recoverable",
    }
    return templates.TemplateResponse(
        request,
        "vault_send_gone.html",
        copy,
        status_code=exc.status_code,
    )


def _payload(row: models.VaultSend) -> dict:
    raw = crypto.decrypt_text(row.payload_enc) or "{}"
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {"text": str(data)}
    except json.JSONDecodeError:
        return {"text": raw}


@router.get("/sends", response_model=list[schemas.VaultSendOut])
def list_sends(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    rows = (
        db.query(models.VaultSend)
        .filter(models.VaultSend.user_id == vault_id(current_user))
        .order_by(models.VaultSend.created_at.desc())
        .all()
    )
    return [_send_out(r) for r in rows]


def list_item_sends(item_id: str, db: Session, current_user: models.User) -> list[schemas.VaultSendOut]:
    """Active sends that snapshot a specific vault login (not revoked/expired/maxed)."""
    now = datetime.utcnow()
    out: list[schemas.VaultSendOut] = []
    for s in list_sends(db=db, current_user=current_user):
        if s.item_id != item_id or s.revoked:
            continue
        if s.expires_at and s.expires_at < now:
            continue
        if s.max_views is not None and (s.view_count or 0) >= s.max_views:
            continue
        out.append(s)
    return out


@router.post("/items/{item_id}/sends/revoke-all", status_code=204)
def revoke_all_item_sends(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Revoke every active share link for this login."""
    require_owner(current_user)
    _owned_item(item_id, db, current_user)
    rows = db.query(models.VaultSend).filter(
        models.VaultSend.user_id == vault_id(current_user),
        models.VaultSend.revoked.is_(False),
    ).all()
    n = 0
    for row in rows:
        data = _payload(row)
        if data.get("item_id") == item_id:
            row.revoked = True
            n += 1
    db.commit()
    return Response(status_code=204)


@router.post("/sends", response_model=schemas.VaultSendOut, status_code=201)
def create_send(
    body: schemas.VaultSendCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    payload: dict
    send_type = body.send_type if body.send_type in ("text", "login") else "text"
    if send_type == "login":
        if not body.item_id:
            raise HTTPException(status_code=400, detail="item_id is required for a login send")
        item = _owned_item(body.item_id, db, current_user)
        out = _to_out(item)
        payload = {
            "item_id": out.id,
            "username": out.username,
            "password": out.password,
            "uris": out.uris,
            "name": out.name,
        }
        if body.include_totp and out.totp_secret:
            payload["totp_secret"] = out.totp_secret
            payload["require_totp"] = True
        if body.require_grant:
            payload["require_grant"] = True
        if body.require_email_otp:
            emails = _normalize_allowed_emails(body.allowed_emails)
            payload["require_email_otp"] = True
            if emails:
                payload["allowed_emails"] = emails
    else:
        if not (body.text or "").strip():
            raise HTTPException(status_code=400, detail="text is required")
        payload = {"text": body.text.strip()}
        if body.require_grant:
            payload["require_grant"] = True
        if body.require_email_otp:
            emails = _normalize_allowed_emails(body.allowed_emails)
            payload["require_email_otp"] = True
            if emails:
                payload["allowed_emails"] = emails
    pin = (body.pin or "").strip() or None
    if pin and len(pin) < 4:
        raise HTTPException(status_code=400, detail="PIN must be at least 4 characters")
    row = models.VaultSend(
        user_id=vault_id(current_user),
        token=secrets.token_urlsafe(24),
        name=body.name.strip(),
        send_type=send_type,
        payload_enc=crypto.encrypt_text(json.dumps(payload)),
        notes_enc=crypto.encrypt_text(body.notes),
        pin_hash=security.hash_password(pin) if pin else None,
        expires_at=datetime.utcnow() + timedelta(hours=body.expires_in_hours),
        max_views=body.max_views,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _send_out(row)


@router.get("/sends/{send_id}", response_model=schemas.VaultSendOut)
def get_send(send_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    row = db.query(models.VaultSend).filter(
        models.VaultSend.id == send_id,
        models.VaultSend.user_id == vault_id(current_user),
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Send not found")
    return _send_out(row)


@router.delete("/sends/{send_id}", status_code=204)
def revoke_send(send_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    row = db.query(models.VaultSend).filter(
        models.VaultSend.id == send_id,
        models.VaultSend.user_id == vault_id(current_user),
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Send not found")
    row.revoked = True
    db.commit()


def _normalize_allowed_emails(raw) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        parts = raw.replace(";", ",").replace("\n", ",").split(",")
    else:
        parts = list(raw)
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        e = (p or "").strip().lower()
        if not e or "@" not in e or e in seen:
            continue
        seen.add(e)
        out.append(e)
    return out[:40]


def _record_send_view(
    row: models.VaultSend,
    request: Request,
    db: Session,
    *,
    action: str = "view",
    email: str | None = None,
    request_id: str | None = None,
) -> None:
    db.add(models.VaultSendAccess(
        send_id=row.id,
        action=action,
        ip=_client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:400] or None,
        email=(email or None),
        request_id=request_id,
    ))
    if action == "password_viewed":
        row.view_count = (row.view_count or 0) + 1
        if request_id:
            req = db.query(models.VaultSendRequest).filter(models.VaultSendRequest.id == request_id).first()
            if req and req.send_id == row.id and req.viewed_at is None:
                req.viewed_at = datetime.utcnow()
    else:
        row.view_count = (row.view_count or 0) + 1
    db.commit()


def _send_totp_gate(data: dict, code: Optional[str]) -> tuple[bool, bool]:
    """Returns (needs_totp_gate, code_ok)."""
    secret = (data.get("totp_secret") or "").strip()
    if not secret or not data.get("require_totp"):
        return False, True
    return True, security.verify_totp(secret, code or "")


def _otpauth_for_send(name: str, secret: str) -> tuple[str, str]:
    from app import totp as totp_util
    label = (name or "Vault Send").replace(" ", "_")[:64]
    url = totp_util.otpauth_url(label, secret.replace(" ", "").upper())
    return url, totp_util.qr_data_uri(url)


def _send_req_cookie_name(token: str) -> str:
    # vsrs_ = session-scoped grant cookie (browser close clears access).
    return f"vsrs_{token[:32]}"


def _read_request_cookie(request: Request, token: str) -> str | None:
    rid = (request.cookies.get(_send_req_cookie_name(token)) or "").strip()
    return rid or None


def _guest_request(
    request: Request, send: models.VaultSend, db: Session
) -> models.VaultSendRequest | None:
    rid = _read_request_cookie(request, send.token)
    if not rid:
        return None
    return (
        db.query(models.VaultSendRequest)
        .filter(
            models.VaultSendRequest.id == rid,
            models.VaultSendRequest.send_id == send.id,
        )
        .first()
    )


def _grant_unlocked(request: Request, send: models.VaultSend, data: dict, db: Session) -> bool:
    """True when secrets may be revealed (no grant gate, or this browser was granted)."""
    if not data.get("require_grant"):
        return True
    row = _guest_request(request, send, db)
    return bool(row and row.status == "granted")


def _email_otp_cookie_name(token: str) -> str:
    return f"vse_{token[:32]}"


def _email_otp_unlocked(request: Request, send: models.VaultSend, data: dict) -> tuple[bool, str | None]:
    if not data.get("require_email_otp"):
        return True, None
    email = (request.cookies.get(_email_otp_cookie_name(send.token)) or "").strip().lower()
    if not email or "@" not in email:
        return False, None
    allowed = _normalize_allowed_emails(data.get("allowed_emails") or [])
    if allowed and email not in allowed:
        return False, None
    return True, email


def _validate_guest_email(data: dict, email: str, db: Session) -> str | None:
    """Return error code or None if ok.

    Always: valid email format.
    If allowed_emails is set: must be on that list. Otherwise any email is fine.
    """
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return "email"
    allowed = _normalize_allowed_emails(data.get("allowed_emails") or [])
    if allowed and email not in allowed:
        return "not_allowed"
    return None


@public_router.get("/public/{token}", response_model=schemas.VaultSendPublicOut)
def public_send_json(
    token: str,
    request: Request,
    pin: Optional[str] = None,
    totp: Optional[str] = None,
    db: Session = Depends(get_db),
):
    row = _load_valid_send(token, db)
    data = _payload(row)
    require_grant = bool(data.get("require_grant"))
    if row.pin_hash and not (pin and security.verify_password(pin, row.pin_hash)):
        return schemas.VaultSendPublicOut(
            name=row.name,
            send_type=row.send_type,
            expires_at=row.expires_at,
            has_pin=True,
            pin_required=True,
            request_access_enabled=require_grant,
        )
    if not _grant_unlocked(request, row, data, db):
        return schemas.VaultSendPublicOut(
            name=row.name,
            send_type=row.send_type,
            expires_at=row.expires_at,
            has_pin=bool(row.pin_hash),
            pin_required=False,
            grant_required=True,
            request_access_enabled=True,
        )
    email_ok, verified_email = _email_otp_unlocked(request, row, data)
    if not email_ok:
        return schemas.VaultSendPublicOut(
            name=row.name,
            send_type=row.send_type,
            expires_at=row.expires_at,
            has_pin=bool(row.pin_hash),
            pin_required=False,
            email_otp_required=True,
            request_access_enabled=require_grant,
        )
    needs_totp, totp_ok = _send_totp_gate(data, totp)
    if needs_totp and not totp_ok:
        return schemas.VaultSendPublicOut(
            name=row.name,
            send_type=row.send_type,
            expires_at=row.expires_at,
            has_pin=bool(row.pin_hash),
            pin_required=False,
            totp_required=True,
            request_access_enabled=require_grant,
        )
    notes = crypto.decrypt_text(row.notes_enc)
    guest_req = _guest_request(request, row, db) if require_grant else None
    _record_send_view(
        row, request, db,
        action="password_viewed",
        email=verified_email,
        request_id=guest_req.id if guest_req else None,
    )
    return schemas.VaultSendPublicOut(
        name=row.name,
        send_type=row.send_type,
        text=data.get("text"),
        username=data.get("username"),
        password=data.get("password"),
        uris=data.get("uris") or [],
        notes=notes,
        expires_at=row.expires_at,
        has_pin=bool(row.pin_hash),
        pin_required=False,
        totp_required=False,
        request_access_enabled=require_grant,
    )


@public_router.get("/public/{token}/page", response_class=HTMLResponse)
def public_send_page(
    token: str,
    request: Request,
    pin: Optional[str] = None,
    totp: Optional[str] = None,
    req_ok: Optional[str] = None,
    req_err: Optional[str] = None,
    otp_sent: Optional[str] = None,
    otp_err: Optional[str] = None,
    otp_email: Optional[str] = None,
    db: Session = Depends(get_db),
):
    try:
        row = _load_valid_send(token, db)
    except HTTPException as exc:
        return _send_gone_page(request, exc)
    data = _payload(row)
    require_grant = bool(data.get("require_grant"))
    guest_req = _guest_request(request, row, db) if require_grant else None
    email_ok, verified_email = _email_otp_unlocked(request, row, data)
    ctx_extra = {
        "request_ok": bool(req_ok),
        "request_err": (req_err or "").strip(),
        "request_access_enabled": require_grant,
        "grant_pending": bool(guest_req and guest_req.status in ("pending", "seen")),
        "grant_denied": bool(guest_req and guest_req.status == "dismissed"),
        "guest_request_id": guest_req.id if guest_req else "",
        "video_status": (guest_req.video_status if guest_req else "none") or "none",
        "email_otp_enabled": bool(data.get("require_email_otp")),
        "email_otp_required": bool(data.get("require_email_otp")) and not email_ok,
        "email_hint": ", ".join(_normalize_allowed_emails(data.get("allowed_emails") or [])[:3]),
        "otp_sent": bool(otp_sent),
        "otp_error": (otp_err or "").strip() or None,
        "otp_email": (otp_email or verified_email or "").strip(),
        "show_request_panel": False,
    }
    pin_ok = not row.pin_hash or (pin and security.verify_password(pin, row.pin_hash))
    if not pin_ok:
        return templates.TemplateResponse(request, "vault_send_public.html", {
            "send": row, "token": token, "pin_required": True, "totp_required": False,
            "grant_required": False, "email_otp_required": False, "payload": None, "notes": None,
            "error": bool(pin), "totp_error": False, "pin_value": pin or "", **ctx_extra,
        })
    if require_grant and not (guest_req and guest_req.status == "granted"):
        ctx_extra["show_request_panel"] = True
        return templates.TemplateResponse(request, "vault_send_public.html", {
            "send": row, "token": token, "pin_required": False, "totp_required": False,
            "grant_required": True, "email_otp_required": False, "payload": None, "notes": None,
            "error": False, "totp_error": False, "pin_value": pin or "", **ctx_extra,
        })
    if not email_ok:
        return templates.TemplateResponse(request, "vault_send_public.html", {
            "send": row, "token": token, "pin_required": False, "totp_required": False,
            "grant_required": False, "payload": None, "notes": None,
            "error": False, "totp_error": False, "pin_value": pin or "", **ctx_extra,
        })
    needs_totp, totp_ok = _send_totp_gate(data, totp)
    if needs_totp and not totp_ok:
        return templates.TemplateResponse(request, "vault_send_public.html", {
            "send": row, "token": token, "pin_required": False, "totp_required": True,
            "grant_required": False, "email_otp_required": False,
            "payload": {"name": data.get("name") or row.name},
            "notes": None, "error": False, "totp_error": bool(totp),
            "pin_value": pin or "", **ctx_extra,
        })
    notes = crypto.decrypt_text(row.notes_enc)
    shown = {k: v for k, v in data.items() if k not in (
        "totp_secret", "require_grant", "require_totp", "require_email_otp",
        "allowed_emails", "require_vault_user_email",
    )}
    _record_send_view(
        row, request, db,
        action="password_viewed",
        email=verified_email,
        request_id=guest_req.id if guest_req else None,
    )
    ctx_extra["email_otp_required"] = False
    # Granted / unlocked: never show the Request access panel again this session.
    ctx_extra["grant_required"] = False
    ctx_extra["grant_pending"] = False
    ctx_extra["request_ok"] = False
    ctx_extra["request_err"] = ""
    ctx_extra["show_request_panel"] = False
    return templates.TemplateResponse(request, "vault_send_public.html", {
        "send": row, "token": token, "pin_required": False, "totp_required": False,
        "grant_required": False, "payload": shown, "notes": notes,
        "error": False, "totp_error": False, "pin_value": pin or "", **ctx_extra,
    })


@public_router.get("/public/{token}/qr", response_class=HTMLResponse)
def public_send_qr_page(
    token: str,
    request: Request,
    pin: Optional[str] = None,
    req_ok: Optional[str] = None,
    req_err: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Separate authenticator setup page — QR/key only, no password."""
    try:
        row = _load_valid_send(token, db)
    except HTTPException as exc:
        return _send_gone_page(request, exc)
    data = _payload(row)
    secret = (data.get("totp_secret") or "").strip()
    if not secret or not data.get("require_totp"):
        return HTMLResponse("<h1>No authenticator setup for this send</h1>", status_code=404)
    require_grant = bool(data.get("require_grant"))
    guest_req = _guest_request(request, row, db) if require_grant else None
    ctx_extra = {
        "request_ok": bool(req_ok),
        "request_err": (req_err or "").strip(),
        "request_access_enabled": require_grant,
        "grant_pending": bool(guest_req and guest_req.status in ("pending", "seen")),
        "grant_denied": bool(guest_req and guest_req.status == "dismissed"),
        "grant_required": require_grant and not (guest_req and guest_req.status == "granted"),
        "show_request_panel": False,
    }
    pin_ok = not row.pin_hash or (pin and security.verify_password(pin, row.pin_hash))
    if not pin_ok:
        return templates.TemplateResponse(request, "vault_send_qr.html", {
            "send": row, "token": token, "pin_required": True, "error": bool(pin),
            "totp_secret": None, "otpauth_qr": None, **ctx_extra,
        })
    if ctx_extra["grant_required"]:
        ctx_extra["show_request_panel"] = True
        return templates.TemplateResponse(request, "vault_send_qr.html", {
            "send": row, "token": token, "pin_required": False, "error": False,
            "totp_secret": None, "otpauth_qr": None, **ctx_extra,
        })
    _url, otpauth_qr = _otpauth_for_send(row.name, secret)
    return templates.TemplateResponse(request, "vault_send_qr.html", {
        "send": row, "token": token, "pin_required": False, "error": False,
        "totp_secret": secret, "otpauth_qr": otpauth_qr, **ctx_extra,
    })


def _notify_send_request(
    db: Session,
    owner_id: str,
    req: models.VaultSendRequest,
    send_name: str,
    send_token: str = "",
) -> int:
    from app.push import send_fcm
    from app.send_request_events import send_request_hub
    from app.server_settings import fcm_service_account

    # Live update any open web admin tabs (SSE), independent of FCM.
    item_id = None
    if req.send_id:
        send_row = db.query(models.VaultSend).filter(models.VaultSend.id == req.send_id).first()
        if send_row:
            raw = _payload(send_row).get("item_id")
            if isinstance(raw, str) and raw.strip():
                item_id = raw.strip()
    send_request_hub.publish(
        owner_id,
        {
            "id": req.id,
            "send_id": req.send_id,
            "send_name": send_name,
            "send_token": send_token,
            "item_id": item_id,
            "name": req.name,
            "email": req.email,
            "ip": req.ip,
            "has_photo": bool(req.photo_path),
            "status": req.status,
            "created_at": req.created_at.isoformat() if req.created_at else "",
        },
    )

    account = fcm_service_account(db)
    tokens = db.query(models.DeviceToken).filter(models.DeviceToken.user_id == owner_id).all()
    if not tokens or not account:
        return 0
    who = (req.name or req.email or req.ip or "Someone").strip()
    title = "Send access request"
    body = f"{who} asked for access to “{send_name}”"
    sent = 0
    for tok in tokens:
        if send_fcm(
            tok.token, title, body,
            data={
                "type": "vault_send_request",
                "id": req.id,
                "send_id": req.send_id or "",
                "send_name": send_name or "",
                "name": (req.name or ""),
                "email": (req.email or ""),
                "ip": (req.ip or ""),
                "has_photo": "1" if req.photo_path else "0",
                "item_id": item_id or "",
            },
            account=account,
        ):
            sent += 1
    return sent


def _request_out(row: models.VaultSendRequest, send: models.VaultSend | None = None) -> schemas.VaultSendRequestOut:
    send = send or row.send
    item_id = None
    if send:
        data = _payload(send)
        raw = data.get("item_id")
        if isinstance(raw, str) and raw.strip():
            item_id = raw.strip()
    return schemas.VaultSendRequestOut(
        id=row.id,
        send_id=row.send_id,
        send_name=(send.name if send else "Send"),
        send_token=(send.token if send else ""),
        item_id=item_id,
        name=row.name,
        email=row.email,
        ip=row.ip,
        user_agent=row.user_agent,
        latitude=row.latitude,
        longitude=row.longitude,
        has_photo=bool(row.photo_path),
        has_face=bool(row.face_path),
        status=row.status,
        video_status=(row.video_status or "none"),
        created_at=row.created_at,
        viewed_at=row.viewed_at,
        face_captured_at=row.face_captured_at,
    )


@public_router.post("/public/{token}/request-access")
async def public_request_access(
    token: str,
    request: Request,
    name: str = Form(""),
    email: str = Form(""),
    latitude: str = Form(""),
    longitude: str = Form(""),
    next: str = Form("page"),
    photo: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
):
    """Guest asks the owner for access; optional name, email, geo, selfie/photo."""
    back = "qr" if (next or "").strip() == "qr" else "page"
    back_url = f"/vault/public/{token}/{back}"

    def _redir(q: str = "") -> RedirectResponse:
        return RedirectResponse(back_url + (f"?{q}" if q else ""), status_code=302)

    try:
        send = _load_valid_send(token, db)
    except HTTPException:
        return _redir("req_err=gone")

    data = _payload(send)
    if not data.get("require_grant"):
        return _redir("req_err=disabled")

    display_name = (name or "").strip()[:120] or None
    mail = (email or "").strip()[:255] or None
    if mail and "@" not in mail:
        return _redir("req_err=email")

    lat = (latitude or "").strip()[:32] or None
    lng = (longitude or "").strip()[:32] or None
    if lat:
        try:
            float(lat)
        except ValueError:
            lat = None
    if lng:
        try:
            float(lng)
        except ValueError:
            lng = None

    row = models.VaultSendRequest(
        send_id=send.id,
        user_id=send.user_id,
        name=display_name,
        email=mail,
        ip=_client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:400] or None,
        latitude=lat,
        longitude=lng,
        status="pending",
    )
    db.add(row)
    db.flush()

    if photo and (photo.filename or (photo.content_type or "").startswith("image/")):
        raw = await photo.read()
        if raw and (photo.content_type or "").startswith("image/"):
            if len(raw) > settings.MAX_UPLOAD_MB * 1024 * 1024:
                db.rollback()
                return _redir("req_err=photo")
            dest = settings.STORAGE_DIR / send.user_id / "vault_send_requests"
            dest.mkdir(parents=True, exist_ok=True)
            enc_path = dest / f"{row.id}.enc"
            enc_path.write_bytes(crypto.encrypt_bytes(raw))
            row.photo_path = str(enc_path.relative_to(settings.STORAGE_DIR))
            row.photo_mime = (photo.content_type or "image/jpeg")[:80]

    db.commit()
    db.refresh(row)
    _notify_send_request(db, send.user_id, row, send.name, send.token)

    wants_json = "application/json" in (request.headers.get("accept") or "")
    if wants_json:
        resp = JSONResponse({"ok": True, "id": row.id})
    else:
        resp = _redir("req_ok=1")
    resp.set_cookie(
        key=_send_req_cookie_name(token),
        value=row.id,
        httponly=True,
        samesite="lax",
        # Session cookie: closes with the browser so the next visit must request access again.
        secure=request.url.scheme == "https",
    )
    return resp


@public_router.get("/public/{token}/request-status")
def public_request_status(token: str, request: Request, db: Session = Depends(get_db)):
    """Guest polls grant / live-video state for their cookie-bound request."""
    try:
        send = _load_valid_send(token, db)
    except HTTPException:
        raise HTTPException(410, "Send not found")
    row = _guest_request(request, send, db)
    if not row:
        return {"ok": False, "status": None, "video_status": "none"}
    return {
        "ok": True,
        "id": row.id,
        "status": row.status,
        "video_status": row.video_status or "none",
    }


def _chat_out(row: models.VaultSendChatMessage) -> schemas.VaultSendChatOut:
    return schemas.VaultSendChatOut(
        id=row.id,
        from_role=row.from_role,
        body=row.body,
        created_at=row.created_at,
    )


def _normalize_chat_text(raw: str) -> str:
    text = (raw or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        raise HTTPException(400, "Message is empty")
    if len(text) > 1000:
        raise HTTPException(400, "Message is too long")
    return text


def _list_chat_messages(
    request_id: str,
    db: Session,
    *,
    after: Optional[str] = None,
    limit: int = 80,
) -> list[models.VaultSendChatMessage]:
    q = (
        db.query(models.VaultSendChatMessage)
        .filter(models.VaultSendChatMessage.request_id == request_id)
        .order_by(models.VaultSendChatMessage.created_at.asc(), models.VaultSendChatMessage.id.asc())
    )
    rows = q.all()
    if after:
        # Return only messages after the given id (stable for polling).
        seen = False
        filtered: list[models.VaultSendChatMessage] = []
        for row in rows:
            if seen:
                filtered.append(row)
            elif row.id == after:
                seen = True
        rows = filtered
    if limit > 0 and len(rows) > limit:
        rows = rows[-limit:]
    return rows


def _post_chat_message(
    row: models.VaultSendRequest,
    *,
    from_role: str,
    text: str,
    db: Session,
) -> models.VaultSendChatMessage:
    if row.status not in ("pending", "seen"):
        raise HTTPException(400, "Chat is only available while the access request is pending")
    body = _normalize_chat_text(text)
    msg = models.VaultSendChatMessage(
        request_id=row.id,
        from_role=from_role,
        body=body,
    )
    db.add(msg)
    if from_role == "admin" and row.status == "pending":
        row.status = "seen"
    db.commit()
    db.refresh(msg)
    return msg


@public_router.get("/public/{token}/chat")
def public_send_chat_list(
    token: str,
    request: Request,
    after: Optional[str] = None,
    db: Session = Depends(get_db),
):
    try:
        send = _load_valid_send(token, db)
    except HTTPException:
        raise HTTPException(410, "Send not found")
    row = _guest_request(request, send, db)
    if not row:
        return {"ok": False, "status": None, "messages": []}
    messages = _list_chat_messages(row.id, db, after=after)
    return {
        "ok": True,
        "status": row.status,
        "messages": [_chat_out(m).model_dump(mode="json") for m in messages],
    }


@public_router.post("/public/{token}/chat")
async def public_send_chat_post(token: str, request: Request, db: Session = Depends(get_db)):
    try:
        send = _load_valid_send(token, db)
    except HTTPException:
        raise HTTPException(410, "Send not found")
    row = _guest_request(request, send, db)
    if not row or row.status not in ("pending", "seen"):
        raise HTTPException(400, "No pending access request")
    body = await request.json()
    msg = _post_chat_message(row, from_role="guest", text=str((body or {}).get("text") or ""), db=db)
    # Nudge owner tabs (same hub as new access requests).
    try:
        from app.send_request_events import send_request_hub
        payload = _request_out(row, send).model_dump(mode="json")
        payload["chat_preview"] = msg.body[:120]
        payload["chat_from"] = "guest"
        send_request_hub.publish(row.user_id, payload)
    except Exception:
        pass
    return {"ok": True, "message": _chat_out(msg).model_dump(mode="json")}


@public_router.post("/public/{token}/video/accept")
def public_video_accept(token: str, request: Request, db: Session = Depends(get_db)):
    """Guest accepts live video and marks the session live."""
    try:
        send = _load_valid_send(token, db)
    except HTTPException:
        raise HTTPException(410, "Send not found")
    row = _guest_request(request, send, db)
    if not row or row.status not in ("pending", "seen"):
        raise HTTPException(400, "No pending access request")
    if (row.video_status or "none") not in ("requested", "live"):
        raise HTTPException(400, "Owner has not asked for live video")
    from app.video_signal import video_signal_hub
    row.video_status = "live"
    db.commit()
    video_signal_hub.push(row.id, "admin", {"type": "ready"})
    return {"ok": True, "video_status": "live", "id": row.id}


@public_router.post("/public/{token}/video/signal")
async def public_video_signal(token: str, request: Request, db: Session = Depends(get_db)):
    try:
        send = _load_valid_send(token, db)
    except HTTPException:
        raise HTTPException(410, "Send not found")
    row = _guest_request(request, send, db)
    if not row or (row.video_status or "none") not in ("requested", "live"):
        raise HTTPException(400, "Video session is not active")
    body = await request.json()
    msg_type = str((body or {}).get("type") or "").strip().lower()
    if msg_type not in ("offer", "answer", "ice", "hangup"):
        raise HTTPException(400, "Invalid signal type")
    from app.video_signal import video_signal_hub
    payload: dict = {"type": msg_type}
    if body.get("sdp"):
        payload["sdp"] = body["sdp"]
    if body.get("candidate") is not None:
        payload["candidate"] = body["candidate"]
    video_signal_hub.push(row.id, "admin", payload)
    if msg_type == "hangup":
        row.video_status = "ended"
        db.commit()
    return {"ok": True}


@public_router.get("/public/{token}/video/signals")
def public_video_signals(token: str, request: Request, db: Session = Depends(get_db)):
    try:
        send = _load_valid_send(token, db)
    except HTTPException:
        raise HTTPException(410, "Send not found")
    row = _guest_request(request, send, db)
    if not row:
        return {"video_status": "none", "status": None, "messages": []}
    from app.video_signal import video_signal_hub
    return {
        "video_status": row.video_status or "none",
        "status": row.status,
        "messages": video_signal_hub.drain(row.id, "guest"),
    }


@public_router.post("/public/{token}/email-otp")
async def public_send_email_otp(
    token: str,
    request: Request,
    email: str = Form(""),
    code: str = Form(""),
    pin: str = Form(""),
    step: str = Form("send"),
    db: Session = Depends(get_db),
):
    """step=send → mail OTP; step=verify → set cookie and redirect to page."""
    from urllib.parse import quote

    def _page(**extra):
        q = []
        if pin:
            q.append(f"pin={quote(pin)}")
        for k, v in extra.items():
            if v is None or v is False or v == "":
                continue
            q.append(f"{k}={quote(str(v))}")
        dest = f"/vault/public/{token}/page"
        if q:
            dest += "?" + "&".join(q)
        return RedirectResponse(dest, status_code=302)

    try:
        send = _load_valid_send(token, db)
    except HTTPException:
        return _send_gone_page(request, HTTPException(410, "Send not found"))
    data = _payload(send)
    if not data.get("require_email_otp"):
        return _page()
    if send.pin_hash and not (pin and security.verify_password(pin, send.pin_hash)):
        return RedirectResponse(f"/vault/public/{token}/page", status_code=302)
    if not _grant_unlocked(request, send, data, db):
        return _page()

    mail = (email or "").strip().lower()
    step = (step or "send").strip().lower()

    if step == "send":
        err = _validate_guest_email(data, mail, db)
        if err:
            return _page(otp_err=err)
        from app.mailer import mail_ready, send_vault_otp
        if not mail_ready(db):
            return _page(otp_err="mail")
        code_plain = f"{secrets.randbelow(1_000_000):06d}"
        db.query(models.VaultSendEmailOtp).filter(models.VaultSendEmailOtp.send_id == send.id).delete()
        db.add(models.VaultSendEmailOtp(
            send_id=send.id,
            email=mail,
            code_hash=security.hash_password(code_plain),
            expires_at=datetime.utcnow() + timedelta(minutes=10),
        ))
        db.commit()
        if not send_vault_otp(mail, code_plain, send.name, db=db):
            return _page(otp_err="mail", otp_email=mail)
        return _page(otp_sent=1, otp_email=mail)

    # verify
    err = _validate_guest_email(data, mail, db)
    if err:
        return _page(otp_err=err, otp_email=mail)
    row = (
        db.query(models.VaultSendEmailOtp)
        .filter(
            models.VaultSendEmailOtp.send_id == send.id,
            models.VaultSendEmailOtp.email == mail,
        )
        .order_by(models.VaultSendEmailOtp.created_at.desc())
        .first()
    )
    if not row or row.expires_at < datetime.utcnow() or not security.verify_password((code or "").strip(), row.code_hash):
        return _page(otp_err="bad_code", otp_email=mail, otp_sent=1)
    db.delete(row)
    db.commit()
    resp = RedirectResponse(
        f"/vault/public/{token}/page" + (f"?pin={pin}" if pin else ""),
        status_code=302,
    )
    resp.set_cookie(
        key=_email_otp_cookie_name(token),
        value=mail,
        httponly=True,
        samesite="lax",
        max_age=24 * 3600,
        secure=request.url.scheme == "https",
    )
    return resp


@router.get("/send-requests", response_model=list[schemas.VaultSendRequestOut])
def list_send_requests(
    status: Optional[str] = "pending",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    q = db.query(models.VaultSendRequest).filter(
        models.VaultSendRequest.user_id == vault_id(current_user),
    )
    if status and status != "all":
        q = q.filter(models.VaultSendRequest.status == status)
    rows = q.order_by(models.VaultSendRequest.created_at.desc()).limit(100).all()
    send_ids = {r.send_id for r in rows}
    sends = {
        s.id: s
        for s in db.query(models.VaultSend).filter(models.VaultSend.id.in_(send_ids)).all()
    } if send_ids else {}
    return [_request_out(r, sends.get(r.send_id)) for r in rows]


@router.post("/send-requests/{request_id}/seen", response_model=schemas.VaultSendRequestOut)
def mark_send_request_seen(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = (
        db.query(models.VaultSendRequest)
        .filter(
            models.VaultSendRequest.id == request_id,
            models.VaultSendRequest.user_id == vault_id(current_user),
        )
        .first()
    )
    if not row:
        raise HTTPException(404, "Request not found")
    if row.status == "pending":
        row.status = "seen"
        row.decided_at = datetime.utcnow()
        db.commit()
        db.refresh(row)
    return _request_out(row)


@router.post("/send-requests/{request_id}/grant", response_model=schemas.VaultSendRequestOut)
def grant_send_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Allow this guest's browser (cookie) to unlock the send secrets."""
    require_owner(current_user)
    row = (
        db.query(models.VaultSendRequest)
        .filter(
            models.VaultSendRequest.id == request_id,
            models.VaultSendRequest.user_id == vault_id(current_user),
        )
        .first()
    )
    if not row:
        raise HTTPException(404, "Request not found")
    if row.status == "dismissed":
        raise HTTPException(400, "Request was dismissed")
    row.status = "granted"
    row.decided_at = datetime.utcnow()
    row.video_status = "ended"
    db.commit()
    db.refresh(row)
    from app.video_signal import video_signal_hub
    video_signal_hub.clear(row.id)
    return _request_out(row)


@router.post("/send-requests/{request_id}/dismiss", response_model=schemas.VaultSendRequestOut)
def dismiss_send_request(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = (
        db.query(models.VaultSendRequest)
        .filter(
            models.VaultSendRequest.id == request_id,
            models.VaultSendRequest.user_id == vault_id(current_user),
        )
        .first()
    )
    if not row:
        raise HTTPException(404, "Request not found")
    row.status = "dismissed"
    row.decided_at = datetime.utcnow()
    row.video_status = "ended"
    db.commit()
    db.refresh(row)
    from app.video_signal import video_signal_hub
    video_signal_hub.clear(row.id)
    return _request_out(row)


def _owned_send_request(request_id: str, db: Session, current_user: models.User) -> models.VaultSendRequest:
    row = (
        db.query(models.VaultSendRequest)
        .filter(
            models.VaultSendRequest.id == request_id,
            models.VaultSendRequest.user_id == vault_id(current_user),
        )
        .first()
    )
    if not row:
        raise HTTPException(404, "Request not found")
    return row


@router.post("/send-requests/{request_id}/video/request", response_model=schemas.VaultSendRequestOut)
def request_send_video(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Owner asks the waiting guest to turn on live camera."""
    require_owner(current_user)
    row = _owned_send_request(request_id, db, current_user)
    if row.status not in ("pending", "seen"):
        raise HTTPException(400, "Can only request video while the access request is pending")
    from app.video_signal import video_signal_hub
    video_signal_hub.clear(row.id)
    row.video_status = "requested"
    if row.status == "pending":
        row.status = "seen"
    db.commit()
    db.refresh(row)
    return _request_out(row)


@router.post("/send-requests/{request_id}/video/end", response_model=schemas.VaultSendRequestOut)
def end_send_video(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = _owned_send_request(request_id, db, current_user)
    row.video_status = "ended"
    db.commit()
    db.refresh(row)
    from app.video_signal import video_signal_hub
    video_signal_hub.push(row.id, "guest", {"type": "hangup"})
    return _request_out(row)


@router.post("/send-requests/{request_id}/video/signal")
def admin_video_signal(
    request_id: str,
    body: schemas.VaultVideoSignalIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = _owned_send_request(request_id, db, current_user)
    if row.video_status not in ("requested", "live"):
        raise HTTPException(400, "Video session is not active")
    from app.video_signal import video_signal_hub
    msg_type = (body.type or "").strip().lower()
    if msg_type not in ("offer", "answer", "ice", "hangup"):
        raise HTTPException(400, "Invalid signal type")
    payload: dict = {"type": msg_type}
    if body.sdp:
        payload["sdp"] = body.sdp
    if body.candidate is not None:
        payload["candidate"] = body.candidate
    video_signal_hub.push(row.id, "guest", payload)
    if msg_type == "hangup":
        row.video_status = "ended"
        db.commit()
    return {"ok": True}


@router.get("/send-requests/{request_id}/video/signals")
def admin_video_signals(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = _owned_send_request(request_id, db, current_user)
    from app.video_signal import video_signal_hub
    return {
        "video_status": row.video_status or "none",
        "status": row.status,
        "messages": video_signal_hub.drain(row.id, "admin"),
    }


@router.get("/send-requests/{request_id}/chat")
def list_send_request_chat(
    request_id: str,
    after: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = _owned_send_request(request_id, db, current_user)
    messages = _list_chat_messages(row.id, db, after=after)
    return {
        "ok": True,
        "status": row.status,
        "messages": [_chat_out(m).model_dump(mode="json") for m in messages],
    }


@router.post("/send-requests/{request_id}/chat")
def post_send_request_chat(
    request_id: str,
    body: schemas.VaultSendChatIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = _owned_send_request(request_id, db, current_user)
    msg = _post_chat_message(row, from_role="admin", text=body.text, db=db)
    return {"ok": True, "message": _chat_out(msg).model_dump(mode="json")}


@router.get("/send-requests/{request_id}/photo")
def send_request_photo(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = _owned_send_request(request_id, db, current_user)
    if not row.photo_path:
        raise HTTPException(404, "Photo not found")
    path = settings.STORAGE_DIR / row.photo_path
    if not path.is_file():
        raise HTTPException(404, "Photo not found")
    raw = crypto.decrypt_bytes(path.read_bytes())
    return Response(content=raw, media_type=row.photo_mime or "image/jpeg")


@router.post("/send-requests/{request_id}/face", response_model=schemas.VaultSendRequestOut)
async def capture_send_request_face(
    request_id: str,
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Owner captures a still from live video; stored encrypted as verification record."""
    require_owner(current_user)
    row = _owned_send_request(request_id, db, current_user)
    if row.status not in ("pending", "seen"):
        raise HTTPException(400, "Can only capture a face while the request is pending")
    raw = await photo.read()
    if not raw or not (photo.content_type or "").startswith("image/"):
        raise HTTPException(400, "Image required")
    if len(raw) > settings.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(400, "Image too large")
    dest = settings.STORAGE_DIR / row.user_id / "vault_send_faces"
    dest.mkdir(parents=True, exist_ok=True)
    # Replace previous capture if any
    if row.face_path:
        old = settings.STORAGE_DIR / row.face_path
        try:
            if old.is_file():
                old.unlink()
        except OSError:
            pass
    enc_path = dest / f"{row.id}.enc"
    enc_path.write_bytes(crypto.encrypt_bytes(raw))
    row.face_path = str(enc_path.relative_to(settings.STORAGE_DIR))
    row.face_mime = (photo.content_type or "image/jpeg")[:80]
    row.face_captured_at = datetime.utcnow()
    db.commit()
    db.refresh(row)
    return _request_out(row)


@router.get("/send-requests/{request_id}/face")
def send_request_face(
    request_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = _owned_send_request(request_id, db, current_user)
    if not row.face_path:
        raise HTTPException(404, "Face capture not found")
    path = settings.STORAGE_DIR / row.face_path
    if not path.is_file():
        raise HTTPException(404, "Face capture not found")
    raw = crypto.decrypt_bytes(path.read_bytes())
    return Response(content=raw, media_type=row.face_mime or "image/jpeg")


# ---------- Items ----------
@router.get("/items", response_model=list[schemas.VaultItemOut])
def list_items(
    q: Optional[str] = None,
    item_type: Optional[str] = None,
    folder_id: Optional[str] = None,
    favorite: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    query = db.query(models.VaultItem).filter(
        models.VaultItem.user_id == vault_id(current_user),
        models.VaultItem.deleted_at.is_(None),
    )
    if item_type:
        query = query.filter(models.VaultItem.item_type == item_type)
    if folder_id == "none":
        query = query.filter(models.VaultItem.folder_id.is_(None))
    elif folder_id:
        query = query.filter(models.VaultItem.folder_id == folder_id)
    if favorite:
        query = query.filter(models.VaultItem.favorite.is_(True))
    rows = query.order_by(models.VaultItem.favorite.desc(), models.VaultItem.name).all()
    needle = (q or "").strip().lower()
    counts = _active_send_counts(vault_id(current_user), db)
    out = [_to_out(r, active_send_count=counts.get(r.id, 0)) for r in rows]
    if needle:
        def _match(item: schemas.VaultItemOut) -> bool:
            blob = " ".join(filter(None, [
                item.name, item.username, item.notes, item.email,
                " ".join(item.uris), item.first_name, item.last_name, item.cardholder_name,
            ])).lower()
            return needle in blob
        out = [i for i in out if _match(i)]
    return out


@router.post("/items", response_model=schemas.VaultItemOut, status_code=201)
def create_item(
    body: schemas.VaultItemIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    item_type = body.item_type if body.item_type in _ALLOWED_TYPES else models.VaultItemType.login.value
    now = datetime.utcnow()
    item = models.VaultItem(
        user_id=vault_id(current_user),
        folder_id=_owned_folder(body.folder_id, db, current_user),
        item_type=item_type,
        name=body.name.strip(),
        favorite=body.favorite,
        username=body.username,
        password_enc=crypto.encrypt_text(body.password),
        totp_secret_enc=crypto.encrypt_text((body.totp_secret or "").replace(" ", "") or None),
        uris=_uris_dump(body.uris),
        notes_enc=crypto.encrypt_text(body.notes),
        cardholder_name=body.cardholder_name,
        card_brand=body.card_brand,
        card_number_enc=crypto.encrypt_text(body.card_number),
        card_exp_month=body.card_exp_month,
        card_exp_year=body.card_exp_year,
        card_cvv_enc=crypto.encrypt_text(body.card_cvv),
        identity_title=body.identity_title,
        first_name=body.first_name,
        middle_name=body.middle_name,
        last_name=body.last_name,
        email=body.email,
        phone=body.phone,
        address1=body.address1,
        address2=body.address2,
        city=body.city,
        state=body.state,
        postal_code=body.postal_code,
        country=body.country,
        ssn_enc=crypto.encrypt_text(body.ssn),
        license_number_enc=crypto.encrypt_text(body.license_number),
        passport_number_enc=crypto.encrypt_text(body.passport_number),
        password_changed_at=now if body.password else None,
        created_at=now,
        updated_at=now,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _to_out(item)


@router.get("/items/{item_id}", response_model=schemas.VaultItemOut)
def get_item(item_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    item = _owned_item(item_id, db, current_user, include_deleted=True)
    counts = _active_send_counts(vault_id(current_user), db)
    return _to_out(item, active_send_count=counts.get(item.id, 0))


@router.patch("/items/{item_id}", response_model=schemas.VaultItemOut)
def update_item(
    item_id: str,
    body: schemas.VaultItemUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    item = _owned_item(item_id, db, current_user)
    data = body.dict(exclude_unset=True)
    if "folder_id" in data:
        item.folder_id = _owned_folder(data.pop("folder_id"), db, current_user)
    if "password" in data:
        new_pw = data.pop("password")
        old_pw = crypto.decrypt_text(item.password_enc)
        if old_pw and old_pw != new_pw:
            db.add(models.VaultPasswordHistory(item_id=item.id, password_enc=item.password_enc or crypto.encrypt_text(old_pw)))
        item.password_enc = crypto.encrypt_text(new_pw)
        item.password_changed_at = datetime.utcnow()
    if "totp_secret" in data:
        secret = (data.pop("totp_secret") or "").replace(" ", "") or None
        item.totp_secret_enc = crypto.encrypt_text(secret)
    if "notes" in data:
        item.notes_enc = crypto.encrypt_text(data.pop("notes"))
    if "uris" in data:
        item.uris = _uris_dump(data.pop("uris"))
    if "card_number" in data:
        item.card_number_enc = crypto.encrypt_text(data.pop("card_number"))
    if "card_cvv" in data:
        item.card_cvv_enc = crypto.encrypt_text(data.pop("card_cvv"))
    if "ssn" in data:
        item.ssn_enc = crypto.encrypt_text(data.pop("ssn"))
    if "license_number" in data:
        item.license_number_enc = crypto.encrypt_text(data.pop("license_number"))
    if "passport_number" in data:
        item.passport_number_enc = crypto.encrypt_text(data.pop("passport_number"))
    for field, value in data.items():
        setattr(item, field, value)
    item.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return _to_out(item)


@router.delete("/items/{item_id}", status_code=204)
def trash_item(item_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    item = _owned_item(item_id, db, current_user)
    item.deleted_at = datetime.utcnow()
    db.commit()


@router.post("/items/{item_id}/restore", response_model=schemas.VaultItemOut)
def restore_item(item_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    item = _owned_item(item_id, db, current_user, include_deleted=True)
    item.deleted_at = None
    db.commit()
    db.refresh(item)
    return _to_out(item)


@router.delete("/items/{item_id}/permanent", status_code=204)
def delete_item_forever(item_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    item = _owned_item(item_id, db, current_user, include_deleted=True)
    db.delete(item)
    db.commit()


@router.post("/items/{item_id}/favorite", response_model=schemas.VaultItemOut)
def favorite_item(item_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    item = _owned_item(item_id, db, current_user)
    item.favorite = True
    db.commit()
    db.refresh(item)
    return _to_out(item)


@router.delete("/items/{item_id}/favorite", response_model=schemas.VaultItemOut)
def unfavorite_item(item_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    item = _owned_item(item_id, db, current_user)
    item.favorite = False
    db.commit()
    db.refresh(item)
    return _to_out(item)


@router.get("/items/{item_id}/totp", response_model=schemas.VaultTotpOut)
def item_totp(item_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    item = _owned_item(item_id, db, current_user)
    secret = crypto.decrypt_text(item.totp_secret_enc)
    if not secret:
        raise HTTPException(status_code=404, detail="No authenticator key on this login")
    period = 30
    remaining = period - (int(time.time()) % period)
    return schemas.VaultTotpOut(code=security.totp_code(secret), period=period, remaining=remaining)


@router.get("/items/{item_id}/history", response_model=list[schemas.VaultHistoryOut])
def item_history(item_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    item = _owned_item(item_id, db, current_user, include_deleted=True)
    rows = (
        db.query(models.VaultPasswordHistory)
        .filter(models.VaultPasswordHistory.item_id == item.id)
        .order_by(models.VaultPasswordHistory.created_at.desc())
        .all()
    )
    return [
        schemas.VaultHistoryOut(
            id=r.id,
            password=crypto.decrypt_text(r.password_enc) or "",
            created_at=r.created_at,
        )
        for r in rows
    ]
