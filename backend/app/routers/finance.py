"""Money Manager — accounts, ledger, stats, budgets, SMS/AI tagging."""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.config import settings, vault_now
from app.database import get_db
from app import models, schemas, crypto
from app.deps import require_enabled_module, get_current_user, require_owner, vault_id
from app.extract import enhance_scan
from app.finance_ai import (
    EXPENSE_CATEGORIES,
    INCOME_CATEGORIES, PAYMENT_METHODS, PAYMENT_LABELS,
    build_description, classify_message, split_messages,
)

router = APIRouter(prefix="/finance", tags=["finance"], dependencies=[Depends(require_enabled_module("finance"))])

ASSET_TYPES = {"cash", "bank", "wallet", "investment", "other"}
LIABILITY_TYPES = {"credit_card", "loan"}
ACCOUNT_TYPES = ("cash", "bank", "credit_card", "loan", "wallet", "investment", "other")
TXN_TYPES = ("expense", "income", "transfer")
CAT_COLORS = [
    "#FF6B7A", "#F5B942", "#3DDC97", "#5B8CFF", "#A89BFF",
    "#22D3EE", "#FB7185", "#84CC16", "#F97316", "#38BDF8",
]

_DEFAULT_ACCOUNTS = [
    ("Cash", "cash"),
    ("Bank", "bank"),
    ("Card", "credit_card"),
]


def _dec(val) -> Decimal:
    if val is None:
        return Decimal("0")
    if isinstance(val, Decimal):
        return val
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _f(val) -> float:
    return float(_dec(val))


def inr(val) -> str:
    n = _f(val)
    sign = "-" if n < 0 else ""
    n = abs(n)
    whole, frac = f"{n:.2f}".split(".")
    if len(whole) <= 3:
        body = whole
    else:
        last3, rest = whole[-3:], whole[:-3]
        parts = []
        while rest:
            parts.append(rest[-2:])
            rest = rest[:-2]
        body = ",".join(list(reversed(parts)) + [last3])
    return f"{sign}₹ {body}.{frac}"


def _month_bounds(year_month: str) -> tuple[str, str]:
    try:
        y, m = [int(p) for p in year_month.split("-")]
        last = calendar.monthrange(y, m)[1]
        return f"{y:04d}-{m:02d}-01", f"{y:04d}-{m:02d}-{last:02d}"
    except (ValueError, IndexError):
        today = datetime.utcnow()
        last = calendar.monthrange(today.year, today.month)[1]
        return f"{today:%Y-%m}-01", f"{today:%Y-%m}-{last:02d}"


def _shift_month(year_month: str, delta: int) -> str:
    y, m = [int(p) for p in year_month.split("-")]
    m += delta
    while m < 1:
        m += 12
        y -= 1
    while m > 12:
        m -= 12
        y += 1
    return f"{y:04d}-{m:02d}"


def _parse_ym(value: str | None) -> tuple[int, int] | None:
    if not value:
        return None
    try:
        dt = datetime.strptime(str(value).strip()[:7], "%Y-%m")
        return dt.year, dt.month
    except ValueError:
        return None


def _parse_day(value: str | None) -> date | None:
    if not value:
        return None
    raw = str(value).strip()
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        parsed = _parse_ym(raw)
        if parsed:
            return date(parsed[0], parsed[1], 1)
        return None


def _monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _fmt_day(day: date) -> str:
    return f"{day.day} {day.strftime('%b')}"


def _chart_window(
    period: str | None = None,
    year_month: str | None = None,
    week: str | None = None,
    year: int | str | None = None,
) -> dict:
    """Resolve week / month / year bounds. Month is the default."""
    today = vault_now().date()
    kind = (period or "month").strip().lower()
    if kind not in ("week", "month", "year"):
        kind = "month"

    if kind == "week":
        day = _parse_day(week)
        if day is None:
            ym = _parse_ym(year_month)
            if ym and (today.year, today.month) == ym:
                day = today
            elif ym:
                day = date(ym[0], ym[1], 1)
            else:
                day = today
        start = _monday(day)
        end = start + timedelta(days=6)
        return {
            "period": "week",
            "grain": "day",
            "start": start,
            "end": end,
            "year_month": f"{start.year:04d}-{start.month:02d}",
            "year": start.year,
            "week_start": start.isoformat(),
            "label": f"{_fmt_day(start)} – {_fmt_day(end)} {end.year}",
            "prev": (start - timedelta(days=7)).isoformat(),
            "next": (start + timedelta(days=7)).isoformat(),
            "days": 7,
            "is_current": start <= today <= end,
            "today_day": (today - start).days + 1 if start <= today <= end else None,
            "elapsed": min(max((today - start).days + 1, 0), 7) if today >= start else 7,
            "heatmap_pad": 0,
            "heat_dows": ["M", "T", "W", "T", "F", "S", "S"],
        }

    if kind == "year":
        try:
            y = int(year) if year not in (None, "") else None
        except (TypeError, ValueError):
            y = None
        if y is None:
            parsed = _parse_ym(year_month)
            y = parsed[0] if parsed else today.year
        if y < 1990 or y > 2100:
            y = today.year
        start = date(y, 1, 1)
        end = date(y, 12, 31)
        days = 366 if calendar.isleap(y) else 365
        is_current = today.year == y
        elapsed = (today - start).days + 1 if is_current else days
        return {
            "period": "year",
            "grain": "month",
            "start": start,
            "end": end,
            "year_month": f"{y:04d}-{(today.month if is_current else 12):02d}",
            "year": y,
            "week_start": None,
            "label": str(y),
            "prev": str(y - 1),
            "next": str(y + 1),
            "days": days,
            "is_current": is_current,
            "today_day": today.month if is_current else None,
            "elapsed": elapsed,
            "heatmap_pad": 0,
            "heat_dows": ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"],
        }

    parsed = _parse_ym(year_month)
    y, m = parsed if parsed else (today.year, today.month)
    last = calendar.monthrange(y, m)[1]
    start = date(y, m, 1)
    end = date(y, m, last)
    is_current = (today.year, today.month) == (y, m)
    return {
        "period": "month",
        "grain": "day",
        "start": start,
        "end": end,
        "year_month": f"{y:04d}-{m:02d}",
        "year": y,
        "week_start": None,
        "label": start.strftime("%b %Y"),
        "prev": _shift_month(f"{y:04d}-{m:02d}", -1),
        "next": _shift_month(f"{y:04d}-{m:02d}", 1),
        "days": last,
        "is_current": is_current,
        "today_day": today.day if is_current else None,
        "elapsed": today.day if is_current else last,
        "heatmap_pad": (start.weekday() + 1) % 7,
        "heat_dows": ["S", "M", "T", "W", "T", "F", "S"],
    }


def _txns_in_range(db: Session, uid: str, start: str, end: str):
    return _txn_query(db, uid).filter(
        models.FinanceTransaction.txn_date >= start,
        models.FinanceTransaction.txn_date <= end,
    ).all()


def _owned(db: Session, user: models.User):
    return vault_id(user)


def ensure_defaults(db: Session, user: models.User) -> None:
    uid = _owned(db, user)
    cats = db.query(models.FinanceCategory).filter(models.FinanceCategory.user_id == uid).all()
    have = {c.name.lower() for c in cats}
    changed = False
    if not cats:
        for i, name in enumerate(EXPENSE_CATEGORIES):
            db.add(models.FinanceCategory(
                user_id=uid, name=name, kind="expense",
                color=CAT_COLORS[i % len(CAT_COLORS)], is_system=True,
            ))
        for i, name in enumerate(INCOME_CATEGORIES):
            db.add(models.FinanceCategory(
                user_id=uid, name=name, kind="income",
                color=CAT_COLORS[i % len(CAT_COLORS)], is_system=True,
            ))
        changed = True
    else:
        for i, name in enumerate(EXPENSE_CATEGORIES + INCOME_CATEGORIES):
            if name.lower() in have:
                continue
            kind = "income" if name in INCOME_CATEGORIES else "expense"
            db.add(models.FinanceCategory(
                user_id=uid, name=name, kind=kind,
                color=CAT_COLORS[i % len(CAT_COLORS)], is_system=True,
            ))
            changed = True
    accts = db.query(models.FinanceAccount).filter(models.FinanceAccount.user_id == uid).all()
    have_types = {a.account_type for a in accts}
    had_no_accounts = not accts
    for name, kind in _DEFAULT_ACCOUNTS:
        if kind in have_types:
            continue
        db.add(models.FinanceAccount(
            user_id=uid, name=name, account_type=kind, opening_balance=0,
            is_default=had_no_accounts and not have_types,
        ))
        have_types.add(kind)
        changed = True
    if changed:
        db.commit()


def _get_account(db: Session, user: models.User, account_id: str) -> models.FinanceAccount:
    row = db.query(models.FinanceAccount).filter(
        models.FinanceAccount.id == account_id,
        models.FinanceAccount.user_id == _owned(db, user),
    ).first()
    if not row:
        raise HTTPException(404, "Account not found")
    return row


