"""Shopping List — grocery lists, live sharing, friends, grocery dictionary."""
from __future__ import annotations

import json
import secrets
from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.orm import Session
from app.templating import nice_name, setup_templates

from app import crypto, models, schemas
from app.config import settings
from app.database import get_db
from app.deps import get_current_user, require_owner, vault_id
from app.extract import enhance_scan
from app.grocery import (
    CATALOG_CATEGORIES, VALID_SCOPES, _fold, catalog_payload, format_item_name,
    grouped_quick_add, money, PARSER_TO_FINANCE, recognize, seed_dictionary, suggest,
)

router = APIRouter(prefix="/tracker", tags=["tracker"])
templates = setup_templates()

MAX_PDF = 10 * 1024 * 1024
BANK_LABELS = (
    "SBI", "HDFC", "ICICI", "Axis", "Kotak", "Yes Bank", "IndusInd", "RBL", "IDFC", "Amex",
)


def _uid(user: models.User) -> str:
    return vault_id(user)


def _json_list(raw: Optional[str]) -> list:
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except (TypeError, json.JSONDecodeError):
        return []


def _household_names(db: Session, user_id: str) -> set[str]:
    names: set[str] = set()
    owner = db.query(models.User).filter(models.User.id == user_id).first()
    if owner and owner.full_name:
        names.add(owner.full_name.strip().casefold())
    for person in db.query(models.Person).filter(models.Person.user_id == user_id).all():
        if person.name:
            names.add(person.name.strip().casefold())
    for contact in (
        db.query(models.ShopContact)
        .filter(models.ShopContact.user_id == user_id)
        .all()
    ):
        rel = (contact.relation or "").strip().lower()
        if rel in ("family", "spouse", "child", "parent") or rel.startswith("fam"):
            if contact.name:
                names.add(contact.name.strip().casefold())
    return {n for n in names if n}


def _is_household(db: Session, lst: models.ShopList, guest_name: str) -> bool:
    return (guest_name or "").strip().casefold() in _household_names(db, lst.user_id)


