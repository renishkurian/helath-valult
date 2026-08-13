"""Monthly EMI schedule, auto-post, and status."""
from __future__ import annotations

import calendar
import logging
from datetime import date, datetime

from sqlalchemy.orm import Session

from app import models

log = logging.getLogger("vault.emi")

EMI_KINDS = {
    "emi": "EMI",
    "chitty": "Chitty",
    "loan": "Loan",
    "insurance": "Insurance",
    "rent": "Rent",
    "subscription": "Subscription",
    "other": "Other",
}
_KIND_CATEGORY = {
    "emi": "EMI / loans",
    "chitty": "EMI / loans",
    "loan": "EMI / loans",
    "insurance": "Insurance",
    "rent": "Rent",
    "subscription": "Subscriptions",
    "other": "Other",
}


def normalize_kind(kind: str | None) -> str:
    key = (kind or "emi").strip().lower()
    return key if key in EMI_KINDS else "other"


def kind_label(kind: str | None) -> str:
    return EMI_KINDS.get(normalize_kind(kind), "Other")


def _parse(d: str) -> date:
    return datetime.strptime(d[:10], "%Y-%m-%d").date()


def _on_month(year: int, month: int, day: int) -> date:
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(max(1, day), last))


def add_month(d: date, day: int) -> date:
    month = d.month + 1
    year = d.year
    if month > 12:
        month = 1
        year += 1
    return _on_month(year, month, day)


def first_due(start: str, end: str, day: int) -> date | None:
    start_d = _parse(start)
    end_d = _parse(end)
    day = max(1, min(31, int(day)))
    cur = _on_month(start_d.year, start_d.month, day)
    if cur < start_d:
        cur = add_month(cur, day)
    if cur > end_d:
        return None
    return cur


def installment_dates(start: str, end: str, day: int) -> list[date]:
    cur = first_due(start, end, day)
    if not cur:
        return []
    end_d = _parse(end)
    out: list[date] = []
    guard = 0
    while cur <= end_d and guard < 600:
        out.append(cur)
        cur = add_month(cur, day)
        guard += 1
    return out


def next_open_due(start: str, end: str, day: int, paid_dates: set[str], today: date | None = None) -> date | None:
    today = today or date.today()
    for d in installment_dates(start, end, day):
        key = d.isoformat()
        if key in paid_dates:
            continue
        return d
    return None


def _paid_dates(db: Session, emi_id: str) -> set[str]:
    rows = db.query(models.FinanceTransaction.txn_date).filter(
        models.FinanceTransaction.emi_id == emi_id,
    ).all()
    return {r[0][:10] for r in rows if r[0]}


def _emi_category_id(db: Session, uid: str, preferred: str | None, kind: str | None = None) -> str | None:
    if preferred:
        return preferred
    want = _KIND_CATEGORY.get(normalize_kind(kind), "Other")
    row = (
        db.query(models.FinanceCategory)
        .filter(
            models.FinanceCategory.user_id == uid,
            models.FinanceCategory.name == want,
            models.FinanceCategory.kind == "expense",
        )
        .first()
    )
    return row.id if row else None


def emi_out(db: Session, row: models.FinanceEmi, accounts=None, categories=None) -> dict:
    dates = installment_dates(row.start_date, row.end_date, int(row.day_of_month or 1))
    paid = _paid_dates(db, row.id)
    total = len(dates)
    paid_count = sum(1 for d in dates if d.isoformat() in paid)
    remaining = max(0, total - paid_count)
    today = date.today()
    nxt = row.next_due
    if not row.active or remaining == 0 or (nxt and _parse(nxt) > _parse(row.end_date)):
        status = "completed"
    elif nxt and _parse(nxt) < today:
        status = "overdue"
    else:
        status = "pending"
    acc_name = ""
    cat_name = None
    if accounts and row.account_id in accounts:
        acc_name = accounts[row.account_id].name
    if categories and row.category_id and row.category_id in categories:
        cat_name = categories[row.category_id].name
    return {
        "id": row.id,
        "name": row.name,
        "kind": normalize_kind(getattr(row, "kind", None)),
        "kind_label": kind_label(getattr(row, "kind", None)),
        "account_id": row.account_id,
        "account_name": acc_name,
        "category_id": row.category_id,
        "category_name": cat_name,
        "amount": float(row.amount or 0),
        "start_date": row.start_date,
        "end_date": row.end_date,
        "day_of_month": int(row.day_of_month or 1),
        "next_due": row.next_due,
        "auto_post": bool(row.auto_post),
        "notify_days": int(row.notify_days or 2),
        "notes": row.notes,
        "active": bool(row.active),
        "status": status,
        "total_installments": total,
        "paid_count": paid_count,
        "remaining": remaining,
        "created_at": row.created_at,
    }


def sync_next_due(db: Session, row: models.FinanceEmi) -> None:
    paid = _paid_dates(db, row.id)
    nxt = next_open_due(row.start_date, row.end_date, int(row.day_of_month or 1), paid)
    row.next_due = nxt.isoformat() if nxt else None
    if not nxt:
        row.active = False


def post_installment(db: Session, row: models.FinanceEmi) -> models.FinanceTransaction | None:
    if not row.next_due:
        sync_next_due(db, row)
    if not row.next_due or not row.active:
        return None
    due = row.next_due[:10]
    if due > date.today().isoformat():
        return None
    if due > row.end_date[:10]:
        row.active = False
        row.next_due = None
        return None
    existing = (
        db.query(models.FinanceTransaction)
        .filter(
            models.FinanceTransaction.emi_id == row.id,
            models.FinanceTransaction.txn_date == due,
        )
        .first()
    )
    if existing:
        sync_next_due(db, row)
        return existing
    cat_id = _emi_category_id(db, row.user_id, row.category_id, getattr(row, "kind", None))
    label = kind_label(getattr(row, "kind", None))
    txn = models.FinanceTransaction(
        user_id=row.user_id,
        account_id=row.account_id,
        category_id=cat_id,
        txn_type="expense",
        amount=row.amount,
        txn_date=due,
        payee=row.name,
        notes=row.notes,
        description=f"{label} · {row.name}",
        source="emi",
        emi_id=row.id,
    )
    db.add(txn)
    db.flush()
    sync_next_due(db, row)
    return txn


def run_due_emis() -> int:
    from app.database import SessionLocal
    db = SessionLocal()
    posted = 0
    try:
        today = date.today().isoformat()
        rows = (
            db.query(models.FinanceEmi)
            .filter(
                models.FinanceEmi.active.is_(True),
                models.FinanceEmi.auto_post.is_(True),
                models.FinanceEmi.next_due.isnot(None),
                models.FinanceEmi.next_due <= today,
            )
            .all()
        )
        for row in rows:
            try:
                txn = post_installment(db, row)
                if txn:
                    posted += 1
                    log.info("Posted EMI %s on %s", row.name, row.next_due)
            except Exception:
                log.exception("EMI post failed for %s", row.id)
        db.commit()
    finally:
        db.close()
    return posted