def _get_category(db: Session, user: models.User, category_id: str) -> models.FinanceCategory:
    row = db.query(models.FinanceCategory).filter(
        models.FinanceCategory.id == category_id,
        models.FinanceCategory.user_id == _owned(db, user),
    ).first()
    if not row:
        raise HTTPException(404, "Category not found")
    return row


def _account_balance(db: Session, account: models.FinanceAccount) -> Decimal:
    uid = account.user_id
    txns = _txn_query(db, uid).filter(
        (models.FinanceTransaction.account_id == account.id)
        | (models.FinanceTransaction.to_account_id == account.id),
    ).all()
    bal = _dec(account.opening_balance)
    liability = account.account_type in LIABILITY_TYPES
    for t in txns:
        amt = _dec(t.amount)
        if t.txn_type == "transfer":
            if t.account_id == account.id:
                bal -= amt
            if t.to_account_id == account.id:
                bal += amt
            continue
        if t.account_id != account.id:
            continue
        if liability:
            if t.txn_type == "expense":
                bal += amt
            else:
                bal -= amt
        else:
            if t.txn_type == "income":
                bal += amt
            else:
                bal -= amt
    return bal


def _cat_map(db: Session, uid: str) -> dict[str, models.FinanceCategory]:
    rows = db.query(models.FinanceCategory).filter(models.FinanceCategory.user_id == uid).all()
    return {c.id: c for c in rows}


def _acct_map(db: Session, uid: str) -> dict[str, models.FinanceAccount]:
    rows = db.query(models.FinanceAccount).filter(models.FinanceAccount.user_id == uid).all()
    return {a.id: a for a in rows}


def _category_label(cat, categories) -> str | None:
    """Parent / Sub when nested, else category name — used as title fallback."""
    if not cat:
        return None
    if cat.parent_id:
        parent = categories.get(cat.parent_id) if isinstance(categories, dict) else None
        if parent is None and not isinstance(categories, dict):
            parent = next((c for c in categories if c.id == cat.parent_id), None)
        if parent is not None:
            return f"{parent.name} / {cat.name}"
    return cat.name


def _txn_out(t: models.FinanceTransaction, accounts, categories) -> schemas.FinanceTxnOut:
    acc = accounts.get(t.account_id)
    to = accounts.get(t.to_account_id) if t.to_account_id else None
    cat = categories.get(t.category_id) if t.category_id else None
    return schemas.FinanceTxnOut(
        id=t.id, account_id=t.account_id, account_name=acc.name if acc else "",
        to_account_id=t.to_account_id, to_account_name=to.name if to else None,
        category_id=t.category_id, category_name=_category_label(cat, categories),
        category_color=cat.color if cat else None,
        txn_type=t.txn_type, amount=_f(t.amount), currency=t.currency or "INR",
        txn_date=t.txn_date, txn_time=t.txn_time, payee=t.payee, notes=t.notes,
        description=t.description, payment_method=t.payment_method, tags=t.tags,
        source=t.source or "manual", has_image=bool(t.image_path),
        deleted_at=t.deleted_at, created_at=t.created_at,
    )


def _txn_query(db: Session, uid: str, *, include_deleted: bool = False):
    q = db.query(models.FinanceTransaction).filter(models.FinanceTransaction.user_id == uid)
    if not include_deleted:
        q = q.filter(models.FinanceTransaction.deleted_at.is_(None))
    return q


def _account_out(db: Session, a: models.FinanceAccount) -> schemas.FinanceAccountOut:
    bal = _account_balance(db, a)
    return schemas.FinanceAccountOut(
        id=a.id, name=a.name, account_type=a.account_type, currency=a.currency or "INR",
        opening_balance=_f(a.opening_balance), credit_limit=_f(a.credit_limit) if a.credit_limit is not None else None,
        institution=a.institution, last4=a.last4, archived=bool(a.archived),
        no_default_categories=bool(a.no_default_categories), is_default=bool(a.is_default),
        balance=_f(bal), is_liability=a.account_type in LIABILITY_TYPES,
        created_at=a.created_at,
    )


def _set_default_account(db: Session, uid: str, keep_id: str) -> None:
    """Exactly one non-archived account may be default. Unset every other one first."""
    db.query(models.FinanceAccount).filter(
        models.FinanceAccount.user_id == uid,
        models.FinanceAccount.id != keep_id,
    ).update({"is_default": False})


def _month_ie(txns) -> tuple[Decimal, Decimal]:
    income = sum((_dec(t.amount) for t in txns if t.txn_type == "income"), Decimal("0"))
    expense = sum((_dec(t.amount) for t in txns if t.txn_type == "expense"), Decimal("0"))
    return income, expense


def _txns_in_month(db: Session, uid: str, year_month: str):
    start, end = _month_bounds(year_month)
    return _txn_query(db, uid).filter(
        models.FinanceTransaction.txn_date >= start,
        models.FinanceTransaction.txn_date <= end,
    ).all()


def _txns_before(db: Session, uid: str, year_month: str):
    start, _ = _month_bounds(year_month)
    return _txn_query(db, uid).filter(
        models.FinanceTransaction.txn_date < start,
    ).all()


def _account_for_method(accounts: list[models.FinanceAccount], method: str | None, override: models.FinanceAccount | None = None) -> models.FinanceAccount | None:
    if override:
        return override
    want = {
        "credit_card": "credit_card",
        "cash": "cash",
        "atm": "bank",
        "debit_card": "bank",
        "upi": "bank",
        "netbanking": "bank",
    }.get(method or "", "bank")
    return next((a for a in accounts if a.account_type == want), None) or (accounts[0] if accounts else None)


def _cash_account(accounts: list[models.FinanceAccount]) -> models.FinanceAccount | None:
    return next((a for a in accounts if a.account_type == "cash"), None)


def _clean_method(value: str | None) -> str | None:
    if not value:
        return None
    method = value.strip().lower().replace(" ", "_").replace("-", "_")
    return method if method in PAYMENT_METHODS else None


def _message_out(m: models.FinanceMessage) -> schemas.FinanceMessageOut:
    return schemas.FinanceMessageOut(
        id=m.id, raw_text=m.raw_text, direction=m.direction,
        amount=_f(m.amount) if m.amount is not None else None,
        payee=m.payee, txn_date=m.txn_date, payment_method=m.payment_method,
        category_id=m.category_id, suggested_category=m.suggested_category,
        confidence=_f(m.confidence) if m.confidence is not None else None,
        provider_used=m.provider_used, status=m.status,
        transaction_id=m.transaction_id, created_at=m.created_at,
    )


def _post_message_txn(
    db: Session,
    uid: str,
    msg: models.FinanceMessage,
    accounts: list[models.FinanceAccount],
    override: models.FinanceAccount | None = None,
) -> models.FinanceTransaction | None:
    if not msg.amount:
        return None
    method = _clean_method(msg.payment_method) or "other"
    desc = build_description(method, msg.payee, msg.suggested_category)
    if method == "atm" and msg.direction != "credit" and override is None:
        bank = next((a for a in accounts if a.account_type == "bank"), None)
        cash = _cash_account(accounts)
        if bank and cash:
            txn = models.FinanceTransaction(
                user_id=uid, account_id=bank.id, to_account_id=cash.id,
                category_id=msg.category_id, txn_type="transfer", amount=msg.amount,
                txn_date=msg.txn_date or datetime.utcnow().strftime("%Y-%m-%d"),
                payee=msg.payee or "ATM", notes=(msg.raw_text or "")[:400],
                description=desc or "ATM cash withdrawal", payment_method="atm",
                source="message", message_id=msg.id,
            )
            db.add(txn)
            db.flush()
            return txn
    acc = _account_for_method(accounts, method, override)
    if not acc:
        return None
    txn = models.FinanceTransaction(
        user_id=uid, account_id=acc.id, category_id=msg.category_id,
        txn_type="income" if msg.direction == "credit" else "expense",
        amount=msg.amount, txn_date=msg.txn_date or datetime.utcnow().strftime("%Y-%m-%d"),
        payee=msg.payee, notes=(msg.raw_text or "")[:400],
        description=desc, payment_method=method if method != "other" else None,
        source="message", message_id=msg.id,
    )
    db.add(txn)
    db.flush()
    return txn


def _category_out(
    c: models.FinanceCategory,
    accounts: dict | None = None,
    categories: dict | None = None,
) -> schemas.FinanceCategoryOut:
    acc = accounts.get(c.account_id) if accounts and c.account_id else None
    parent = categories.get(c.parent_id) if categories and c.parent_id else None
    return schemas.FinanceCategoryOut(
        id=c.id, name=c.name, kind=c.kind, color=c.color, is_system=bool(c.is_system),
        account_id=c.account_id, account_name=acc.name if acc else None,
        parent_id=c.parent_id, parent_name=parent.name if parent else None,
        scope="account" if c.account_id else "general",
    )