def _member_names(db: Session, user_id: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for person in db.query(models.Person).filter(models.Person.user_id == user_id).all():
        name = (person.name or "").strip()
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            out.append(name)
    for contact in db.query(models.ShopContact).filter(models.ShopContact.user_id == user_id).all():
        rel = (contact.relation or "").strip().lower()
        if rel and rel not in ("family", "spouse", "child", "parent") and not rel.startswith("fam"):
            continue
        name = (contact.name or "").strip()
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            out.append(name)
    return out


def _list_revision(lst: models.ShopList) -> str:
    stamps = [lst.updated_at, lst.created_at]
    for item in lst.items or []:
        stamps.append(item.updated_at)
        stamps.append(item.created_at)
    latest = max((s for s in stamps if s), default=None)
    return latest.isoformat() if latest else ""


def _touch_list(lst: models.ShopList) -> None:
    lst.updated_at = datetime.utcnow()


def _recompute_total(lst: models.ShopList) -> None:
    total = Decimal("0")
    for item in lst.items or []:
        if item.price is None:
            continue
        qty = item.quantity if item.quantity is not None else Decimal("1")
        total += Decimal(str(item.price)) * Decimal(str(qty))
    lst.total_amount = total
    lst.updated_at = datetime.utcnow()


def _share_token(db: Session, lst: models.ShopList) -> Optional[str]:
    share = (
        db.query(models.ShopShare)
        .filter(models.ShopShare.list_id == lst.id)
        .order_by(models.ShopShare.created_at.desc())
        .first()
    )
    return share.token if share else None


def _owner_name(db: Session, lst: models.ShopList, cache: dict[str, str] | None = None) -> str:
    uid = (lst.user_id or "").strip()
    if not uid:
        return "Owner"
    names = cache if cache is not None else {}
    if uid not in names:
        owner = db.query(models.User).filter(models.User.id == uid).first()
        names[uid] = nice_name(
            ((owner.full_name or owner.email or "").strip() if owner else "") or "Owner"
        )
    return names[uid] or "Owner"


def _adder_name(db: Session, item: models.ShopItem, cache: dict[str, str]) -> Optional[str]:
    guest = (item.guest_name or "").strip()
    if guest:
        return nice_name(guest)
    uid = (item.added_by or "").strip()
    if uid and uid != "guest":
        if uid not in cache:
            user = db.query(models.User).filter(models.User.id == uid).first()
            cache[uid] = nice_name((user.full_name or user.email or "").strip() if user else "")
        if cache[uid]:
            return cache[uid]
    lst = item.lst
    owner_id = lst.user_id if lst else ""
    if owner_id:
        if owner_id not in cache:
            owner = db.query(models.User).filter(models.User.id == owner_id).first()
            cache[owner_id] = nice_name((owner.full_name or owner.email or "").strip() if owner else "")
        return cache[owner_id] or None
    return None


def _item_out(
    db: Session, item: models.ShopItem, cache: dict[str, str] | None = None, *, merged: bool = False,
) -> schemas.ShopItemOut:
    names = cache if cache is not None else {}
    return schemas.ShopItemOut(
        id=item.id, list_id=item.list_id, name=item.name,
        quantity=money(item.quantity) or 1, unit=item.unit,
        price=money(item.price) if item.price is not None else None,
        checked=bool(item.checked), emoji=item.emoji, category=item.category,
        notes=item.notes, added_by=item.added_by, guest_name=item.guest_name,
        added_by_name=_adder_name(db, item, names),
        status=item.status or "approved", merged=merged, created_at=item.created_at,
    )


def _receipt_out(row: models.ShopReceipt) -> schemas.ShopReceiptOut:
    mime = (row.image_mime or "").lower()
    return schemas.ShopReceiptOut(
        id=row.id, list_id=row.list_id, original_name=row.original_name,
        image_mime=row.image_mime, is_image=mime.startswith("image/"),
        created_at=row.created_at,
    )


def _list_out(db: Session, lst: models.ShopList, *, with_items: bool = False) -> schemas.ShopListOut:
    items = list(lst.items or [])
    receipts = list(lst.receipts or [])
    names: dict[str, str] = {}
    return schemas.ShopListOut(
        id=lst.id, name=lst.name, description=lst.description,
        completed=bool(lst.completed), total_amount=money(lst.total_amount),
        item_count=len(items),
        checked_count=sum(1 for i in items if i.checked),
        pending_count=sum(1 for i in items if i.status == "pending"),
        receipt_count=len(receipts),
        share_token=_share_token(db, lst),
        owner_name=_owner_name(db, lst, names),
        created_at=lst.created_at, updated_at=lst.updated_at,
        completed_at=lst.completed_at, deleted_at=lst.deleted_at,
        revision=_list_revision(lst),
        items=[_item_out(db, i, names) for i in items] if with_items else None,
        receipts=[_receipt_out(r) for r in receipts] if with_items else None,
    )


def _owned_list(
    db: Session, user: models.User, list_id: str, *, include_deleted: bool = False,
) -> models.ShopList:
    lst = (
        db.query(models.ShopList)
        .filter(models.ShopList.id == list_id, models.ShopList.user_id == _uid(user))
        .first()
    )
    if not lst or (lst.deleted_at and not include_deleted):
        raise HTTPException(404, "List not found")
    return lst


def _stmt_out(row: models.ShopStatementTxn) -> schemas.ShopStatementTxnOut:
    return schemas.ShopStatementTxnOut(
        id=row.id, txn_date=row.txn_date, description=row.description,
        amount=money(row.amount) if row.amount is not None else None,
        direction=row.direction, category=row.category, bank_name=row.bank_name,
        account_number=row.account_number, account_type=row.account_type,
        source_file=row.source_file, status=row.status,
        finance_txn_id=row.finance_txn_id, created_at=row.created_at,
    )


def _contact_out(row: models.ShopContact) -> schemas.ShopContactOut:
    return schemas.ShopContactOut(
        id=row.id, name=row.name, email=row.email, phone=row.phone,
        relation=row.relation, created_at=row.created_at,
    )


def _send_out(db: Session, row: models.ShopSend) -> schemas.ShopSendOut:
    sender = db.query(models.User).filter(models.User.id == row.sender_id).first()
    receiver = db.query(models.User).filter(models.User.id == row.receiver_id).first()
    snap = {}
    if row.list_data:
        try:
            snap = json.loads(row.list_data) or {}
        except json.JSONDecodeError:
            snap = {}
    return schemas.ShopSendOut(
        id=row.id, sender_id=row.sender_id, receiver_id=row.receiver_id,
        sender_name=sender.full_name if sender else None,
        receiver_name=receiver.full_name if receiver else None,
        list_name=snap.get("name"), status=row.status, message=row.message,
        sent_at=row.sent_at,
    )


def _list_snapshot(lst: models.ShopList) -> dict:
    return {
        "name": lst.name,
        "description": lst.description,
        "items": [
            {
                "name": i.name, "quantity": money(i.quantity) or 1, "unit": i.unit,
                "price": money(i.price) if i.price is not None else None,
                "emoji": i.emoji, "category": i.category, "notes": i.notes,
            }
            for i in (lst.items or [])
        ],
    }


def _public_payload(db: Session, lst: models.ShopList) -> dict:
    names: dict[str, str] = {}
    items = [_item_out(db, i, names).model_dump() for i in (lst.items or []) if i.status != "rejected"]
    for row in items:
        if isinstance(row.get("created_at"), datetime):
            row["created_at"] = row["created_at"].isoformat()
    return {
        "id": lst.id,
        "name": lst.name,
        "description": lst.description,
        "completed": bool(lst.completed),
        "total_amount": money(lst.total_amount),
        "revision": _list_revision(lst),
        "owner_name": _owner_name(db, lst, names),
        "created_at": lst.created_at.isoformat() if lst.created_at else None,
        "updated_at": lst.updated_at.isoformat() if lst.updated_at else None,
        "members": _member_names(db, lst.user_id),
        "items": items,
    }


# ---------- Summary ----------

@router.get("/summary", response_model=schemas.ShopSummaryOut)
def tracker_summary(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    uid = _uid(current_user)
    lists = (
        db.query(models.ShopList)
        .filter(models.ShopList.user_id == uid, models.ShopList.deleted_at.is_(None))
        .all()
    )
    pending_items = (
        db.query(models.ShopItem)
        .join(models.ShopList)
        .filter(
            models.ShopList.user_id == uid,
            models.ShopList.deleted_at.is_(None),
            models.ShopItem.status == "pending",
        )
        .count()
    )
    pending_stmt = (
        db.query(models.ShopStatementTxn)
        .filter(models.ShopStatementTxn.user_id == uid, models.ShopStatementTxn.status == "pending")
        .count()
    )
    friends = db.query(models.ShopContact).filter(models.ShopContact.user_id == uid).count()
    inbox = (
        db.query(models.ShopSend)
        .filter(models.ShopSend.receiver_id == uid, models.ShopSend.status == "pending")
        .count()
    )
    return schemas.ShopSummaryOut(
        lists=len(lists),
        open_lists=sum(1 for x in lists if not x.completed),
        pending_items=pending_items,
        pending_statements=pending_stmt,
        friends=friends,
        inbox=inbox,
    )


# ---------- Lists ----------

@router.get("/lists", response_model=list[schemas.ShopListOut])
def list_lists(
    completed: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    q = db.query(models.ShopList).filter(
        models.ShopList.user_id == _uid(current_user),
        models.ShopList.deleted_at.is_(None),
    )
    if completed is not None:
        q = q.filter(models.ShopList.completed.is_(completed))
    rows = q.order_by(models.ShopList.updated_at.desc()).all()
    return [_list_out(db, r) for r in rows]


@router.post("/lists", response_model=schemas.ShopListOut, status_code=201)
def create_list(
    body: schemas.ShopListIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    name = body.name.strip().title()
    lst = models.ShopList(
        user_id=_uid(current_user), name=name,
        description=(body.description or "").strip() or None,
    )
    db.add(lst)
    db.commit()
    db.refresh(lst)
    return _list_out(db, lst, with_items=True)


@router.get("/lists/{list_id}", response_model=schemas.ShopListOut)
def get_list(
    list_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _list_out(db, _owned_list(db, current_user, list_id), with_items=True)


@router.patch("/lists/{list_id}", response_model=schemas.ShopListOut)
def update_list(
    list_id: str,
    body: schemas.ShopListUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    lst = _owned_list(db, current_user, list_id)
    if body.name is not None:
        lst.name = body.name.strip().title()
    if body.description is not None:
        lst.description = body.description.strip() or None
    if body.completed is not None:
        lst.completed = body.completed
        lst.completed_at = datetime.utcnow() if body.completed else None
    lst.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(lst)
    return _list_out(db, lst, with_items=True)


@router.delete("/lists/{list_id}", status_code=204)
def delete_list(
    list_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Move a shopping list to trash (soft delete)."""
    require_owner(current_user)
    lst = _owned_list(db, current_user, list_id)
    lst.deleted_at = datetime.utcnow()
    lst.updated_at = datetime.utcnow()
    db.commit()
    return None


@router.get("/trash", response_model=list[schemas.ShopListOut])
def list_trash(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    rows = (
        db.query(models.ShopList)
        .filter(
            models.ShopList.user_id == _uid(current_user),
            models.ShopList.deleted_at.isnot(None),
        )
        .order_by(models.ShopList.deleted_at.desc())
        .all()
    )
    return [_list_out(db, r) for r in rows]


@router.post("/lists/{list_id}/restore", response_model=schemas.ShopListOut)
def restore_list(
    list_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    lst = _owned_list(db, current_user, list_id, include_deleted=True)
    if not lst.deleted_at:
        raise HTTPException(400, "List is not in trash")
    lst.deleted_at = None
    lst.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(lst)
    return _list_out(db, lst)


@router.delete("/lists/{list_id}/permanent", status_code=204)
def permanent_delete_list(
    list_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    lst = _owned_list(db, current_user, list_id, include_deleted=True)
    if not lst.deleted_at:
        raise HTTPException(400, "Move the list to trash first")
    for rec in list(lst.receipts or []):
        _drop_receipt_file(rec)
    db.delete(lst)
    db.commit()
    return None


@router.post("/trash/empty", status_code=204)
def empty_trash(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    rows = (
        db.query(models.ShopList)
        .filter(
            models.ShopList.user_id == _uid(current_user),
            models.ShopList.deleted_at.isnot(None),
        )
        .all()
    )
    for lst in rows:
        for rec in list(lst.receipts or []):
            _drop_receipt_file(rec)
        db.delete(lst)
    db.commit()
    return None


@router.post("/lists/{list_id}/share", response_model=schemas.ShopShareOut)
def share_list(
    list_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    lst = _owned_list(db, current_user, list_id)
    existing = (
        db.query(models.ShopShare)
        .filter(models.ShopShare.list_id == lst.id)
        .order_by(models.ShopShare.created_at.desc())
        .first()
    )
    if existing:
        share = existing
    else:
        share = models.ShopShare(
            list_id=lst.id, token=secrets.token_urlsafe(24),
            created_by=current_user.id,
        )
        db.add(share)
        db.commit()
        db.refresh(share)
    origin = str(request.base_url).rstrip("/")
    return schemas.ShopShareOut(token=share.token, url=f"{origin}/shop/{share.token}", list_id=lst.id)


# ---------- Bill copies ----------

def _drop_receipt_file(row: models.ShopReceipt) -> None:
    if not row.image_path:
        return
    path = settings.STORAGE_DIR / row.image_path
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def _owned_receipt(db: Session, user: models.User, list_id: str, receipt_id: str) -> models.ShopReceipt:
    lst = _owned_list(db, user, list_id)
    row = (
        db.query(models.ShopReceipt)
        .filter(
            models.ShopReceipt.id == receipt_id,
            models.ShopReceipt.list_id == lst.id,
            models.ShopReceipt.user_id == _uid(user),
        )
        .first()
    )
    if not row:
        raise HTTPException(404, "Bill copy not found")
    return row


def save_receipt(
    db: Session,
    user: models.User,
    list_id: str,
    raw: bytes,
    mime: str | None,
    filename: str | None,
) -> models.ShopReceipt:
    lst = _owned_list(db, user, list_id)
    mime = (mime or "").split(";")[0].strip().lower()
    name = (filename or "").lower()
    is_pdf = mime == "application/pdf" or name.endswith(".pdf")
    is_image = mime.startswith("image/") or name.endswith((".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif"))
    if not is_pdf and not is_image:
        raise HTTPException(400, "Upload a photo or PDF of the bill")
    if is_image and not is_pdf:
        raw = enhance_scan(raw, mime or "image/jpeg")
        mime = "image/jpeg"
    elif is_pdf:
        mime = "application/pdf"
    if not raw:
        raise HTTPException(400, "Empty file")
    size_mb = len(raw) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_MB:
        raise HTTPException(413, f"File exceeds {settings.MAX_UPLOAD_MB} MB")
    if len(list(lst.receipts or [])) >= 20:
        raise HTTPException(400, "This list already has 20 bill copies")
    uid = _uid(user)
    dest_dir = settings.STORAGE_DIR / uid / "shop"
    dest_dir.mkdir(parents=True, exist_ok=True)
    rec = models.ShopReceipt(
        list_id=lst.id, user_id=uid,
        image_path="", image_mime=mime,
        original_name=(filename or "")[:255] or None,
    )
    db.add(rec)
    db.flush()
    rel = f"{uid}/shop/{rec.id}.enc"
    (settings.STORAGE_DIR / rel).write_bytes(crypto.encrypt_bytes(raw))
    rec.image_path = rel
    _touch_list(lst)
    db.commit()
    db.refresh(rec)
    return rec


@router.post("/lists/{list_id}/receipts", response_model=schemas.ShopReceiptOut, status_code=201)
async def upload_receipt(
    list_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    raw = await file.read()
    row = save_receipt(db, current_user, list_id, raw, file.content_type, file.filename)
    return _receipt_out(row)


@router.get("/lists/{list_id}/receipts/{receipt_id}/image")
def get_receipt_image(
    list_id: str,
    receipt_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    row = _owned_receipt(db, current_user, list_id, receipt_id)
    path = settings.STORAGE_DIR / row.image_path
    if not path.exists():
        raise HTTPException(404, "Bill copy missing on disk")
    plain = crypto.decrypt_bytes(path.read_bytes())
    return Response(content=plain, media_type=row.image_mime or "image/jpeg")


@router.delete("/lists/{list_id}/receipts/{receipt_id}", status_code=204)
def delete_receipt(
    list_id: str,
    receipt_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = _owned_receipt(db, current_user, list_id, receipt_id)
    lst = row.lst
    _drop_receipt_file(row)
    db.delete(row)
    if lst:
        _touch_list(lst)
    db.commit()
    return None


# ---------- Items ----------

def _item_match_key(db: Session, name: str) -> str:
    from app.grocery import _fold, recognize

    hint = recognize(db, name or "")
    if hint.get("matched") and hint.get("english"):
        return _fold(str(hint["english"]))
    return _fold(name or "")


def _add_item_row(
    db: Session, lst: models.ShopList, body: schemas.ShopItemIn, *, added_by: str, status: str,
) -> tuple[models.ShopItem, bool]:
    hint = recognize(db, body.name)
    if hint.get("matched"):
        display = format_item_name(hint.get("english") or "", hint.get("malayalam"))
    else:
        display = (body.name or hint.get("english") or "").strip()
    qty = Decimal(str(body.quantity if body.quantity not in (None, 0) else 1))
    unit = (body.unit or "").strip() or None
    want_key = _item_match_key(db, body.name) or _item_match_key(db, display)
    unit_key = (unit or "").strip().casefold()

    for existing in list(lst.items or []):
        if (existing.status or "approved") != status:
            continue
        if existing.status == "rejected":
            continue
        existing_unit = (existing.unit or "").strip().casefold()
        if existing_unit != unit_key:
            continue
        existing_key = _item_match_key(db, existing.name or "")
        if not want_key or existing_key != want_key:
            continue
        existing.quantity = Decimal(str(existing.quantity or 0)) + qty
        if body.price not in (None, ""):
            existing.price = Decimal(str(body.price))
        note = (body.notes or "").strip()
        if note:
            existing.notes = note
        if existing.checked:
            existing.checked = False
        existing.updated_at = datetime.utcnow()
        _recompute_total(lst)
        _touch_list(lst)
        return existing, True

    item = models.ShopItem(
        list_id=lst.id,
        name=display,
        quantity=qty,
        unit=unit,
        price=Decimal(str(body.price)) if body.price not in (None, "") else None,
        emoji=(body.emoji or hint.get("emoji") or "🛒"),
        category=(body.category or hint.get("category")),
        notes=(body.notes or "").strip() or None,
        added_by=added_by,
        guest_name=(body.guest_name or "").strip() or None,
        status=status,
    )
    db.add(item)
    db.flush()
    _recompute_total(lst)
    _touch_list(lst)
    return item, False


@router.post("/lists/{list_id}/items", response_model=schemas.ShopItemOut, status_code=201)
def add_item(
    list_id: str,
    body: schemas.ShopItemIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    lst = _owned_list(db, current_user, list_id)
    item, merged = _add_item_row(db, lst, body, added_by=current_user.id, status="approved")
    db.commit()
    db.refresh(item)
    return _item_out(db, item, merged=merged)


@router.patch("/lists/{list_id}/items/{item_id}", response_model=schemas.ShopItemOut)
def update_item(
    list_id: str,
    item_id: str,
    body: schemas.ShopItemUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    lst = _owned_list(db, current_user, list_id)
    item = next((i for i in lst.items if i.id == item_id), None)
    if not item:
        raise HTTPException(404, "Item not found")
    data = body.model_dump(exclude_unset=True)
    for key, val in data.items():
        if key == "quantity" and val is not None:
            item.quantity = Decimal(str(val))
        elif key == "price":
            item.price = Decimal(str(val)) if val is not None else None
        elif key == "name" and val:
            item.name = val.strip()
        elif hasattr(item, key) and key not in ("id", "list_id", "added_by"):
            setattr(item, key, val)
    _recompute_total(lst)
    _touch_list(lst)
    db.commit()
    db.refresh(item)
    return _item_out(db, item)


@router.post("/lists/{list_id}/items/{item_id}/toggle", response_model=schemas.ShopItemOut)
def toggle_item(
    list_id: str,
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    lst = _owned_list(db, current_user, list_id)
    item = next((i for i in lst.items if i.id == item_id), None)
    if not item:
        raise HTTPException(404, "Item not found")
    item.checked = not bool(item.checked)
    lst.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(item)
    return _item_out(db, item)


@router.post("/lists/{list_id}/items/{item_id}/approve", response_model=schemas.ShopItemOut)
def approve_item(
    list_id: str,
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    lst = _owned_list(db, current_user, list_id)
    item = next((i for i in lst.items if i.id == item_id), None)
    if not item:
        raise HTTPException(404, "Item not found")
    item.status = "approved"
    _recompute_total(lst)
    db.commit()
    db.refresh(item)
    return _item_out(db, item)


@router.post("/lists/{list_id}/items/{item_id}/reject", status_code=204)
def reject_item(
    list_id: str,
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    lst = _owned_list(db, current_user, list_id)
    item = next((i for i in lst.items if i.id == item_id), None)
    if not item:
        raise HTTPException(404, "Item not found")
    db.delete(item)
    db.flush()
    _recompute_total(lst)
    db.commit()
    return None


@router.delete("/lists/{list_id}/items/{item_id}", status_code=204)
def delete_item(
    list_id: str,
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    lst = _owned_list(db, current_user, list_id)
    item = next((i for i in lst.items if i.id == item_id), None)
    if not item:
        raise HTTPException(404, "Item not found")
    db.delete(item)
    db.flush()
    _recompute_total(lst)
    db.commit()
    return None


# ---------- Public share ----------

def _list_by_token(db: Session, token: str, *, bump: bool = True) -> tuple[models.ShopShare, models.ShopList]:
    share = db.query(models.ShopShare).filter(models.ShopShare.token == token).first()
    if not share:
        raise HTTPException(404, "Share not found")
    lst = db.query(models.ShopList).filter(models.ShopList.id == share.list_id).first()
    if not lst or lst.deleted_at:
        raise HTTPException(404, "List not found")
    if bump:
        share.use_count = (share.use_count or 0) + 1
    return share, lst


@router.get("/shared/{token}")
def get_shared(token: str, db: Session = Depends(get_db)):
    share, lst = _list_by_token(db, token, bump=False)
    return _public_payload(db, lst)


@router.post("/shared/{token}/items", status_code=201)
def guest_add_item(token: str, body: schemas.ShopItemIn, db: Session = Depends(get_db)):
    share, lst = _list_by_token(db, token)
    guest = (body.guest_name or "Guest").strip() or "Guest"
    blocked = {str(x).lower() for x in _json_list(lst.blocked_uids)}
    if guest.lower() in blocked:
        raise HTTPException(403, "You are blocked from this list")
    status = "approved" if _is_household(db, lst, guest) else "pending"
    item, _merged = _add_item_row(db, lst, body, added_by="guest", status=status)
    item.guest_name = guest
    _touch_list(lst)
    db.commit()
    db.refresh(item)
    return _item_out(db, item, merged=_merged)


@router.post("/shared/{token}/items/{item_id}/toggle")
def guest_toggle(token: str, item_id: str, db: Session = Depends(get_db)):
    share, lst = _list_by_token(db, token, bump=False)
    item = next((i for i in lst.items if i.id == item_id), None)
    if not item or item.status != "approved":
        raise HTTPException(404, "Item not found")
    item.checked = not bool(item.checked)
    _touch_list(lst)
    db.commit()
    db.refresh(item)
    return _item_out(db, item)


# ---------- Friends ----------

@router.get("/friends", response_model=list[schemas.ShopContactOut])
def list_friends(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    rows = (
        db.query(models.ShopContact)
        .filter(models.ShopContact.user_id == _uid(current_user))
        .order_by(models.ShopContact.name)
        .all()
    )
    return [_contact_out(r) for r in rows]


@router.post("/friends", response_model=schemas.ShopContactOut, status_code=201)
def add_friend(
    body: schemas.ShopContactIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = models.ShopContact(
        user_id=_uid(current_user), name=body.name.strip(),
        email=str(body.email).lower() if body.email else None,
        phone=(body.phone or "").strip() or None,
        relation=(body.relation or "").strip() or None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _contact_out(row)


@router.delete("/friends/{contact_id}", status_code=204)
def delete_friend(
    contact_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = (
        db.query(models.ShopContact)
        .filter(models.ShopContact.id == contact_id, models.ShopContact.user_id == _uid(current_user))
        .first()
    )
    if not row:
        raise HTTPException(404, "Contact not found")
    db.delete(row)
    db.commit()
    return None


@router.post("/lists/{list_id}/send", response_model=schemas.ShopSendOut)
def send_list(
    list_id: str,
    body: schemas.ShopSendIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    lst = _owned_list(db, current_user, list_id)
    receiver = db.query(models.User).filter(models.User.email == str(body.email).lower()).first()
    if not receiver:
        raise HTTPException(404, "No vault user with that email")
    rid = vault_id(receiver)
    if rid == _uid(current_user):
        raise HTTPException(400, "You already own this list")
    row = models.ShopSend(
        sender_id=_uid(current_user), receiver_id=rid, list_id=lst.id,
        list_data=json.dumps(_list_snapshot(lst)),
        message=(body.message or "").strip() or None,
        status="pending",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _send_out(db, row)


@router.get("/inbox", response_model=list[schemas.ShopSendOut])
def inbox(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    rows = (
        db.query(models.ShopSend)
        .filter(models.ShopSend.receiver_id == _uid(current_user))
        .order_by(models.ShopSend.sent_at.desc())
        .all()
    )
    return [_send_out(db, r) for r in rows]


@router.get("/sent", response_model=list[schemas.ShopSendOut])
def sent(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    rows = (
        db.query(models.ShopSend)
        .filter(models.ShopSend.sender_id == _uid(current_user))
        .order_by(models.ShopSend.sent_at.desc())
        .all()
    )
    return [_send_out(db, r) for r in rows]


@router.post("/inbox/{send_id}/accept", response_model=schemas.ShopListOut)
def accept_send(
    send_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    uid = _uid(current_user)
    row = (
        db.query(models.ShopSend)
        .filter(models.ShopSend.id == send_id, models.ShopSend.receiver_id == uid)
        .first()
    )
    if not row:
        raise HTTPException(404, "Invite not found")
    if row.status != "pending":
        raise HTTPException(400, "Already responded")
    snap = {}
    if row.list_data:
        try:
            snap = json.loads(row.list_data) or {}
        except json.JSONDecodeError:
            snap = {}
    lst = models.ShopList(
        user_id=uid, name=(snap.get("name") or "Shared list").title(),
        description=snap.get("description"),
    )
    db.add(lst)
    db.flush()
    for raw in snap.get("items") or []:
        db.add(models.ShopItem(
            list_id=lst.id, name=raw.get("name") or "Item",
            quantity=Decimal(str(raw.get("quantity") or 1)),
            unit=raw.get("unit"), price=Decimal(str(raw["price"])) if raw.get("price") is not None else None,
            emoji=raw.get("emoji") or "🛒", category=raw.get("category"),
            notes=raw.get("notes"), added_by=row.sender_id, status="approved",
        ))
    db.flush()
    _recompute_total(lst)
    row.status = "accepted"
    row.responded_at = datetime.utcnow()
    db.commit()
    db.refresh(lst)
    return _list_out(db, lst, with_items=True)


@router.post("/inbox/{send_id}/reject", status_code=204)
def reject_send(
    send_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = (
        db.query(models.ShopSend)
        .filter(models.ShopSend.id == send_id, models.ShopSend.receiver_id == _uid(current_user))
        .first()
    )
    if not row:
        raise HTTPException(404, "Invite not found")
    row.status = "rejected"
    row.responded_at = datetime.utcnow()
    db.commit()
    return None


@router.delete("/sent/{send_id}", status_code=204)
def recall_send(
    send_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = (
        db.query(models.ShopSend)
        .filter(models.ShopSend.id == send_id, models.ShopSend.sender_id == _uid(current_user))
        .first()
    )
    if not row:
        raise HTTPException(404, "Send not found")
    if row.status != "pending":
        raise HTTPException(400, "Can only recall a pending send")
    db.delete(row)
    db.commit()
    return None


# ---------- Grocery ----------

def _catalog_out(row: models.ShopCatalogItem, owner: str) -> schemas.ShopCatalogItemOut:
    return schemas.ShopCatalogItemOut(
        id=row.id,
        english=row.english,
        malayalam=row.malayalam,
        emoji=row.emoji or "🛒",
        category=row.category or "custom",
        scope=row.scope or "personal",
        aliases=row.aliases,
        mine=row.user_id == owner,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _normalize_catalog_fields(
    english: str,
    malayalam: Optional[str],
    emoji: Optional[str],
    category: str,
    scope: str,
    aliases: Optional[str],
) -> dict:
    en = (english or "").strip()
    if not en:
        raise HTTPException(400, "Name is required")
    cat = (category or "custom").strip().lower()
    if cat not in CATALOG_CATEGORIES:
        cat = "custom"
    sc = (scope or "personal").strip().lower()
    if sc not in VALID_SCOPES:
        sc = "personal"
    al = (aliases or "").strip() or None
    return {
        "english": en[:255],
        "malayalam": ((malayalam or "").strip() or None),
        "emoji": ((emoji or "🛒").strip() or "🛒")[:16],
        "category": cat,
        "scope": sc,
        "aliases": al[:500] if al else None,
    }


def _sync_dict_for_global(db: Session, row: models.ShopCatalogItem) -> None:
    """Global chips also feed recognition for everyone via ShopDictItem."""
    if (row.scope or "") != "global":
        return
    keys = {_fold(row.english)}
    if row.malayalam:
        keys.add(_fold(row.malayalam))
    for part in (row.aliases or "").replace(";", ",").split(","):
        f = _fold(part.strip())
        if f:
            keys.add(f)
    keys = {k for k in keys if k}
    for key in keys:
        exists = db.query(models.ShopDictItem).filter(models.ShopDictItem.key == key).first()
        if exists:
            if exists.source == "seed":
                continue
            exists.english = row.english
            exists.malayalam = row.malayalam
            exists.emoji = row.emoji or "🛒"
            exists.category = row.category
            continue
        db.add(models.ShopDictItem(
            key=key,
            english=row.english,
            malayalam=row.malayalam,
            emoji=row.emoji or "🛒",
            source="user",
            category=row.category,
        ))


@router.get("/catalog", response_model=list[schemas.ShopCatalogItemOut])
def list_catalog(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    owner = _uid(current_user)
    from sqlalchemy import or_

    rows = (
        db.query(models.ShopCatalogItem)
        .filter(
            or_(
                models.ShopCatalogItem.scope == "global",
                models.ShopCatalogItem.user_id == owner,
            )
        )
        .order_by(models.ShopCatalogItem.scope.desc(), models.ShopCatalogItem.english)
        .all()
    )
    return [_catalog_out(r, owner) for r in rows]


@router.post("/catalog", response_model=schemas.ShopCatalogItemOut, status_code=201)
def add_catalog_item(
    body: schemas.ShopCatalogItemIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    owner = _uid(current_user)
    fields = _normalize_catalog_fields(
        body.english, body.malayalam, body.emoji, body.category, body.scope, body.aliases,
    )
    row = models.ShopCatalogItem(user_id=owner, **fields)
    db.add(row)
    db.flush()
    _sync_dict_for_global(db, row)
    db.commit()
    db.refresh(row)
    return _catalog_out(row, owner)


@router.put("/catalog/{item_id}", response_model=schemas.ShopCatalogItemOut)
def update_catalog_item(
    item_id: str,
    body: schemas.ShopCatalogItemIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    owner = _uid(current_user)
    row = (
        db.query(models.ShopCatalogItem)
        .filter(models.ShopCatalogItem.id == item_id, models.ShopCatalogItem.user_id == owner)
        .first()
    )
    if not row:
        raise HTTPException(404, "Catalog item not found")
    fields = _normalize_catalog_fields(
        body.english, body.malayalam, body.emoji, body.category, body.scope, body.aliases,
    )
    for k, v in fields.items():
        setattr(row, k, v)
    row.updated_at = datetime.utcnow()
    _sync_dict_for_global(db, row)
    db.commit()
    db.refresh(row)
    return _catalog_out(row, owner)


@router.delete("/catalog/{item_id}", status_code=204)
def delete_catalog_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    owner = _uid(current_user)
    row = (
        db.query(models.ShopCatalogItem)
        .filter(models.ShopCatalogItem.id == item_id, models.ShopCatalogItem.user_id == owner)
        .first()
    )
    if not row:
        raise HTTPException(404, "Catalog item not found")
    db.delete(row)
    db.commit()
    return None


@router.get("/quick-add")
def quick_add(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    seed_dictionary(db)
    return {"groups": grouped_quick_add(db, _uid(current_user))}


@router.post("/recognize", response_model=schemas.ShopGroceryItemOut)
def recognize_item(
    body: schemas.ShopRecognizeIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return schemas.ShopGroceryItemOut(**recognize(db, body.name))


@router.get("/suggest", response_model=list[schemas.ShopGroceryItemOut])
def suggest_items(
    q: str = "",
    limit: int = 12,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return [
        schemas.ShopGroceryItemOut(**row)
        for row in suggest(db, q, limit=limit, user_id=_uid(current_user))
    ]


# ---------- PDF passwords ----------

@router.get("/passwords", response_model=list[schemas.ShopPdfPasswordOut])
def list_passwords(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    rows = (
        db.query(models.ShopPdfPassword)
        .filter(models.ShopPdfPassword.user_id == _uid(current_user))
        .order_by(models.ShopPdfPassword.created_at.desc())
        .all()
    )
    return [
        schemas.ShopPdfPasswordOut(
            id=r.id, identifier=r.identifier, account_type=r.account_type,
            last_4_digits=r.last_4_digits, created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/passwords", response_model=schemas.ShopPdfPasswordOut, status_code=201)
def save_password(
    body: schemas.ShopPdfPasswordIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = upsert_pdf_password(
        db, current_user,
        identifier=body.identifier,
        password=body.password,
        account_type=body.account_type,
        last_4_digits=body.last_4_digits,
    )
    db.commit()
    db.refresh(row)
    try:
        from app import expense_analyser as ea
        ea.retry_locked_pdfs(db, current_user)
    except Exception:
        pass
    return schemas.ShopPdfPasswordOut(
        id=row.id, identifier=row.identifier, account_type=row.account_type,
        last_4_digits=row.last_4_digits, created_at=row.created_at,
    )


@router.delete("/passwords/{password_id}", status_code=204)
def delete_password(
    password_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = (
        db.query(models.ShopPdfPassword)
        .filter(models.ShopPdfPassword.id == password_id, models.ShopPdfPassword.user_id == _uid(current_user))
        .first()
    )
    if not row:
        raise HTTPException(404, "Password not found")
    db.delete(row)
    db.commit()
    return None


def upsert_pdf_password(
    db: Session,
    user: models.User,
    *,
    identifier: str,
    password: str,
    account_type: str = "bank",
    last_4_digits: str | None = None,
) -> models.ShopPdfPassword:
    ident = (identifier or "").strip()
    kind = account_type if account_type in ("bank", "credit_card") else "bank"
    digits = (last_4_digits or "").strip() or None
    uid = _uid(user)
    row = (
        db.query(models.ShopPdfPassword)
        .filter(models.ShopPdfPassword.user_id == uid, models.ShopPdfPassword.identifier == ident)
        .first()
    )
    if row:
        row.password_enc = crypto.encrypt_text(password)
        row.account_type = kind
        if digits:
            row.last_4_digits = digits
        return row
    row = models.ShopPdfPassword(
        user_id=uid, identifier=ident,
        password_enc=crypto.encrypt_text(password),
        account_type=kind, last_4_digits=digits,
    )
    db.add(row)
    db.flush()
    return row


def _saved_password_rows(db: Session, user: models.User) -> list[tuple[str, str, str]]:
    """Return (identifier, last_4, password) for saved bank PDF passwords."""
    rows = db.query(models.ShopPdfPassword).filter(models.ShopPdfPassword.user_id == _uid(user)).all()
    out: list[tuple[str, str, str]] = []
    for r in rows:
        try:
            plain = crypto.decrypt_text(r.password_enc)
        except Exception:
            continue
        if plain:
            out.append((r.identifier or "", r.last_4_digits or "", plain))
    return out


def _saved_passwords(db: Session, user: models.User) -> list[str]:
    return [pwd for _ident, _digits, pwd in _saved_password_rows(db, user)]


def resolve_pdf_password(
    db: Session,
    user: models.User,
    raw: bytes,
    *,
    hint: str = "",
    explicit: str | None = None,
) -> str | None:
    """Pick a working PDF password: typed first, then saved banks matching the hint."""
    from app.statement_parsers import is_pdf_encrypted, test_pdf_password

    typed = (explicit or "").strip() or None
    if not is_pdf_encrypted(raw):
        return typed
    if typed and test_pdf_password(raw, typed):
        return typed
    blob = (hint or "").lower()
    matched: list[str] = []
    rest: list[str] = []
    for ident, digits, pwd in _saved_password_rows(db, user):
        tokens = [t for t in f"{ident} {digits}".lower().split() if t]
        hit = bool(blob) and any((len(t) >= 3 or t.isdigit()) and t in blob for t in tokens)
        (matched if hit else rest).append(pwd)
    seen: set[str] = set()
    for pwd in matched + rest:
        if pwd in seen:
            continue
        seen.add(pwd)
        if test_pdf_password(raw, pwd):
            return pwd
    return None


def ingest_statement_bytes(
    db: Session,
    user: models.User,
    raw: bytes,
    filename: str,
    *,
    password: str | None = None,
    identifier: str = "",
    source_label: str | None = None,
) -> dict:
    """Parse a statement PDF and insert pending rows. Caller commits."""
    from app.statement_parsers import parse_statement_file

    parsed = parse_statement_file(raw, filename or "statement.pdf", password=password)
    uid = _uid(user)
    existing = {
        r[0]
        for r in db.query(models.ShopStatementTxn.transaction_id)
        .filter(models.ShopStatementTxn.user_id == uid, models.ShopStatementTxn.transaction_id.isnot(None))
        .all()
    }
    created = 0
    skipped = 0
    label = source_label or filename or "statement.pdf"
    for txn in parsed.get("transactions") or []:
        tid = txn.get("transaction_id")
        if tid and tid in existing:
            skipped += 1
            continue
        db.add(models.ShopStatementTxn(
            user_id=uid,
            txn_date=txn.get("date"),
            description=txn.get("description"),
            amount=Decimal(str(txn.get("amount") or 0)),
            direction=txn.get("type") if txn.get("type") in ("debit", "credit") else "debit",
            category=txn.get("category") or "other",
            bank_name=txn.get("bank_name"),
            account_number=txn.get("account_number"),
            account_type=txn.get("account_type"),
            source_file=label,
            transaction_id=tid,
            reference_number=txn.get("reference_number"),
            status="pending",
        ))
        if tid:
            existing.add(tid)
        created += 1
    pwd = (password or "").strip()
    ident = (identifier or "").strip()
    if pwd and ident:
        upsert_pdf_password(db, user, identifier=ident, password=pwd)
    db.flush()
    return {
        "created": created,
        "skipped": skipped,
        "parser_used": parsed.get("parser_used"),
        "account_info": parsed.get("account_info"),
        "summary": parsed.get("summary"),
    }


# ---------- Statements ----------

@router.get("/statements", response_model=list[schemas.ShopStatementTxnOut])
def list_statements(
    status: Optional[str] = "pending",
    category: Optional[str] = None,
    q: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    query = db.query(models.ShopStatementTxn).filter(models.ShopStatementTxn.user_id == _uid(current_user))
    if status:
        query = query.filter(models.ShopStatementTxn.status == status)
    if category:
        query = query.filter(models.ShopStatementTxn.category == category)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(models.ShopStatementTxn.description.ilike(like))
    rows = query.order_by(models.ShopStatementTxn.txn_date.desc(), models.ShopStatementTxn.created_at.desc()).limit(500).all()
    return [_stmt_out(r) for r in rows]


@router.post("/statements/upload")
async def upload_statement(
    file: UploadFile = File(...),
    password: str = Form(""),
    identifier: str = Form(""),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty file")
    if len(raw) > MAX_PDF:
        raise HTTPException(400, "PDF is larger than 10 MB")
    from app.statement_parsers import is_pdf_encrypted

    filename = file.filename or "statement.pdf"
    hint = f"{filename} {identifier or ''}"
    pwd = resolve_pdf_password(
        db, current_user, raw, hint=hint, explicit=(password or "").strip() or None,
    )
    if is_pdf_encrypted(raw) and not pwd:
        raise HTTPException(400, "This PDF is password protected — add the bank password first")
    try:
        result = ingest_statement_bytes(
            db, current_user, raw, filename,
            password=pwd, identifier=identifier or "",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"Could not parse this PDF: {exc}") from exc
    db.commit()
    return result


def post_statement_txn(
    db: Session,
    user: models.User,
    txn_id: str,
    account_id: Optional[str] = None,
) -> models.FinanceTransaction:
    from app.routers import finance as fn

    uid = _uid(user)
    row = (
        db.query(models.ShopStatementTxn)
        .filter(models.ShopStatementTxn.id == txn_id, models.ShopStatementTxn.user_id == uid)
        .first()
    )
    if not row:
        raise LookupError("Statement row not found")
    if row.status == "posted" and row.finance_txn_id:
        raise RuntimeError("Already posted to Money Manager")
    if not row.amount or float(row.amount) <= 0:
        raise RuntimeError("Row needs an amount")

    fn.ensure_defaults(db, user)
    accounts = db.query(models.FinanceAccount).filter(models.FinanceAccount.user_id == uid).all()
    acc = None
    if account_id:
        acc = next((a for a in accounts if a.id == account_id), None)
        if not acc:
            raise RuntimeError("Account not found")
    if acc is None:
        want = (row.account_type or "").lower()
        if "card" in want:
            acc = next((a for a in accounts if a.account_type in ("card", "credit_card")), None)
        elif "cash" in want:
            acc = next((a for a in accounts if a.account_type == "cash"), None)
        else:
            acc = next((a for a in accounts if a.account_type == "bank"), None)
        acc = acc or (accounts[0] if accounts else None)
    if not acc:
        raise RuntimeError("Create a Money Manager account first")

    mapped_name, mapped_kind = PARSER_TO_FINANCE.get(row.category or "other", ("Other", "expense"))
    if row.direction == "credit" and mapped_kind == "expense":
        mapped_kind = "income"
        if mapped_name == "Other":
            mapped_name = "Other income"
    cats = db.query(models.FinanceCategory).filter(models.FinanceCategory.user_id == uid).all()
    cat = next((c for c in cats if c.name == mapped_name and c.kind == mapped_kind), None)
    txn_type = "income" if row.direction == "credit" else "expense"
    method = "credit_card" if (row.account_type or "").lower().find("card") >= 0 else "other"
    desc = (row.description or "").strip() or None
    payee = (desc or "Statement")[:255]
    ft = models.FinanceTransaction(
        user_id=uid, account_id=acc.id, category_id=cat.id if cat else None,
        txn_type=txn_type, amount=row.amount, txn_date=row.txn_date or datetime.utcnow().strftime("%Y-%m-%d"),
        payee=payee, description=desc, payment_method=method,
        source="statement", notes=f"PDF · {row.source_file or ''} · {row.bank_name or ''}".strip(" ·"),
    )
    db.add(ft)
    db.flush()
    row.status = "posted"
    row.finance_txn_id = ft.id
    db.commit()
    db.refresh(ft)
    return ft


@router.post("/statements/{txn_id}/post")
def post_one(
    txn_id: str,
    body: schemas.ShopStatementPostIn | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    try:
        ft = post_statement_txn(db, current_user, txn_id, account_id=(body.account_id if body else None))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "finance_txn_id": ft.id}


@router.post("/statements/{txn_id}/ignore", status_code=204)
def ignore_one(
    txn_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = (
        db.query(models.ShopStatementTxn)
        .filter(models.ShopStatementTxn.id == txn_id, models.ShopStatementTxn.user_id == _uid(current_user))
        .first()
    )
    if not row:
        raise HTTPException(404, "Row not found")
    row.status = "ignored"
    db.commit()
    return None


@router.get("/public/{token}/suggest")
def public_suggest(token: str, q: str = "", limit: int = 8, db: Session = Depends(get_db)):
    """Public-share typeahead — no login, token gates access to the list."""
    _share, lst = _list_by_token(db, token, bump=False)
    return suggest(db, q or "", limit=limit, user_id=lst.user_id)


@router.get("/public/{token}/page", response_class=HTMLResponse)
def public_page(token: str, request: Request, db: Session = Depends(get_db), err: str = "", ok: str = ""):
    from app.grocery import catalog_json_text, catalog_payload
    try:
        share, lst = _list_by_token(db, token)
        db.commit()
    except HTTPException:
        return HTMLResponse("<h1>List not found</h1>", status_code=404)
    catalog = catalog_payload(db, lst.user_id)
    names: dict[str, str] = {}
    return templates.TemplateResponse(request, "tracker_share_public.html", {
        "list": lst,
        "owner_name": _owner_name(db, lst, names),
        "items": [_item_out(db, i, names) for i in (lst.items or []) if i.status != "rejected"],
        "token": token,
        "err": err,
        "ok": ok,
        "catalog_json": catalog_json_text(db, lst.user_id),
        "suggest_url": f"/tracker/public/{token}/suggest",
        "groups": catalog["groups"],
        "revision": _list_revision(lst),
    })


@router.post("/public/{token}/items")
async def public_add_item(token: str, request: Request, db: Session = Depends(get_db)):
    from urllib.parse import quote
    form = await request.form()
    try:
        share, lst = _list_by_token(db, token)
    except HTTPException:
        return HTMLResponse("<h1>List not found</h1>", status_code=404)
    guest = str(form.get("guest_name") or "Guest").strip() or "Guest"
    blocked = {str(x).lower() for x in _json_list(lst.blocked_uids)}
    if guest.lower() in blocked:
        return RedirectResponse(f"/shop/{token}?err=blocked", status_code=302)
    name = str(form.get("name") or "").strip()
    if not name:
        return RedirectResponse(f"/shop/{token}?err=name", status_code=302)
    status = "approved" if _is_household(db, lst, guest) else "pending"
    body = schemas.ShopItemIn(
        name=name,
        quantity=float(form.get("quantity") or 1),
        unit=str(form.get("unit") or "") or None,
        guest_name=guest,
    )
    _item, merged = _add_item_row(db, lst, body, added_by="guest", status=status)
    _touch_list(lst)
    db.commit()
    if merged:
        return RedirectResponse(
            f"/shop/{token}?ok=merged&name={quote(str(_item.name))}&qty={money(_item.quantity)}",
            status_code=302,
        )
    return RedirectResponse(f"/shop/{token}?ok=added", status_code=302)


@router.post("/public/{token}/items/{item_id}/toggle")
def public_toggle(token: str, item_id: str, db: Session = Depends(get_db)):
    try:
        share, lst = _list_by_token(db, token)
    except HTTPException:
        return HTMLResponse("<h1>List not found</h1>", status_code=404)
    item = next((i for i in lst.items if i.id == item_id), None)
    if item and item.status == "approved":
        item.checked = not bool(item.checked)
        _touch_list(lst)
        db.commit()
    return RedirectResponse(f"/shop/{token}", status_code=302)


@router.post("/public/{token}/items/{item_id}/edit")
async def public_edit_item(token: str, item_id: str, request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    try:
        share, lst = _list_by_token(db, token)
    except HTTPException:
        return HTMLResponse("<h1>List not found</h1>", status_code=404)
    item = next((i for i in lst.items if i.id == item_id), None)
    if not item or item.status == "rejected":
        return RedirectResponse(f"/shop/{token}", status_code=302)
    name = str(form.get("name") or "").strip()
    if name:
        item.name = name
    qty = str(form.get("quantity") or "").strip()
    if qty:
        try:
            item.quantity = Decimal(qty)
        except Exception:
            pass
    unit = str(form.get("unit") or "").strip()
    item.unit = unit or None
    _recompute_total(lst)
    _touch_list(lst)
    db.commit()
    return RedirectResponse(f"/shop/{token}", status_code=302)
