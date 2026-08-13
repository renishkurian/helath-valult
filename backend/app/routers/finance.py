"""Money Manager — accounts, ledger, stats, budgets, SMS/AI tagging."""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, crypto
from app.deps import get_current_user, require_owner, vault_id
from app.finance_ai import (
    DEFAULT_BASES, DEFAULT_MODELS, EXPENSE_CATEGORIES,
    INCOME_CATEGORIES, classify_message, split_messages, test_provider,
)

router = APIRouter(prefix="/finance", tags=["finance"])

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


def _owned(db: Session, user: models.User):
    return vault_id(user)


def ensure_defaults(db: Session, user: models.User) -> None:
    uid = _owned(db, user)
    if db.query(models.FinanceCategory).filter(models.FinanceCategory.user_id == uid).first():
        return
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
    for name, kind in _DEFAULT_ACCOUNTS:
        db.add(models.FinanceAccount(user_id=uid, name=name, account_type=kind, opening_balance=0))
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
    txns = db.query(models.FinanceTransaction).filter(
        models.FinanceTransaction.user_id == uid,
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


def _txn_out(t: models.FinanceTransaction, accounts, categories) -> schemas.FinanceTxnOut:
    acc = accounts.get(t.account_id)
    to = accounts.get(t.to_account_id) if t.to_account_id else None
    cat = categories.get(t.category_id) if t.category_id else None
    return schemas.FinanceTxnOut(
        id=t.id, account_id=t.account_id, account_name=acc.name if acc else "",
        to_account_id=t.to_account_id, to_account_name=to.name if to else None,
        category_id=t.category_id, category_name=cat.name if cat else None,
        category_color=cat.color if cat else None,
        txn_type=t.txn_type, amount=_f(t.amount), currency=t.currency or "INR",
        txn_date=t.txn_date, txn_time=t.txn_time, payee=t.payee, notes=t.notes,
        description=t.description, tags=t.tags, source=t.source or "manual",
        created_at=t.created_at,
    )


def _account_out(db: Session, a: models.FinanceAccount) -> schemas.FinanceAccountOut:
    bal = _account_balance(db, a)
    return schemas.FinanceAccountOut(
        id=a.id, name=a.name, account_type=a.account_type, currency=a.currency or "INR",
        opening_balance=_f(a.opening_balance), credit_limit=_f(a.credit_limit) if a.credit_limit is not None else None,
        institution=a.institution, last4=a.last4, archived=bool(a.archived),
        balance=_f(bal), is_liability=a.account_type in LIABILITY_TYPES,
        created_at=a.created_at,
    )


def _find_category(categories: list[models.FinanceCategory], name: str, kind: str) -> models.FinanceCategory | None:
    want = (name or "").strip().lower()
    for c in categories:
        if c.name.lower() == want and c.kind == kind:
            return c
    for c in categories:
        if c.name.lower() == want:
            return c
    return None


def _ai_bundle(db: Session, user: models.User) -> dict | None:
    uid = _owned(db, user)
    row = (
        db.query(models.FinanceAiProvider)
        .filter(
            models.FinanceAiProvider.user_id == uid,
            models.FinanceAiProvider.enabled.is_(True),
            models.FinanceAiProvider.is_default.is_(True),
        )
        .first()
    )
    if not row:
        row = (
            db.query(models.FinanceAiProvider)
            .filter(models.FinanceAiProvider.user_id == uid, models.FinanceAiProvider.enabled.is_(True))
            .first()
        )
    if not row:
        return None
    return {
        "kind": row.kind,
        "api_key": crypto.decrypt_text(row.api_key_enc) if row.api_key_enc else None,
        "model": row.model,
        "base_url": row.base_url,
        "name": row.name,
    }


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
    start, end = _month_bounds(ym)
    txns = db.query(models.FinanceTransaction).filter(
        models.FinanceTransaction.user_id == uid,
        models.FinanceTransaction.txn_date >= start,
        models.FinanceTransaction.txn_date <= end,
    ).all()
    income = sum((_dec(t.amount) for t in txns if t.txn_type == "income"), Decimal("0"))
    expense = sum((_dec(t.amount) for t in txns if t.txn_type == "expense"), Decimal("0"))
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
        year_month=ym, income=_f(income), expense=_f(expense), total=_f(income - expense),
        assets=_f(assets), liabilities=_f(liabilities), net=_f(assets - liabilities),
        pending_messages=pending,
    )


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
    row = models.FinanceAccount(
        user_id=_owned(db, current_user), name=body.name.strip(), account_type=kind,
        currency=body.currency or "INR", opening_balance=_dec(body.opening_balance),
        credit_limit=_dec(body.credit_limit) if body.credit_limit is not None else None,
        institution=body.institution, last4=body.last4,
    )
    db.add(row)
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
    db.commit()
    return {"ok": True}