def _find_category(
    categories: list[models.FinanceCategory],
    name: str,
    kind: str,
    account_id: str | None = None,
    *,
    no_default_categories: bool = False,
) -> models.FinanceCategory | None:
    want = (name or "").strip().lower()
    if not want:
        return None
    if account_id:
        for c in categories:
            if c.name.lower() == want and c.kind == kind and c.account_id == account_id:
                return c
    if not no_default_categories:
        for c in categories:
            if c.name.lower() == want and c.kind == kind and not c.account_id:
                return c
    for c in categories:
        if c.name.lower() == want and c.kind == kind:
            return c
    if not no_default_categories:
        for c in categories:
            if c.name.lower() == want and (not c.account_id or c.account_id == account_id):
                return c
    return None


def _assert_category_for_account(
    cat: models.FinanceCategory | None,
    account: models.FinanceAccount,
) -> None:
    if not cat:
        return
    if cat.account_id and cat.account_id != account.id:
        raise HTTPException(400, "That category belongs to another account")
    if account.no_default_categories and not cat.account_id:
        raise HTTPException(400, "This account only allows its own categories")


def _get_txn(
    db: Session,
    user: models.User,
    txn_id: str,
    *,
    include_deleted: bool = False,
) -> models.FinanceTransaction:
    q = db.query(models.FinanceTransaction).filter(
        models.FinanceTransaction.id == txn_id,
        models.FinanceTransaction.user_id == _owned(db, user),
    )
    if not include_deleted:
        q = q.filter(models.FinanceTransaction.deleted_at.is_(None))
    row = q.first()
    if not row:
        raise HTTPException(404, "Transaction not found")
    return row


def _drop_txn_image(row: models.FinanceTransaction) -> None:
    if not row.image_path:
        return
    path = settings.STORAGE_DIR / row.image_path
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass
    row.image_path = None
    row.image_mime = None


def save_txn_image(
    db: Session,
    user: models.User,
    txn_id: str,
    raw: bytes,
    mime: str | None,
) -> models.FinanceTransaction:
    row = _get_txn(db, user, txn_id)
    mime = (mime or "image/jpeg").split(";")[0].strip().lower()
    if not mime.startswith("image/"):
        raise HTTPException(400, "Upload a photo (jpg, png, webp)")
    if mime.startswith("image/"):
        raw = enhance_scan(raw, mime)
        mime = "image/jpeg"
    size_mb = len(raw) / (1024 * 1024)
    if size_mb > settings.MAX_UPLOAD_MB:
        raise HTTPException(413, f"Photo exceeds {settings.MAX_UPLOAD_MB} MB")
    if not raw:
        raise HTTPException(400, "Empty photo")
    from app import quota
    old_size = 0
    if row.image_path:
        old = settings.STORAGE_DIR / row.image_path
        if old.is_file():
            try:
                old_size = old.stat().st_size
            except OSError:
                old_size = 0
    delta = len(raw) - old_size
    if delta > 0:
        quota.assert_can_store(db, user, delta)
    uid = _owned(db, user)
    dest_dir = settings.STORAGE_DIR / uid / "finance"
    dest_dir.mkdir(parents=True, exist_ok=True)
    _drop_txn_image(row)
    rel = f"{uid}/finance/{row.id}.enc"
    (settings.STORAGE_DIR / rel).write_bytes(crypto.encrypt_bytes(raw))
    row.image_path = rel
    row.image_mime = mime
    db.commit()
    db.refresh(row)
    return row


def _ai_bundle(db: Session, user: models.User) -> dict | None:
    from app.ai_providers import get_default_bundle
    from app.ai_usage import attach_log_context
    return attach_log_context(get_default_bundle(db, user), db, user, "finance_sms")


def _rule_dicts(db: Session, user: models.User, categories) -> list[dict]:
    uid = _owned(db, user)
    rows = db.query(models.FinanceRule).filter(models.FinanceRule.user_id == uid).all()
    out = []
    for r in rows:
        cat = categories.get(r.category_id) if r.category_id else None
        out.append({
            "match_text": r.match_text,
            "category": cat.name if cat else None,
            "category_id": r.category_id,
            "txn_type": r.txn_type,
            "payee": r.payee,
        })
    return out


