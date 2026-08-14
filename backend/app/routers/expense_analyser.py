"""Expense Analyser API — Gmail spend review, separate from Money Manager."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import expense_analyser as ea
from app import models, schemas
from app.database import get_db
from app.deps import get_current_user, require_owner

router = APIRouter(prefix="/expense-analyser", tags=["expense-analyser"])


def _item_out(row: models.ExpenseAnalyserItem) -> schemas.ExpenseAnalyserItemOut:
    return schemas.ExpenseAnalyserItemOut(
        id=row.id,
        gmail_message_id=row.gmail_message_id,
        kind=row.kind,
        subject=row.subject,
        from_addr=row.from_addr,
        received_at=row.received_at,
        raw_snippet=row.raw_snippet,
        direction=row.direction,
        amount=float(row.amount) if row.amount is not None else None,
        currency=row.currency or "INR",
        payee=row.payee,
        txn_date=row.txn_date,
        payment_method=row.payment_method,
        suggested_category=row.suggested_category,
        confidence=float(row.confidence) if row.confidence is not None else None,
        status=row.status,
        match_txn_id=row.match_txn_id,
        finance_txn_id=row.finance_txn_id,
        notes=row.notes,
        created_at=row.created_at,
    )


@router.get("/status", response_model=schemas.ExpenseAnalyserStatusOut)
def status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    return schemas.ExpenseAnalyserStatusOut(**ea.status_dict(db, current_user))


@router.get("/items", response_model=list[schemas.ExpenseAnalyserItemOut])
def list_items(
    status: str | None = None,
    kind: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    rows = ea.list_items(db, current_user, status=status or None, kind=kind or None, limit=limit)
    return [_item_out(r) for r in rows]


@router.patch("/items/{item_id}", response_model=schemas.ExpenseAnalyserItemOut)
def patch_item(
    item_id: str,
    body: schemas.ExpenseAnalyserItemUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    try:
        row = ea.update_item(db, current_user, item_id, body.model_dump(exclude_unset=True))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return _item_out(row)


@router.post("/items/{item_id}/ignore", response_model=schemas.ExpenseAnalyserItemOut)
def ignore_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    try:
        row = ea.ignore_item(db, current_user, item_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return _item_out(row)


@router.post("/items/{item_id}/post")
def post_item(
    item_id: str,
    body: schemas.ExpenseAnalyserPostIn | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    body = body or schemas.ExpenseAnalyserPostIn()
    try:
        txn = ea.post_to_finance(
            db, current_user, item_id,
            account_id=body.account_id,
            category_id=body.category_id,
        )
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"ok": True, "finance_txn_id": txn.id}


@router.post("/sync", response_model=schemas.ExpenseAnalyserSyncOut)
def sync(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = ea.get_or_create(db, current_user)
    if not row.refresh_token_enc:
        raise HTTPException(400, "Connect Gmail first")
    result = ea.sync_gmail(db, current_user)
    return schemas.ExpenseAnalyserSyncOut(**result)


@router.post("/reconcile")
def reconcile(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    n = ea.reconnect_matches(db, current_user)
    return {"ok": True, "updated": n}


@router.put("/query", response_model=schemas.ExpenseAnalyserStatusOut)
def save_query(
    body: schemas.ExpenseAnalyserQueryIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    ea.save_query(db, current_user, body.sync_query)
    return schemas.ExpenseAnalyserStatusOut(**ea.status_dict(db, current_user))


@router.post("/disconnect", response_model=schemas.ExpenseAnalyserStatusOut)
def disconnect(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    ea.disconnect(db, current_user)
    return schemas.ExpenseAnalyserStatusOut(**ea.status_dict(db, current_user))