# ---------- categories ----------
@router.get("/categories", response_model=list[schemas.FinanceCategoryOut])
def list_categories(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    ensure_defaults(db, current_user)
    rows = db.query(models.FinanceCategory).filter(
        models.FinanceCategory.user_id == _owned(db, current_user),
    ).order_by(models.FinanceCategory.kind, models.FinanceCategory.name).all()
    return [
        schemas.FinanceCategoryOut(id=c.id, name=c.name, kind=c.kind, color=c.color, is_system=bool(c.is_system))
        for c in rows
    ]


@router.post("/categories", response_model=schemas.FinanceCategoryOut)
def create_category(
    body: schemas.FinanceCategoryIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    ensure_defaults(db, current_user)
    row = models.FinanceCategory(
        user_id=_owned(db, current_user), name=body.name.strip(),
        kind="income" if body.kind == "income" else "expense",
        color=body.color or CAT_COLORS[0],
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return schemas.FinanceCategoryOut(id=row.id, name=row.name, kind=row.kind, color=row.color, is_system=False)


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
    query = db.query(models.FinanceTransaction).filter(models.FinanceTransaction.user_id == uid)
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
    row = models.FinanceTransaction(
        user_id=uid, account_id=acc.id, to_account_id=to_id,
        category_id=body.category_id, txn_type=txn_type, amount=_dec(body.amount),
        txn_date=body.txn_date, txn_time=body.txn_time, payee=body.payee,
        notes=body.notes, description=body.description, tags=body.tags, source="manual",
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


@router.delete("/transactions/{txn_id}")
def delete_transaction(
    txn_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = db.query(models.FinanceTransaction).filter(
        models.FinanceTransaction.id == txn_id,
        models.FinanceTransaction.user_id == _owned(db, current_user),
    ).first()
    if not row:
        raise HTTPException(404, "Transaction not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


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
    txns = db.query(models.FinanceTransaction).filter(
        models.FinanceTransaction.user_id == uid,
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
    txns = db.query(models.FinanceTransaction).filter(
        models.FinanceTransaction.user_id == uid,
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


# ---------- AI keys ----------
@router.get("/ai-keys", response_model=list[schemas.FinanceAiKeyOut])
def list_ai_keys(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    rows = db.query(models.FinanceAiProvider).filter(
        models.FinanceAiProvider.user_id == _owned(db, current_user),
    ).order_by(models.FinanceAiProvider.created_at.desc()).all()
    return [
        schemas.FinanceAiKeyOut(
            id=r.id, name=r.name, kind=r.kind, base_url=r.base_url, model=r.model,
            is_default=bool(r.is_default), enabled=bool(r.enabled), has_key=bool(r.api_key_enc),
        )
        for r in rows
    ]


@router.post("/ai-keys", response_model=schemas.FinanceAiKeyOut)
def create_ai_key(
    body: schemas.FinanceAiKeyIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    uid = _owned(db, current_user)
    if body.is_default:
        db.query(models.FinanceAiProvider).filter(models.FinanceAiProvider.user_id == uid).update({"is_default": False})
    row = models.FinanceAiProvider(
        user_id=uid, name=body.name.strip(), kind=body.kind,
        api_key_enc=crypto.encrypt_text(body.api_key) if body.api_key else None,
        base_url=body.base_url or DEFAULT_BASES.get(body.kind),
        model=body.model or DEFAULT_MODELS.get(body.kind),
        is_default=body.is_default, enabled=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return schemas.FinanceAiKeyOut(
        id=row.id, name=row.name, kind=row.kind, base_url=row.base_url, model=row.model,
        is_default=row.is_default, enabled=True, has_key=bool(row.api_key_enc),
    )


@router.delete("/ai-keys/{key_id}")
def delete_ai_key(key_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    row = db.query(models.FinanceAiProvider).filter(
        models.FinanceAiProvider.id == key_id, models.FinanceAiProvider.user_id == _owned(db, current_user),
    ).first()
    if not row:
        raise HTTPException(404, "Provider not found")
    db.delete(row)
    db.commit()
    return {"ok": True}


@router.post("/ai-keys/{key_id}/test")
def test_ai_key(key_id: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    row = db.query(models.FinanceAiProvider).filter(
        models.FinanceAiProvider.id == key_id, models.FinanceAiProvider.user_id == _owned(db, current_user),
    ).first()
    if not row:
        raise HTTPException(404, "Provider not found")
    try:
        sample = test_provider(
            row.kind, crypto.decrypt_text(row.api_key_enc) if row.api_key_enc else None, row.model, row.base_url,
        )
        return {"ok": True, "sample": sample}
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
    return [
        schemas.FinanceMessageOut(
            id=m.id, raw_text=m.raw_text, direction=m.direction, amount=_f(m.amount) if m.amount is not None else None,
            payee=m.payee, txn_date=m.txn_date, category_id=m.category_id, suggested_category=m.suggested_category,
            confidence=_f(m.confidence) if m.confidence is not None else None, provider_used=m.provider_used,
            status=m.status, transaction_id=m.transaction_id, created_at=m.created_at,
        )
        for m in rows
    ]


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
        cat = _find_category(cats, parsed.get("category") or "", kind)
        msg = models.FinanceMessage(
            user_id=uid, raw_text=chunk, direction=direction,
            amount=_dec(parsed["amount"]) if parsed.get("amount") is not None else None,
            payee=parsed.get("payee"), txn_date=parsed.get("date"),
            category_id=cat.id if cat else None,
            suggested_category=parsed.get("category"),
            confidence=_dec(parsed.get("confidence") or 0),
            provider_used=parsed.get("provider"), status="pending",
        )
        db.add(msg)
        db.flush()
        created.append(msg)
        conf = float(parsed.get("confidence") or 0)
        if body.auto_accept and default_account and parsed.get("amount") and direction in {"debit", "credit"} and conf >= 0.7:
            txn = models.FinanceTransaction(
                user_id=uid, account_id=default_account.id, category_id=msg.category_id,
                txn_type="income" if direction == "credit" else "expense",
                amount=msg.amount, txn_date=msg.txn_date or datetime.utcnow().strftime("%Y-%m-%d"),
                payee=msg.payee, notes=chunk[:400], source="message", message_id=msg.id,
            )
            db.add(txn)
            db.flush()
            msg.status = "accepted"
            msg.transaction_id = txn.id
    db.commit()
    for m in created:
        db.refresh(m)
    return [
        schemas.FinanceMessageOut(
            id=m.id, raw_text=m.raw_text, direction=m.direction, amount=_f(m.amount) if m.amount is not None else None,
            payee=m.payee, txn_date=m.txn_date, category_id=m.category_id, suggested_category=m.suggested_category,
            confidence=_f(m.confidence) if m.confidence is not None else None, provider_used=m.provider_used,
            status=m.status, transaction_id=m.transaction_id, created_at=m.created_at,
        )
        for m in created
    ]


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
    acc = None
    if account_id:
        acc = _get_account(db, current_user, account_id)
    else:
        acc = db.query(models.FinanceAccount).filter(
            models.FinanceAccount.user_id == uid, models.FinanceAccount.archived.is_(False),
        ).first()
    if not acc:
        raise HTTPException(400, "Add an account first")
    txn = models.FinanceTransaction(
        user_id=uid, account_id=acc.id, category_id=msg.category_id,
        txn_type="income" if msg.direction == "credit" else "expense",
        amount=msg.amount, txn_date=msg.txn_date or datetime.utcnow().strftime("%Y-%m-%d"),
        payee=msg.payee, notes=msg.raw_text[:400], source="message", message_id=msg.id,
    )
    db.add(txn)
    db.flush()
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
    query = db.query(models.FinanceTransaction).filter(
        models.FinanceTransaction.user_id == uid,
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
    days: dict[str, dict] = {}
    for item in items:
        bucket = days.setdefault(item.txn_date, {"date": item.txn_date, "income": 0.0, "expense": 0.0, "items": []})
        if item.txn_type == "income":
            bucket["income"] += item.amount
        elif item.txn_type == "expense":
            bucket["expense"] += item.amount
        bucket["items"].append(item)
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
        info = by_date.get(key, {"date": key, "income": 0, "expense": 0, "items": []})
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
        "total": income - expense,
        "days": day_list,
        "weeks": weeks,
        "items": items,
        "inr": inr,
    }