# ---------- bootstrap / summary ----------
@router.get("/summary", response_model=schemas.FinanceSummaryOut)
def summary(
    year_month: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ensure_defaults(db, current_user)
    uid = _owned(db, current_user)
    ym = year_month or datetime.utcnow().strftime("%Y-%m")
    income, expense = _month_ie(_txns_in_month(db, uid, ym))
    prev_ym = _shift_month(ym, -1)
    prev_income, prev_expense = _month_ie(_txns_in_month(db, uid, prev_ym))
    open_income, open_expense = _month_ie(_txns_before(db, uid, ym))
    opening = open_income - open_expense
    month_total = income - expense
    accounts = db.query(models.FinanceAccount).filter(
        models.FinanceAccount.user_id == uid, models.FinanceAccount.archived.is_(False),
    ).all()
    assets = Decimal("0")
    liabilities = Decimal("0")
    for a in accounts:
        bal = _account_balance(db, a)
        if a.account_type in LIABILITY_TYPES:
            liabilities += bal
        else:
            assets += bal
    pending = db.query(models.FinanceMessage).filter(
        models.FinanceMessage.user_id == uid, models.FinanceMessage.status == "pending",
    ).count()
    return schemas.FinanceSummaryOut(
        year_month=ym, income=_f(income), expense=_f(expense), total=_f(month_total),
        opening=_f(opening), closing=_f(opening + month_total),
        prev_month=prev_ym, prev_income=_f(prev_income), prev_expense=_f(prev_expense),
        prev_total=_f(prev_income - prev_expense),
        assets=_f(assets), liabilities=_f(liabilities), net=_f(assets - liabilities),
        pending_messages=pending,
    )


def build_dashboard(db: Session, user: models.User, year_month: str | None = None) -> dict:
    """Home snapshot: totals, top category, biggest spend, recent rows, one insight."""
    ensure_defaults(db, user)
    ym = year_month or datetime.utcnow().strftime("%Y-%m")
    snap = summary(year_month=ym, db=db, current_user=user)
    report = reports(year_month=ym, kind="expense", db=db, current_user=user)
    ledger = month_ledger(db, user, ym)
    txns = ledger.get("txns") or []
    expenses = [t for t in txns if t.txn_type == "expense"]
    top_row = (report.get("rows") or [None])[0]
    highest = max(expenses, key=lambda t: t.amount, default=None)
    insight = "Add a few expenses to see where this month is going."
    if top_row and snap.expense > 0:
        pct = int(round(float(top_row.get("pct") or 0)))
        insight = f"{top_row['name']} is {pct}% of this month’s spend."
        if highest and highest.payee and highest.payee != top_row["name"]:
            insight += f" Largest single hit: {highest.payee} ({inr(highest.amount)})."
    elif snap.income > 0 and snap.expense == 0:
        insight = "Income is in and spend is still zero — a quiet month so far."
    y, m = [int(p) for p in ym.split("-")]
    return {
        "year_month": ym,
        "label": datetime(y, m, 1).strftime("%b %Y"),
        "prev": _shift_month(ym, -1),
        "next": _shift_month(ym, 1),
        "summary": snap,
        "top_category": top_row,
        "highest": highest,
        "recent": txns[:8],
        "insight": insight,
        "report_rows": (report.get("rows") or [])[:4],
    }


# ---------- accounts ----------
@router.get("/accounts", response_model=list[schemas.FinanceAccountOut])
def list_accounts(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    ensure_defaults(db, current_user)
    rows = db.query(models.FinanceAccount).filter(
        models.FinanceAccount.user_id == _owned(db, current_user),
    ).order_by(models.FinanceAccount.account_type, models.FinanceAccount.name).all()
    return [_account_out(db, a) for a in rows if not a.archived]


@router.post("/accounts", response_model=schemas.FinanceAccountOut)
def create_account(
    body: schemas.FinanceAccountIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    ensure_defaults(db, current_user)
    kind = body.account_type if body.account_type in ACCOUNT_TYPES else "cash"
    uid = _owned(db, current_user)
    existing = db.query(models.FinanceAccount).filter(
        models.FinanceAccount.user_id == uid, models.FinanceAccount.archived.is_(False),
    ).count()
    make_default = bool(body.is_default) or existing == 0  # first account is always the default
    row = models.FinanceAccount(
        user_id=uid, name=body.name.strip(), account_type=kind,
        currency=body.currency or "INR", opening_balance=_dec(body.opening_balance),
        credit_limit=_dec(body.credit_limit) if body.credit_limit is not None else None,
        institution=body.institution, last4=body.last4,
        no_default_categories=bool(body.no_default_categories),
        is_default=make_default,
    )
    db.add(row)
    db.flush()
    if make_default:
        _set_default_account(db, uid, row.id)
    db.commit()
    db.refresh(row)
    return _account_out(db, row)


@router.post("/accounts/{account_id}", response_model=schemas.FinanceAccountOut)
def update_account(
    account_id: str,
    body: schemas.FinanceAccountIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = _get_account(db, current_user, account_id)
    row.name = body.name.strip()
    row.account_type = body.account_type if body.account_type in ACCOUNT_TYPES else row.account_type
    row.opening_balance = _dec(body.opening_balance)
    row.credit_limit = _dec(body.credit_limit) if body.credit_limit is not None else None
    row.institution = body.institution
    row.last4 = body.last4
    row.no_default_categories = bool(body.no_default_categories)
    if body.is_default and not row.is_default:
        row.is_default = True
        db.flush()
        _set_default_account(db, row.user_id, row.id)
    elif not body.is_default:
        row.is_default = False
    db.commit()
    db.refresh(row)
    return _account_out(db, row)


@router.delete("/accounts/{account_id}")
def delete_account(
    account_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = _get_account(db, current_user, account_id)
    row.archived = True
    was_default = bool(row.is_default)
    row.is_default = False
    db.flush()
    if was_default:
        nxt = db.query(models.FinanceAccount).filter(
            models.FinanceAccount.user_id == row.user_id,
            models.FinanceAccount.archived.is_(False),
        ).order_by(models.FinanceAccount.created_at).first()
        if nxt:
            nxt.is_default = True
    db.commit()
    return {"ok": True}


# ---------- categories ----------
@router.get("/categories", response_model=list[schemas.FinanceCategoryOut])
def list_categories(
    account_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ensure_defaults(db, current_user)
    uid = _owned(db, current_user)
    query = db.query(models.FinanceCategory).filter(models.FinanceCategory.user_id == uid)
    if account_id:
        acc = _get_account(db, current_user, account_id)
        if acc.no_default_categories:
            query = query.filter(models.FinanceCategory.account_id == account_id)
        else:
            query = query.filter(
                (models.FinanceCategory.account_id.is_(None))
                | (models.FinanceCategory.account_id == account_id)
            )
    rows = query.order_by(models.FinanceCategory.kind, models.FinanceCategory.name).all()
    accounts = _acct_map(db, uid)
    cats = {c.id: c for c in rows}
    return [_category_out(c, accounts, cats) for c in rows]


@router.post("/categories", response_model=schemas.FinanceCategoryOut)
def create_category(
    body: schemas.FinanceCategoryIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    ensure_defaults(db, current_user)
    uid = _owned(db, current_user)
    acc_id = None
    if body.account_id:
        acc_id = _get_account(db, current_user, body.account_id).id
    parent = None
    kind = "income" if body.kind == "income" else "expense"
    if body.parent_id:
        parent = _get_category(db, current_user, body.parent_id)
        if parent.parent_id:
            raise HTTPException(400, "Only one subcategory level is allowed")
        kind = parent.kind
        if not acc_id:
            acc_id = parent.account_id
    row = models.FinanceCategory(
        user_id=uid, name=body.name.strip(),
        kind=kind,
        color=body.color or CAT_COLORS[0],
        account_id=acc_id,
        parent_id=parent.id if parent else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _category_out(row, _acct_map(db, uid), _cat_map(db, uid))


@router.delete("/categories/{category_id}")
def delete_category(
    category_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = _get_category(db, current_user, category_id)
    if row.is_system:
        raise HTTPException(400, "System categories stay; rename instead")
    kids = db.query(models.FinanceCategory).filter(
        models.FinanceCategory.user_id == row.user_id,
        models.FinanceCategory.parent_id == row.id,
    ).all()
    for kid in kids:
        kid.parent_id = None
    db.delete(row)
    db.commit()
    return {"ok": True}


# ---------- transactions ----------
@router.get("/transactions", response_model=list[schemas.FinanceTxnOut])
def list_transactions(
    year_month: Optional[str] = None,
    txn_type: Optional[str] = None,
    account_id: Optional[str] = None,
    q: Optional[str] = None,
    notes_only: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ensure_defaults(db, current_user)
    uid = _owned(db, current_user)
    query = _txn_query(db, uid)
    if year_month:
        start, end = _month_bounds(year_month)
        query = query.filter(models.FinanceTransaction.txn_date >= start, models.FinanceTransaction.txn_date <= end)
    if txn_type in TXN_TYPES:
        query = query.filter(models.FinanceTransaction.txn_type == txn_type)
    if account_id:
        query = query.filter(
            (models.FinanceTransaction.account_id == account_id)
            | (models.FinanceTransaction.to_account_id == account_id)
        )
    if q:
        like = f"%{q}%"
        query = query.filter(
            (models.FinanceTransaction.payee.ilike(like))
            | (models.FinanceTransaction.notes.ilike(like))
            | (models.FinanceTransaction.description.ilike(like))
        )
    if notes_only:
        query = query.filter(or_(
            and_(models.FinanceTransaction.notes.isnot(None), models.FinanceTransaction.notes != ""),
            and_(models.FinanceTransaction.description.isnot(None), models.FinanceTransaction.description != ""),
        ))
    rows = query.order_by(models.FinanceTransaction.txn_date.desc(), models.FinanceTransaction.created_at.desc()).all()
    accounts, categories = _acct_map(db, uid), _cat_map(db, uid)
    return [_txn_out(t, accounts, categories) for t in rows]


@router.post("/transactions", response_model=schemas.FinanceTxnOut)
def create_transaction(
    body: schemas.FinanceTxnIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    ensure_defaults(db, current_user)
    uid = _owned(db, current_user)
    acc = _get_account(db, current_user, body.account_id)
    txn_type = body.txn_type if body.txn_type in TXN_TYPES else "expense"
    to_id = None
    if txn_type == "transfer":
        if not body.to_account_id:
            raise HTTPException(400, "Transfer needs a destination account")
        dest = _get_account(db, current_user, body.to_account_id)
        to_id = dest.id
    if body.amount <= 0:
        raise HTTPException(400, "Amount must be greater than 0")
    if body.category_id:
        cat = _get_category(db, current_user, body.category_id)
        _assert_category_for_account(cat, acc)
    method = _clean_method(body.payment_method)
    desc = (body.description or "").strip() or None
    if not desc:
        desc = build_description(method, body.payee, None)
    row = models.FinanceTransaction(
        user_id=uid, account_id=acc.id, to_account_id=to_id,
        category_id=body.category_id, txn_type=txn_type, amount=_dec(body.amount),
        txn_date=body.txn_date, txn_time=body.txn_time, payee=body.payee,
        notes=body.notes, description=desc, payment_method=method,
        tags=body.tags, source="manual",
    )
    db.add(row)
    if body.frequency and body.frequency != "none":
        db.add(models.FinanceRecurring(
            user_id=uid, account_id=acc.id, category_id=body.category_id, txn_type=txn_type,
            amount=_dec(body.amount), payee=body.payee, notes=body.notes,
            frequency=body.frequency, next_due=body.txn_date, active=True,
        ))
    db.commit()
    db.refresh(row)
    return _txn_out(row, _acct_map(db, uid), _cat_map(db, uid))


@router.put("/transactions/{txn_id}", response_model=schemas.FinanceTxnOut)
def update_transaction(
    txn_id: str,
    body: schemas.FinanceTxnIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    ensure_defaults(db, current_user)
    row = _get_txn(db, current_user, txn_id)
    acc = _get_account(db, current_user, body.account_id)
    txn_type = body.txn_type if body.txn_type in TXN_TYPES else row.txn_type
    to_id = None
    if txn_type == "transfer":
        if not body.to_account_id:
            raise HTTPException(400, "Transfer needs a destination account")
        dest = _get_account(db, current_user, body.to_account_id)
        to_id = dest.id
    if body.amount <= 0:
        raise HTTPException(400, "Amount must be greater than 0")
    if body.category_id:
        cat = _get_category(db, current_user, body.category_id)
        _assert_category_for_account(cat, acc)
    method = _clean_method(body.payment_method)
    desc = (body.description or "").strip() or None
    if not desc:
        desc = build_description(method, body.payee, None)
    row.account_id = acc.id
    row.to_account_id = to_id
    row.category_id = body.category_id
    row.txn_type = txn_type
    row.amount = _dec(body.amount)
    row.txn_date = body.txn_date
    row.txn_time = body.txn_time
    row.payee = (body.payee or "").strip() or None
    row.notes = (body.notes or "").strip() or None
    row.description = desc
    row.payment_method = method
    if body.tags is not None:
        row.tags = body.tags
    db.commit()
    db.refresh(row)
    uid = _owned(db, current_user)
    return _txn_out(row, _acct_map(db, uid), _cat_map(db, uid))


@router.get("/transactions/{txn_id}", response_model=schemas.FinanceTxnOut)
def get_transaction(
    txn_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = _get_txn(db, current_user, txn_id)
    uid = _owned(db, current_user)
    return _txn_out(row, _acct_map(db, uid), _cat_map(db, uid))


@router.post("/transactions/bulk-delete")
def bulk_delete_transactions(
    body: schemas.BulkIds,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Delete many ledger rows owned by the current vault user."""
    require_owner(current_user)
    ids = [str(i).strip() for i in (body.ids or []) if str(i).strip()]
    if not ids:
        raise HTTPException(400, "Select at least one transaction")
    if len(ids) > 200:
        raise HTTPException(400, "Too many transactions (max 200)")
    uid = _owned(db, current_user)
    now = datetime.utcnow()
    rows = (
        _txn_query(db, uid)
        .filter(models.FinanceTransaction.id.in_(ids))
        .all()
    )
    for row in rows:
        row.deleted_at = now
    db.commit()
    return {"ok": True, "deleted": len(rows)}


@router.delete("/transactions/{txn_id}")
def delete_transaction(
    txn_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = _get_txn(db, current_user, txn_id)
    row.deleted_at = datetime.utcnow()
    db.commit()
    return {"ok": True}


@router.get("/trash", response_model=list[schemas.FinanceTxnOut])
def list_trash(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    uid = _owned(db, current_user)
    rows = (
        _txn_query(db, uid, include_deleted=True)
        .filter(models.FinanceTransaction.deleted_at.isnot(None))
        .order_by(models.FinanceTransaction.deleted_at.desc())
        .all()
    )
    accounts, categories = _acct_map(db, uid), _cat_map(db, uid)
    return [_txn_out(t, accounts, categories) for t in rows]


@router.post("/trash/empty")
def empty_trash(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    uid = _owned(db, current_user)
    rows = (
        _txn_query(db, uid, include_deleted=True)
        .filter(models.FinanceTransaction.deleted_at.isnot(None))
        .all()
    )
    for row in rows:
        _drop_txn_image(row)
        db.delete(row)
    db.commit()
    return {"ok": True, "deleted": len(rows)}


@router.post("/transactions/{txn_id}/restore", response_model=schemas.FinanceTxnOut)
def restore_transaction(
    txn_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = _get_txn(db, current_user, txn_id, include_deleted=True)
    row.deleted_at = None
    db.commit()
    db.refresh(row)
    uid = _owned(db, current_user)
    return _txn_out(row, _acct_map(db, uid), _cat_map(db, uid))


@router.post("/transactions/{txn_id}/permanent")
def permanent_delete_transaction(
    txn_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = _get_txn(db, current_user, txn_id, include_deleted=True)
    _drop_txn_image(row)
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/transactions/{txn_id}/image", response_model=schemas.FinanceTxnOut)
async def upload_transaction_image(
    txn_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    raw = await file.read()
    row = save_txn_image(db, current_user, txn_id, raw, file.content_type)
    uid = _owned(db, current_user)
    return _txn_out(row, _acct_map(db, uid), _cat_map(db, uid))


@router.get("/transactions/{txn_id}/image")
def get_transaction_image(
    txn_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    row = _get_txn(db, current_user, txn_id)
    if not row.image_path:
        raise HTTPException(404, "No photo on this entry")
    path = settings.STORAGE_DIR / row.image_path
    if not path.exists():
        raise HTTPException(404, "Photo missing on disk")
    plain = crypto.decrypt_bytes(path.read_bytes())
    return Response(content=plain, media_type=row.image_mime or "image/jpeg")


# ---------- budgets / recurring ----------
@router.get("/budgets", response_model=list[schemas.FinanceBudgetOut])
def list_budgets(
    year_month: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ensure_defaults(db, current_user)
    uid = _owned(db, current_user)
    ym = year_month or datetime.utcnow().strftime("%Y-%m")
    start, end = _month_bounds(ym)
    rows = db.query(models.FinanceBudget).filter(
        models.FinanceBudget.user_id == uid, models.FinanceBudget.year_month == ym,
    ).all()
    cats = _cat_map(db, uid)
    spent_map: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    txns = _txn_query(db, uid).filter(
        models.FinanceTransaction.txn_type == "expense",
        models.FinanceTransaction.txn_date >= start,
        models.FinanceTransaction.txn_date <= end,
    ).all()
    for t in txns:
        if t.category_id:
            spent_map[t.category_id] += _dec(t.amount)
    return [
        schemas.FinanceBudgetOut(
            id=b.id, category_id=b.category_id,
            category_name=cats[b.category_id].name if b.category_id in cats else "",
            year_month=b.year_month, amount=_f(b.amount), spent=_f(spent_map.get(b.category_id, 0)),
        )
        for b in rows
    ]


@router.post("/budgets", response_model=schemas.FinanceBudgetOut)
def create_budget(
    body: schemas.FinanceBudgetIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    cat = _get_category(db, current_user, body.category_id)
    row = models.FinanceBudget(
        user_id=_owned(db, current_user), category_id=cat.id,
        year_month=body.year_month, amount=_dec(body.amount),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return schemas.FinanceBudgetOut(
        id=row.id, category_id=row.category_id, category_name=cat.name,
        year_month=row.year_month, amount=_f(row.amount), spent=0,
    )


@router.delete("/budgets/{budget_id}")
def delete_budget(budget_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    row = db.query(models.FinanceBudget).filter(
        models.FinanceBudget.id == budget_id, models.FinanceBudget.user_id == _owned(db, current_user),
    ).first()
    if not row:
        raise HTTPException(404, "Budget not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.get("/recurring", response_model=list[schemas.FinanceRecurringOut])
def list_recurring(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    ensure_defaults(db, current_user)
    uid = _owned(db, current_user)
    rows = db.query(models.FinanceRecurring).filter(models.FinanceRecurring.user_id == uid).all()
    accounts, cats = _acct_map(db, uid), _cat_map(db, uid)
    return [
        schemas.FinanceRecurringOut(
            id=r.id, account_id=r.account_id, account_name=accounts[r.account_id].name if r.account_id in accounts else "",
            category_id=r.category_id, category_name=cats[r.category_id].name if r.category_id in cats else None,
            txn_type=r.txn_type, amount=_f(r.amount), payee=r.payee, notes=r.notes,
            frequency=r.frequency, next_due=r.next_due, active=bool(r.active),
        )
        for r in rows
    ]


@router.post("/recurring", response_model=schemas.FinanceRecurringOut)
def create_recurring(
    body: schemas.FinanceRecurringIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    acc = _get_account(db, current_user, body.account_id)
    row = models.FinanceRecurring(
        user_id=_owned(db, current_user), account_id=acc.id, category_id=body.category_id,
        txn_type=body.txn_type if body.txn_type in TXN_TYPES else "expense",
        amount=_dec(body.amount), payee=body.payee, notes=body.notes,
        frequency=body.frequency or "monthly", next_due=body.next_due, active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    cats = _cat_map(db, _owned(db, current_user))
    return schemas.FinanceRecurringOut(
        id=row.id, account_id=row.account_id, account_name=acc.name, category_id=row.category_id,
        category_name=cats[row.category_id].name if row.category_id in cats else None,
        txn_type=row.txn_type, amount=_f(row.amount), payee=row.payee, notes=row.notes,
        frequency=row.frequency, next_due=row.next_due, active=True,
    )


@router.post("/recurring/{rid}/pay")
def pay_recurring(rid: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    uid = _owned(db, current_user)
    row = db.query(models.FinanceRecurring).filter(
        models.FinanceRecurring.id == rid, models.FinanceRecurring.user_id == uid,
    ).first()
    if not row:
        raise HTTPException(404, "Recurring item not found")
    db.add(models.FinanceTransaction(
        user_id=uid, account_id=row.account_id, category_id=row.category_id,
        txn_type=row.txn_type, amount=row.amount, txn_date=row.next_due,
        payee=row.payee, notes=row.notes, source="recurring",
    ))
    try:
        due = datetime.strptime(row.next_due, "%Y-%m-%d")
    except ValueError:
        due = datetime.utcnow()
    if row.frequency == "weekly":
        due += timedelta(days=7)
    elif row.frequency == "yearly":
        due = due.replace(year=due.year + 1)
    else:
        month = due.month + 1
        year = due.year + (1 if month > 12 else 0)
        month = 1 if month > 12 else month
        day = min(due.day, calendar.monthrange(year, month)[1])
        due = due.replace(year=year, month=month, day=day)
    row.next_due = due.strftime("%Y-%m-%d")
    db.commit()
    return {"ok": True, "next_due": row.next_due}


# ---------- EMIs ----------
def _get_emi(db: Session, user: models.User, emi_id: str) -> models.FinanceEmi:
    row = db.query(models.FinanceEmi).filter(
        models.FinanceEmi.id == emi_id,
        models.FinanceEmi.user_id == _owned(db, user),
    ).first()
    if not row:
        raise HTTPException(404, "Recurring payment not found")
    return row


@router.get("/emis", response_model=list[schemas.FinanceEmiOut])
def list_emis(
    status: Optional[str] = None,
    kind: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app.emi import emi_out
    ensure_defaults(db, current_user)
    uid = _owned(db, current_user)
    rows = (
        db.query(models.FinanceEmi)
        .filter(models.FinanceEmi.user_id == uid)
        .order_by(models.FinanceEmi.next_due)
        .all()
    )
    accounts, cats = _acct_map(db, uid), _cat_map(db, uid)
    out = [schemas.FinanceEmiOut(**emi_out(db, r, accounts, cats)) for r in rows]
    if kind:
        from app.emi import normalize_kind
        want = normalize_kind(kind)
        out = [e for e in out if e.kind == want]
    if status in {"pending", "completed", "overdue"}:
        if status == "pending":
            out = [e for e in out if e.status in ("pending", "overdue")]
        else:
            out = [e for e in out if e.status == status]
    return out


@router.post("/emis", response_model=schemas.FinanceEmiOut)
def create_emi(
    body: schemas.FinanceEmiIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app.emi import emi_out, installment_dates, normalize_kind, sync_next_due
    require_owner(current_user)
    ensure_defaults(db, current_user)
    if body.amount <= 0:
        raise HTTPException(400, "Amount must be greater than 0")
    try:
        start = datetime.strptime(body.start_date[:10], "%Y-%m-%d").date()
        end = datetime.strptime(body.end_date[:10], "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, "Use YYYY-MM-DD for start and end dates")
    if end < start:
        raise HTTPException(400, "End date must be on or after start date")
    acc = _get_account(db, current_user, body.account_id)
    cat_id = None
    if body.category_id:
        cat_id = _get_category(db, current_user, body.category_id).id
    day = int(body.day_of_month or start.day)
    day = max(1, min(31, day))
    if not installment_dates(body.start_date[:10], body.end_date[:10], day):
        raise HTTPException(400, "No payment dates fall between start and end")
    uid = _owned(db, current_user)
    row = models.FinanceEmi(
        user_id=uid, name=body.name.strip(), kind=normalize_kind(body.kind),
        account_id=acc.id, category_id=cat_id,
        amount=_dec(body.amount), start_date=start.isoformat(), end_date=end.isoformat(),
        day_of_month=day, auto_post=bool(body.auto_post),
        notify_days=max(0, min(14, int(body.notify_days))),
        notes=(body.notes or "").strip() or None, active=True,
    )
    db.add(row)
    db.flush()
    sync_next_due(db, row)
    db.commit()
    db.refresh(row)
    return schemas.FinanceEmiOut(**emi_out(db, row, _acct_map(db, uid), _cat_map(db, uid)))


@router.post("/emis/{emi_id}/post", response_model=schemas.FinanceEmiOut)
def post_emi_now(
    emi_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app.emi import emi_out, post_installment
    require_owner(current_user)
    row = _get_emi(db, current_user, emi_id)
    txn = post_installment(db, row)
    if not txn and row.active and row.next_due and row.next_due > datetime.utcnow().strftime("%Y-%m-%d"):
        raise HTTPException(400, f"Next payment is on {row.next_due}")
    db.commit()
    uid = _owned(db, current_user)
    return schemas.FinanceEmiOut(**emi_out(db, row, _acct_map(db, uid), _cat_map(db, uid)))


@router.post("/emis/{emi_id}/pause", response_model=schemas.FinanceEmiOut)
def pause_emi(
    emi_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app.emi import emi_out
    require_owner(current_user)
    row = _get_emi(db, current_user, emi_id)
    row.active = not row.active
    if row.active:
        from app.emi import sync_next_due
        sync_next_due(db, row)
    db.commit()
    uid = _owned(db, current_user)
    return schemas.FinanceEmiOut(**emi_out(db, row, _acct_map(db, uid), _cat_map(db, uid)))


@router.delete("/emis/{emi_id}")
def delete_emi(
    emi_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = _get_emi(db, current_user, emi_id)
    db.query(models.FinanceTransaction).filter(models.FinanceTransaction.emi_id == row.id).update(
        {models.FinanceTransaction.emi_id: None}
    )
    db.delete(row)
    db.commit()
    return {"ok": True}


# ---------- reports ----------
@router.get("/reports")
def reports(
    year_month: Optional[str] = None,
    kind: str = Query("expense"),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    ensure_defaults(db, current_user)
    uid = _owned(db, current_user)
    ym = year_month or datetime.utcnow().strftime("%Y-%m")
    start, end = _month_bounds(ym)
    want = "income" if kind == "income" else "expense"
    txns = _txn_query(db, uid).filter(
        models.FinanceTransaction.txn_type == want,
        models.FinanceTransaction.txn_date >= start,
        models.FinanceTransaction.txn_date <= end,
    ).all()
    cats = _cat_map(db, uid)
    buckets: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    colors: dict[str, str] = {}
    for t in txns:
        cat = cats.get(t.category_id) if t.category_id else None
        name = cat.name if cat else "Other"
        buckets[name] += _dec(t.amount)
        colors[name] = (cat.color if cat and cat.color else CAT_COLORS[len(colors) % len(CAT_COLORS)])
    total = sum(buckets.values(), Decimal("0")) or Decimal("1")
    rows = sorted(
        ({"name": k, "amount": _f(v), "pct": _f(v * 100 / total), "color": colors[k]} for k, v in buckets.items()),
        key=lambda r: r["amount"], reverse=True,
    )
    return {"year_month": ym, "kind": want, "total": _f(sum(buckets.values(), Decimal("0"))), "rows": rows}


_HIST_BUCKETS = (
    (0, 100, "Under ₹100"),
    (100, 500, "₹100–500"),
    (500, 1000, "₹500–1k"),
    (1000, 2000, "₹1k–2k"),
    (2000, 5000, "₹2k–5k"),
    (5000, 10000, "₹5k–10k"),
    (10000, None, "₹10k+"),
)
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_CHART_PALETTE = CAT_COLORS + ["#3FE0C5", "#D4A657", "#9C8CF0", "#5FA8D3"]


def _slice_rows(buckets: dict[str, Decimal], counts: dict[str, int] | None = None, colors: dict[str, str] | None = None) -> list[dict]:
    total = sum(buckets.values(), Decimal("0")) or Decimal("1")
    rows = []
    for i, (name, amount) in enumerate(sorted(buckets.items(), key=lambda kv: kv[1], reverse=True)):
        color = (colors or {}).get(name) or _CHART_PALETTE[i % len(_CHART_PALETTE)]
        rows.append({
            "name": name,
            "amount": _f(amount),
            "count": int((counts or {}).get(name, 0)),
            "pct": _f(amount * 100 / total),
            "color": color,
        })
    return rows


def build_charts(
    db: Session,
    user: models.User,
    year_month: str | None = None,
    period: str | None = None,
    week: str | None = None,
    year: int | str | None = None,
) -> dict:
    """Dashboard series for week, month (default), or year."""
    ensure_defaults(db, user)
    win = _chart_window(period=period, year_month=year_month, week=week, year=year)
    uid = _owned(db, user)
    start, end = win["start"].isoformat(), win["end"].isoformat()
    ym = win["year_month"]
    grain = win["grain"]
    txns = _txns_in_range(db, uid, start, end)
    cats = _cat_map(db, uid)
    accts = _acct_map(db, uid)

    if grain == "month":
        daily = {
            f"{win['year']:04d}-{m:02d}": {
                "date": f"{win['year']:04d}-{m:02d}-01", "day": m,
                "income": 0.0, "expense": 0.0, "net": 0.0, "count": 0,
            }
            for m in range(1, 13)
        }
        daily_order = [f"{win['year']:04d}-{m:02d}" for m in range(1, 13)]
    else:
        daily = {}
        daily_order = []
        cursor = win["start"]
        idx = 1
        while cursor <= win["end"]:
            key = cursor.isoformat()
            day_num = idx if win["period"] == "week" else cursor.day
            daily[key] = {
                "date": key, "day": day_num,
                "income": 0.0, "expense": 0.0, "net": 0.0, "count": 0,
            }
            daily_order.append(key)
            cursor += timedelta(days=1)
            idx += 1
    cat_amt: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    cat_n: dict[str, int] = defaultdict(int)
    cat_color: dict[str, str] = {}
    method_amt: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    method_n: dict[str, int] = defaultdict(int)
    acct_amt: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    payee_amt: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    payee_n: dict[str, int] = defaultdict(int)
    payee_cat: dict[str, str] = {}
    weekday_amt = [Decimal("0")] * 7
    weekday_n = [0] * 7
    hist_amt = [Decimal("0")] * len(_HIST_BUCKETS)
    hist_n = [0] * len(_HIST_BUCKETS)
    income = Decimal("0")
    expense = Decimal("0")

    for t in txns:
        raw_date = t.txn_date or ""
        key = raw_date[:7] if grain == "month" else raw_date
        bucket = daily.get(key)
        amt = _dec(t.amount)
        if bucket is None:
            continue
        bucket["count"] += 1
        if t.txn_type == "income":
            bucket["income"] += _f(amt)
            income += amt
        elif t.txn_type == "expense":
            bucket["expense"] += _f(amt)
            expense += amt
            cat = cats.get(t.category_id) if t.category_id else None
            cname = cat.name if cat else "Other"
            cat_amt[cname] += amt
            cat_n[cname] += 1
            if cname not in cat_color:
                cat_color[cname] = (cat.color if cat and cat.color else _CHART_PALETTE[len(cat_color) % len(_CHART_PALETTE)])
            mkey = t.payment_method or "other"
            method_amt[PAYMENT_LABELS.get(mkey, mkey.replace("_", " ").title())] += amt
            method_n[PAYMENT_LABELS.get(mkey, mkey.replace("_", " ").title())] += 1
            aname = accts.get(t.account_id).name if accts.get(t.account_id) else "Account"
            acct_amt[aname] += amt
            pname = (t.payee or "").strip() or cname
            payee_amt[pname] += amt
            payee_n[pname] += 1
            payee_cat[pname] = cname
            try:
                wd = datetime.strptime(t.txn_date, "%Y-%m-%d").weekday()  # Mon=0
            except ValueError:
                wd = 0
            weekday_amt[wd] += amt
            weekday_n[wd] += 1
            val = _f(amt)
            placed = False
            for i, (lo, hi, _label) in enumerate(_HIST_BUCKETS):
                if val >= lo and (hi is None or val < hi):
                    hist_amt[i] += amt
                    hist_n[i] += 1
                    placed = True
                    break
            if not placed:
                hist_amt[-1] += amt
                hist_n[-1] += 1
        bucket["net"] = bucket["income"] - bucket["expense"]

    trend = []
    if win["period"] == "week":
        ws = win["start"]
        for i in range(-11, 1):
            s = ws + timedelta(days=7 * i)
            e = s + timedelta(days=6)
            t_income, t_expense = _month_ie(_txns_in_range(db, uid, s.isoformat(), e.isoformat()))
            trend.append({
                "year_month": s.isoformat(),
                "label": f"{s.day} {s.strftime('%b')}",
                "income": _f(t_income),
                "expense": _f(t_expense),
                "net": _f(t_income - t_expense),
            })
    elif win["period"] == "year":
        for m in range(1, 13):
            t_ym = f"{win['year']:04d}-{m:02d}"
            t_income, t_expense = _month_ie(_txns_in_month(db, uid, t_ym))
            trend.append({
                "year_month": t_ym,
                "label": datetime(win["year"], m, 1).strftime("%b"),
                "income": _f(t_income),
                "expense": _f(t_expense),
                "net": _f(t_income - t_expense),
            })
    else:
        for i in range(-11, 1):
            t_ym = _shift_month(ym, i)
            t_income, t_expense = _month_ie(_txns_in_month(db, uid, t_ym))
            ty, tm = [int(p) for p in t_ym.split("-")]
            trend.append({
                "year_month": t_ym,
                "label": datetime(ty, tm, 1).strftime("%b"),
                "income": _f(t_income),
                "expense": _f(t_expense),
                "net": _f(t_income - t_expense),
            })

    weekday_rows = []
    wd_total = sum(weekday_amt) or Decimal("1")
    for i, name in enumerate(_WEEKDAYS):
        weekday_rows.append({
            "name": name,
            "amount": _f(weekday_amt[i]),
            "count": weekday_n[i],
            "pct": _f(weekday_amt[i] * 100 / wd_total),
            "color": "#E8615C" if i < 5 else "#D4A657",
        })
    hist_rows = []
    hist_total = sum(hist_n) or 1
    for i, (_lo, _hi, label) in enumerate(_HIST_BUCKETS):
        hist_rows.append({
            "name": label,
            "amount": _f(hist_amt[i]),
            "count": hist_n[i],
            "pct": _f(hist_n[i] * 100 / hist_total),
            "color": "#4DD8E0",
        })

    last_day = win["days"]
    is_current = win["is_current"]
    today_day = win["today_day"]
    days_elapsed = win["elapsed"] or last_day
    days_logged = sum(1 for d in daily.values() if d["expense"] or d["income"])
    avg_day = _f(expense / last_day) if last_day else 0.0
    projected = _f(expense)
    if is_current and days_elapsed > 0:
        projected = _f(expense / days_elapsed * last_day)
    month_pct = _f(days_elapsed * 100 / last_day) if last_day else 0.0
    heatmap_pad = win["heatmap_pad"]

    spent_by_cat_id: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for t in txns:
        if t.txn_type == "expense" and t.category_id:
            spent_by_cat_id[t.category_id] += _dec(t.amount)
    if win["period"] == "year":
        yms = [f"{win['year']:04d}-{m:02d}" for m in range(1, 13)]
        budget_rows = db.query(models.FinanceBudget).filter(
            models.FinanceBudget.user_id == uid, models.FinanceBudget.year_month.in_(yms),
        ).all()
        merged: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        for b in budget_rows:
            merged[b.category_id] += _dec(b.amount)
        budget_items = [(cid, amt) for cid, amt in merged.items()]
        cap_scale = Decimal("1")
    else:
        budget_rows = db.query(models.FinanceBudget).filter(
            models.FinanceBudget.user_id == uid, models.FinanceBudget.year_month == ym,
        ).all()
        budget_items = [(b.category_id, _dec(b.amount)) for b in budget_rows]
        if win["period"] == "week":
            month_days = calendar.monthrange(win["start"].year, win["start"].month)[1] or 30
            cap_scale = Decimal(7) / Decimal(month_days)
        else:
            cap_scale = Decimal("1")
    budgets = []
    for cat_id, raw_cap in budget_items:
        cat = cats.get(cat_id)
        name = cat.name if cat else "Category"
        spent = spent_by_cat_id.get(cat_id, Decimal("0"))
        cap = (raw_cap * cap_scale) or Decimal("1")
        budgets.append({
            "name": name,
            "spent": _f(spent),
            "budget": _f(cap),
            "pct": _f(min(Decimal("999"), spent * 100 / cap)),
            "over": spent > cap,
            "color": (cat.color if cat and cat.color else "#F5B942"),
        })
    if not budgets:
        for row in _slice_rows(cat_amt, cat_n, cat_color)[:5]:
            budgets.append({
                "name": row["name"],
                "spent": row["amount"],
                "budget": 0.0,
                "pct": row["pct"],
                "over": False,
                "color": row["color"],
            })

    payee_rows = _slice_rows(payee_amt, payee_n)[:6]
    for row in payee_rows:
        row["meta"] = payee_cat.get(row["name"]) or "Expense"

    return {
        "year_month": ym,
        "period": win["period"],
        "grain": grain,
        "start": start,
        "end": end,
        "year": win["year"],
        "week_start": win["week_start"],
        "heat_dows": win["heat_dows"],
        "label": win["label"],
        "prev": win["prev"],
        "next": win["next"],
        "income": _f(income),
        "expense": _f(expense),
        "total": _f(income - expense),
        "txn_count": len(txns),
        "avg_day": avg_day,
        "days_in_month": last_day,
        "days_elapsed": days_elapsed,
        "days_logged": days_logged,
        "month_pct": month_pct,
        "projected": projected,
        "today_day": today_day,
        "heatmap_pad": heatmap_pad,
        "daily": [daily[k] for k in daily_order],
        "categories": _slice_rows(cat_amt, cat_n, cat_color),
        "methods": _slice_rows(method_amt, method_n),
        "accounts": _slice_rows(acct_amt),
        "payees": payee_rows,
        "weekday": weekday_rows,
        "histogram": hist_rows,
        "trend": trend,
        "budgets": budgets,
    }


@router.get("/charts", response_model=schemas.FinanceChartsOut)
def charts(
    year_month: Optional[str] = None,
    period: Optional[str] = None,
    week: Optional[str] = None,
    year: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return build_charts(db, current_user, year_month, period=period, week=week, year=year)


# ---------- AI keys (compat aliases → shared /ai/providers) ----------
@router.get("/ai-keys", response_model=list[schemas.FinanceAiKeyOut])
def list_ai_keys(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    from app import ai_providers as ap
    require_owner(current_user)
    return [schemas.FinanceAiKeyOut(**ap.provider_out(r)) for r in ap.list_providers(db, current_user)]


@router.post("/ai-keys", response_model=schemas.FinanceAiKeyOut)
def create_ai_key(
    body: schemas.FinanceAiKeyIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app import ai_providers as ap
    require_owner(current_user)
    row = ap.create_provider(
        db, current_user,
        name=body.name, kind=body.kind, api_key=body.api_key,
        base_url=body.base_url, model=body.model, is_default=body.is_default,
    )
    return schemas.FinanceAiKeyOut(**ap.provider_out(row))


@router.delete("/ai-keys/{key_id}")
def delete_ai_key(key_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    from app import ai_providers as ap
    require_owner(current_user)
    if not ap.delete_provider(db, current_user, key_id):
        raise HTTPException(404, "Provider not found")
    return {"ok": True}


@router.post("/ai-keys/{key_id}/test")
def test_ai_key(key_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    from app import ai_providers as ap
    require_owner(current_user)
    try:
        sample = ap.test_provider_row(db, current_user, key_id)
        return {"ok": True, "sample": sample}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"Provider test failed: {exc}") from exc


# ---------- rules ----------
@router.get("/rules", response_model=list[schemas.FinanceRuleOut])
def list_rules(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    uid = _owned(db, current_user)
    rows = db.query(models.FinanceRule).filter(models.FinanceRule.user_id == uid).all()
    cats = _cat_map(db, uid)
    return [
        schemas.FinanceRuleOut(
            id=r.id, match_text=r.match_text, category_id=r.category_id,
            category_name=cats[r.category_id].name if r.category_id in cats else None,
            txn_type=r.txn_type, payee=r.payee,
        )
        for r in rows
    ]


@router.post("/rules", response_model=schemas.FinanceRuleOut)
def create_rule(
    body: schemas.FinanceRuleIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = models.FinanceRule(
        user_id=_owned(db, current_user), match_text=body.match_text.strip(),
        category_id=body.category_id, txn_type=body.txn_type, payee=body.payee,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    cats = _cat_map(db, _owned(db, current_user))
    return schemas.FinanceRuleOut(
        id=row.id, match_text=row.match_text, category_id=row.category_id,
        category_name=cats[row.category_id].name if row.category_id in cats else None,
        txn_type=row.txn_type, payee=row.payee,
    )


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    row = db.query(models.FinanceRule).filter(
        models.FinanceRule.id == rule_id, models.FinanceRule.user_id == _owned(db, current_user),
    ).first()
    if not row:
        raise HTTPException(404, "Rule not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


# ---------- messages ----------
@router.get("/messages", response_model=list[schemas.FinanceMessageOut])
def list_messages(
    status: Optional[str] = "pending",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    uid = _owned(db, current_user)
    q = db.query(models.FinanceMessage).filter(models.FinanceMessage.user_id == uid)
    if status:
        q = q.filter(models.FinanceMessage.status == status)
    rows = q.order_by(models.FinanceMessage.created_at.desc()).limit(200).all()
    return [_message_out(m) for m in rows]


@router.post("/messages/ingest", response_model=list[schemas.FinanceMessageOut])
def ingest_messages(
    body: schemas.FinanceMessageIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    ensure_defaults(db, current_user)
    uid = _owned(db, current_user)
    chunks = split_messages(body.text)
    if not chunks:
        raise HTTPException(400, "Paste at least one bank / UPI message")
    cats = list(_cat_map(db, uid).values())
    cat_by_id = {c.id: c for c in cats}
    rules = _rule_dicts(db, current_user, cat_by_id)
    ai = _ai_bundle(db, current_user)
    accounts = [a for a in db.query(models.FinanceAccount).filter(
        models.FinanceAccount.user_id == uid, models.FinanceAccount.archived.is_(False),
    ).all()]
    default_account = None
    if body.account_id:
        default_account = _get_account(db, current_user, body.account_id)
    elif accounts:
        default_account = next((a for a in accounts if a.account_type == "bank"), accounts[0])
    created: list[models.FinanceMessage] = []
    for chunk in chunks:
        parsed = classify_message(chunk, rules=rules, ai=ai)
        direction = parsed.get("direction") or "unknown"
        kind = "income" if direction == "credit" else "expense"
        method = _clean_method(parsed.get("payment_method"))
        override = default_account if body.account_id else None
        target = _account_for_method(accounts, method, override)
        cat = _find_category(
            cats, parsed.get("category") or "", kind, target.id if target else None,
            no_default_categories=bool(target and target.no_default_categories),
        )
        msg = models.FinanceMessage(
            user_id=uid, raw_text=chunk, direction=direction,
            amount=_dec(parsed["amount"]) if parsed.get("amount") is not None else None,
            payee=parsed.get("payee"), txn_date=parsed.get("date"),
            payment_method=method, category_id=cat.id if cat else None,
            suggested_category=parsed.get("category"),
            confidence=_dec(parsed.get("confidence") or 0),
            provider_used=parsed.get("provider"), status="pending",
        )
        db.add(msg)
        db.flush()
        created.append(msg)
        conf = float(parsed.get("confidence") or 0)
        if body.auto_accept and parsed.get("amount") and direction in {"debit", "credit"} and conf >= 0.7:
            override = default_account if body.account_id else None
            txn = _post_message_txn(db, uid, msg, accounts, override)
            if txn:
                msg.status = "accepted"
                msg.transaction_id = txn.id
    db.commit()
    for m in created:
        db.refresh(m)
    return [_message_out(m) for m in created]


@router.post("/messages/{message_id}/accept", response_model=schemas.FinanceTxnOut)
def accept_message(
    message_id: str,
    account_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    uid = _owned(db, current_user)
    msg = db.query(models.FinanceMessage).filter(
        models.FinanceMessage.id == message_id, models.FinanceMessage.user_id == uid,
    ).first()
    if not msg:
        raise HTTPException(404, "Message not found")
    if msg.status == "accepted" and msg.transaction_id:
        txn = db.query(models.FinanceTransaction).filter(models.FinanceTransaction.id == msg.transaction_id).first()
        if txn:
            return _txn_out(txn, _acct_map(db, uid), _cat_map(db, uid))
    if not msg.amount:
        raise HTTPException(400, "No amount detected — edit and save as a normal transaction")
    accounts = [a for a in db.query(models.FinanceAccount).filter(
        models.FinanceAccount.user_id == uid, models.FinanceAccount.archived.is_(False),
    ).all()]
    override = _get_account(db, current_user, account_id) if account_id else None
    txn = _post_message_txn(db, uid, msg, accounts, override)
    if not txn:
        raise HTTPException(400, "Add an account first")
    msg.status = "accepted"
    msg.transaction_id = txn.id
    db.commit()
    db.refresh(txn)
    return _txn_out(txn, _acct_map(db, uid), _cat_map(db, uid))


@router.post("/messages/{message_id}/ignore")
def ignore_message(message_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    msg = db.query(models.FinanceMessage).filter(
        models.FinanceMessage.id == message_id,
        models.FinanceMessage.user_id == _owned(db, current_user),
    ).first()
    if not msg:
        raise HTTPException(404, "Message not found")
    msg.status = "ignored"
    db.commit()
    return {"ok": True}


def month_ledger(db: Session, user: models.User, year_month: str, q: str | None = None, notes_only: bool = False):
    """Grouped daily view used by the admin UI."""
    ensure_defaults(db, user)
    uid = _owned(db, user)
    start, end = _month_bounds(year_month)
    query = _txn_query(db, uid).filter(
        models.FinanceTransaction.txn_date >= start,
        models.FinanceTransaction.txn_date <= end,
    )
    if q:
        like = f"%{q}%"
        query = query.filter(
            (models.FinanceTransaction.payee.ilike(like))
            | (models.FinanceTransaction.notes.ilike(like))
            | (models.FinanceTransaction.description.ilike(like))
        )
    if notes_only:
        query = query.filter(or_(
            and_(models.FinanceTransaction.notes.isnot(None), models.FinanceTransaction.notes != ""),
            and_(models.FinanceTransaction.description.isnot(None), models.FinanceTransaction.description != ""),
        ))
    rows = query.order_by(models.FinanceTransaction.txn_date.desc(), models.FinanceTransaction.created_at.desc()).all()
    accounts, categories = _acct_map(db, uid), _cat_map(db, uid)
    items = [_txn_out(t, accounts, categories) for t in rows]
    income = sum(i.amount for i in items if i.txn_type == "income")
    expense = sum(i.amount for i in items if i.txn_type == "expense")
    prev_ym = _shift_month(year_month, -1)
    prev_income, prev_expense = _month_ie(_txns_in_month(db, uid, prev_ym))
    open_income, open_expense = _month_ie(_txns_before(db, uid, year_month))
    opening = _f(open_income - open_expense)
    month_total = income - expense
    days: dict[str, dict] = {}
    for item in items:
        bucket = days.setdefault(item.txn_date, {"date": item.txn_date, "income": 0.0, "expense": 0.0, "txns": []})
        if item.txn_type == "income":
            bucket["income"] += item.amount
        elif item.txn_type == "expense":
            bucket["expense"] += item.amount
        bucket["txns"].append(item)
    day_list = []
    for date, bucket in days.items():
        try:
            dt = datetime.strptime(date, "%Y-%m-%d")
            label = dt.strftime("%d %a %m.%Y")
        except ValueError:
            label = date
        bucket["label"] = label
        day_list.append(bucket)
    y, m = [int(p) for p in year_month.split("-")]
    last = calendar.monthrange(y, m)[1]
    cal = []
    first_wd = datetime(y, m, 1).weekday()  # Mon=0
    # Money Manager style often starts Sunday
    start_pad = (first_wd + 1) % 7
    cells = [None] * start_pad
    by_date = {d["date"]: d for d in day_list}
    for day in range(1, last + 1):
        key = f"{y:04d}-{m:02d}-{day:02d}"
        info = by_date.get(key, {"date": key, "income": 0, "expense": 0, "txns": []})
        cells.append(info)
    while len(cells) % 7:
        cells.append(None)
    weeks = [cells[i:i + 7] for i in range(0, len(cells), 7)]
    return {
        "year_month": year_month,
        "label": datetime(y, m, 1).strftime("%b %Y"),
        "prev": _shift_month(year_month, -1),
        "next": _shift_month(year_month, 1),
        "income": income,
        "expense": expense,
        "total": month_total,
        "opening": opening,
        "closing": opening + month_total,
        "prev_month": prev_ym,
        "prev_income": _f(prev_income),
        "prev_expense": _f(prev_expense),
        "prev_total": _f(prev_income - prev_expense),
        "days": day_list,
        "weeks": weeks,
        "txns": items,
        "inr": inr,
    }
