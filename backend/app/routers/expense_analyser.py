"""Expense Analyser API — Gmail spend review, separate from Money Manager."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import expense_analyser as ea
from app import models, schemas
from app.database import get_db
from app.deps import require_enabled_module, get_current_user, require_owner, vault_id

router = APIRouter(prefix="/expense-analyser", tags=["expense-analyser"], dependencies=[Depends(require_enabled_module("expense"))])


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
    statuses: str | None = None,
    kind: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    status_list = [s.strip() for s in (statuses or "").split(",") if s.strip()] or None
    rows = ea.list_items(
        db, current_user,
        status=status or None, statuses=status_list, kind=kind or None,
        limit=limit, offset=offset,
    )
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
            subcategory_id=body.subcategory_id,
            new_category=body.new_category,
            new_subcategory=body.new_subcategory,
            payee=body.payee,
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
    result = ea.sync_gmail(db, current_user, trigger="manual")
    return schemas.ExpenseAnalyserSyncOut(**result)


@router.get("/sync-logs", response_model=list[schemas.ExpenseAnalyserSyncLogOut])
def sync_logs(
    limit: int = 30,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    rows = ea.list_sync_logs(db, current_user, limit=limit)
    return [
        schemas.ExpenseAnalyserSyncLogOut(
            id=r.id, trigger=r.trigger, ok=bool(r.ok),
            fetched=r.fetched or 0, created=r.created or 0, skipped=r.skipped or 0,
            matched=r.matched or 0, missed=r.missed or 0, error=r.error,
            started_at=r.started_at, finished_at=r.finished_at,
        )
        for r in rows
    ]


@router.post("/retag")
def retag(
    body: schemas.ExpenseAnalyserRetagIn | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    body = body or schemas.ExpenseAnalyserRetagIn()
    ids = [str(i).strip() for i in (body.item_ids or []) if str(i).strip()]
    started = ea.start_retag_background(
        vault_id(current_user),
        limit=body.limit or ea._RETAG_AI_LIMIT,
        use_ai=True,
        item_ids=ids or None,
        force=bool(body.force),
    )
    if not started:
        raise HTTPException(409, "Sync or re-tag already running")
    return {
        "ok": True,
        "started": True,
        "limit": len(ids) if ids else (body.limit or ea._RETAG_AI_LIMIT),
        "item_ids": ids or None,
    }


@router.post("/items/{item_id}/retag")
def retag_item(
    item_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    started = ea.start_retag_background(
        vault_id(current_user), use_ai=True, item_ids=[item_id],
    )
    if not started:
        raise HTTPException(409, "Sync or re-tag already running")
    return {"ok": True, "started": True, "item_ids": [item_id]}


@router.post("/clear")
def clear_inbox(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Delete every analyser inbox row for this vault (ledger untouched)."""
    require_owner(current_user)
    return ea.clear_inbox(db, current_user)


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


@router.put("/schedule", response_model=schemas.ExpenseAnalyserStatusOut)
def save_schedule(
    body: schemas.ExpenseAnalyserScheduleIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    ea.save_schedule(db, current_user, enabled=body.enabled, hour=body.hour)
    return schemas.ExpenseAnalyserStatusOut(**ea.status_dict(db, current_user))


@router.get("/insights")
def insights(
    month: str | None = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    return ea.insights(db, current_user, month)


@router.post("/disconnect", response_model=schemas.ExpenseAnalyserStatusOut)
def disconnect(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    ea.disconnect(db, current_user)
    return schemas.ExpenseAnalyserStatusOut(**ea.status_dict(db, current_user))


def _pdf_out(row: models.ShopStatementPdf) -> schemas.ShopStatementPdfOut:
    return schemas.ShopStatementPdfOut(
        id=row.id, filename=row.filename, subject=row.subject, from_addr=row.from_addr,
        received_at=row.received_at, status=row.status, error=row.error,
        bank_hint=row.bank_hint, created_count=row.created_count or 0,
        skipped_count=row.skipped_count or 0, created_at=row.created_at,
    )


@router.post("/import-pdfs", response_model=schemas.ExpenseAnalyserPdfImportOut)
def import_pdfs(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = ea.get_or_create(db, current_user)
    if not row.refresh_token_enc:
        raise HTTPException(400, "Connect Gmail first")
    started = ea.start_pdf_import_background(vault_id(current_user))
    if not started:
        raise HTTPException(409, "Sync or import already running")
    return schemas.ExpenseAnalyserPdfImportOut(ok=True, started=True)


@router.get("/mail-pdfs", response_model=list[schemas.ShopStatementPdfOut])
def list_mail_pdfs(
    status: str | None = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    rows = ea.list_mail_pdfs(db, current_user, status=status or None, limit=limit)
    return [_pdf_out(r) for r in rows]


@router.post("/mail-pdfs/{pdf_id}/ignore", response_model=schemas.ShopStatementPdfOut)
def ignore_mail_pdf(
    pdf_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    try:
        row = ea.ignore_mail_pdf(db, current_user, pdf_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    return _pdf_out(row)


def _mail_pdf_file_response(pdf_id: str, db: Session, user: models.User, *, inline: bool):
    from fastapi.responses import Response
    try:
        data, filename = ea.fetch_mail_pdf_bytes(db, user, pdf_id)
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(400, str(exc)) from exc
    safe = filename.replace('"', "")
    disposition = "inline" if inline else "attachment"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'{disposition}; filename="{safe}"',
            "Cache-Control": "private, no-store",
        },
    )


@router.get("/mail-pdfs/{pdf_id}/view")
def view_mail_pdf(
    pdf_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    return _mail_pdf_file_response(pdf_id, db, current_user, inline=True)


@router.get("/mail-pdfs/{pdf_id}/download")
def download_mail_pdf(
    pdf_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    return _mail_pdf_file_response(pdf_id, db, current_user, inline=False)
