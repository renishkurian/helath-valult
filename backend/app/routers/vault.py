"""Password Vault — Bitwarden-style items, generator, TOTP, health, Send."""
from __future__ import annotations

import json
import math
import secrets
import string
import time
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

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


def _to_out(item: models.VaultItem) -> schemas.VaultItemOut:
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
    """Active sends that snapshot a specific vault login."""
    return [
        s for s in list_sends(db=db, current_user=current_user)
        if s.item_id == item_id and not s.revoked
    ]


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
    else:
        if not (body.text or "").strip():
            raise HTTPException(status_code=400, detail="text is required")
        payload = {"text": body.text.strip()}
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


@public_router.get("/public/{token}", response_model=schemas.VaultSendPublicOut)
def public_send_json(
    token: str,
    request: Request,
    pin: Optional[str] = None,
    db: Session = Depends(get_db),
):
    row = _load_valid_send(token, db)
    if row.pin_hash and not (pin and security.verify_password(pin, row.pin_hash)):
        return schemas.VaultSendPublicOut(
            name=row.name,
            send_type=row.send_type,
            expires_at=row.expires_at,
            has_pin=True,
            pin_required=True,
        )
    data = _payload(row)
    notes = crypto.decrypt_text(row.notes_enc)
    db.add(models.VaultSendAccess(
        send_id=row.id, action="view", ip=_client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:400] or None,
    ))
    row.view_count = (row.view_count or 0) + 1
    db.commit()
    return schemas.VaultSendPublicOut(
        name=row.name,
        send_type=row.send_type,
        text=data.get("text"),
        username=data.get("username"),
        password=data.get("password"),
        uris=data.get("uris") or [],
        totp_secret=data.get("totp_secret"),
        notes=notes,
        expires_at=row.expires_at,
        has_pin=bool(row.pin_hash),
        pin_required=False,
    )


@public_router.get("/public/{token}/page", response_class=HTMLResponse)
def public_send_page(
    token: str,
    request: Request,
    pin: Optional[str] = None,
    db: Session = Depends(get_db),
):
    try:
        row = _load_valid_send(token, db)
    except HTTPException as exc:
        return HTMLResponse(f"<h1>{exc.detail}</h1>", status_code=exc.status_code)
    pin_ok = not row.pin_hash or (pin and security.verify_password(pin, row.pin_hash))
    if not pin_ok:
        return templates.TemplateResponse(request, "vault_send_public.html", {
            "send": row, "token": token, "pin_required": True, "payload": None, "notes": None, "error": bool(pin),
        })
    data = _payload(row)
    notes = crypto.decrypt_text(row.notes_enc)
    db.add(models.VaultSendAccess(
        send_id=row.id, action="view", ip=_client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:400] or None,
    ))
    row.view_count = (row.view_count or 0) + 1
    db.commit()
    return templates.TemplateResponse(request, "vault_send_public.html", {
        "send": row, "token": token, "pin_required": False, "payload": data, "notes": notes, "error": False,
    })


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
    out = [_to_out(r) for r in rows]
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
    return _to_out(_owned_item(item_id, db, current_user, include_deleted=True))


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
