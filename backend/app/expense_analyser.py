"""Expense Analyser — Gmail spend inbox, separate from Money Manager.

Reads bank/UPI/card alert mail, classifies with the same heuristics as SMS AI,
reconciles against the ledger, and posts only when the user accepts.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from app import crypto, finance_ai, gmail, models
from app.deps import vault_id
from app.drive_backup import oauth_creds, oauth_ready

log = logging.getLogger("vault.expense_analyser")

STATUSES = ("pending", "matched", "corrected", "posted", "ignored", "missed")
KINDS = ("alert", "bill", "bill_line")

_BILL_LINE_RE = re.compile(
    r"(?P<date>\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4})"
    r".{0,40}?"
    r"(?:rs\.?|inr|₹)\s*(?P<amount>[0-9]{1,3}(?:,[0-9]{2,3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)"
    r".{0,60}?"
    r"(?P<payee>[A-Za-z0-9 &._-]{3,40})?",
    re.I,
)


def _row(db: Session, user: models.User) -> models.ExpenseAnalyserConnection | None:
    return (
        db.query(models.ExpenseAnalyserConnection)
        .filter(models.ExpenseAnalyserConnection.user_id == vault_id(user))
        .first()
    )


def get_or_create(db: Session, user: models.User) -> models.ExpenseAnalyserConnection:
    row = _row(db, user)
    if row:
        return row
    row = models.ExpenseAnalyserConnection(
        user_id=vault_id(user),
        sync_query=gmail.DEFAULT_SYNC_QUERY,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def status_dict(db: Session, user: models.User) -> dict[str, Any]:
    from sqlalchemy import func

    row = _row(db, user)
    uid = vault_id(user)
    counts = {"pending": 0, "matched": 0, "missed": 0, "posted": 0}
    rows = (
        db.query(models.ExpenseAnalyserItem.status, func.count(models.ExpenseAnalyserItem.id))
        .filter(models.ExpenseAnalyserItem.user_id == uid)
        .group_by(models.ExpenseAnalyserItem.status)
        .all()
    )
    for status, n in rows:
        if status in counts:
            counts[status] = int(n)
    return {
        "connected": bool(row and row.refresh_token_enc),
        "email": row.connected_email if row else None,
        "server_oauth": oauth_ready(db),
        "sync_query": (row.sync_query if row and row.sync_query else gmail.DEFAULT_SYNC_QUERY),
        "last_sync_at": row.last_sync_at.isoformat() if row and row.last_sync_at else None,
        "last_ok": row.last_ok if row else None,
        "last_error": row.last_error if row else None,
        **counts,
    }


def _access_token(db: Session, row: models.ExpenseAnalyserConnection) -> str:
    if not row.refresh_token_enc:
        raise RuntimeError("Gmail is not connected")
    client_id, secret = oauth_creds(db)
    if not client_id or not secret:
        raise RuntimeError("Google OAuth client is not configured")
    refresh = crypto.decrypt_text(row.refresh_token_enc) or ""
    return gmail.refresh_access_token(client_id, secret, refresh)


def _dec(value: float | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _f(value) -> float | None:
    if value is None:
        return None
    return float(value)


def _parse_bill_lines(text: str) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    for m in _BILL_LINE_RE.finditer(text or ""):
        amount_raw = (m.group("amount") or "").replace(",", "")
        try:
            amount = float(amount_raw)
        except ValueError:
            continue
        if amount <= 0 or amount > 5_000_000:
            continue
        date_raw = m.group("date")
        txn_date = finance_ai._parse_date(date_raw) or finance_ai._parse_date(m.group(0))
        payee = (m.group("payee") or "").strip(" .-_") or None
        key = (txn_date, amount, (payee or "").lower())
        if key in seen:
            continue
        seen.add(key)
        lines.append({
            "direction": "debit",
            "amount": amount,
            "payee": payee,
            "txn_date": txn_date,
            "payment_method": "credit_card",
            "suggested_category": "Other",
            "confidence": 0.45,
            "kind": "bill_line",
            "snippet": m.group(0)[:240],
        })
        if len(lines) >= 80:
            break
    return lines


def _classify_alert(text: str) -> dict[str, Any]:
    return finance_ai.classify_heuristic(text or "")


def _find_ledger_match(
    db: Session,
    uid: str,
    *,
    amount: float | None,
    txn_date: str | None,
    payee: str | None,
) -> models.FinanceTransaction | None:
    if amount is None:
        return None
    amt = Decimal(str(amount))
    q = db.query(models.FinanceTransaction).filter(
        models.FinanceTransaction.user_id == uid,
        models.FinanceTransaction.amount == amt,
        models.FinanceTransaction.txn_type.in_(("expense", "income", "transfer")),
    )
    if txn_date:
        try:
            base = datetime.strptime(txn_date, "%Y-%m-%d").date()
            dates = [
                (base + timedelta(days=d)).strftime("%Y-%m-%d")
                for d in (-2, -1, 0, 1, 2)
            ]
            q = q.filter(models.FinanceTransaction.txn_date.in_(dates))
        except ValueError:
            q = q.filter(models.FinanceTransaction.txn_date == txn_date)
    rows = q.order_by(models.FinanceTransaction.created_at.desc()).limit(20).all()
    if not rows:
        return None
    want = (payee or "").strip().lower()
    if want:
        for row in rows:
            have = (row.payee or "").strip().lower()
            if have and (want in have or have in want):
                return row
    return rows[0]


def _item_from_mail(
    db: Session,
    uid: str,
    mail: dict[str, Any],
    parsed: dict[str, Any],
    *,
    kind: str,
) -> models.ExpenseAnalyserItem | None:
    gmail_id = mail.get("id")
    if not gmail_id:
        return None
    # Deduplicate alerts by gmail id + kind + amount + date
    existing = (
        db.query(models.ExpenseAnalyserItem)
        .filter(
            models.ExpenseAnalyserItem.user_id == uid,
            models.ExpenseAnalyserItem.gmail_message_id == gmail_id,
            models.ExpenseAnalyserItem.kind == kind,
            models.ExpenseAnalyserItem.amount == _dec(parsed.get("amount")),
            models.ExpenseAnalyserItem.txn_date == parsed.get("txn_date"),
            models.ExpenseAnalyserItem.payee == parsed.get("payee"),
        )
        .first()
    )
    if existing:
        return None

    amount = parsed.get("amount")
    txn_date = parsed.get("txn_date")
    payee = parsed.get("payee")
    match = _find_ledger_match(db, uid, amount=_f(amount), txn_date=txn_date, payee=payee)
    status = "matched" if match else ("missed" if kind == "bill_line" and amount else "pending")

    item = models.ExpenseAnalyserItem(
        user_id=uid,
        gmail_message_id=gmail_id,
        gmail_thread_id=mail.get("thread_id"),
        kind=kind,
        subject=mail.get("subject"),
        from_addr=mail.get("from_addr"),
        received_at=mail.get("received_at"),
        raw_snippet=(parsed.get("snippet") or mail.get("snippet") or "")[:500],
        raw_text_enc=crypto.encrypt_text((mail.get("text") or "")[:8000] or None),
        direction=parsed.get("direction") or "unknown",
        amount=_dec(amount),
        currency="INR",
        payee=payee,
        txn_date=txn_date,
        payment_method=parsed.get("payment_method"),
        suggested_category=parsed.get("category") or parsed.get("suggested_category"),
        confidence=_dec(parsed.get("confidence")),
        status=status,
        match_txn_id=match.id if match else None,
    )
    db.add(item)
    return item


def sync_gmail(db: Session, user: models.User, *, max_messages: int = 40) -> dict[str, Any]:
    row = get_or_create(db, user)
    uid = vault_id(user)
    out = {"fetched": 0, "created": 0, "skipped": 0, "matched": 0, "missed": 0, "error": None}
    try:
        token = _access_token(db, row)
        query = (row.sync_query or "").strip() or gmail.DEFAULT_SYNC_QUERY
        ids, _next = gmail.list_message_ids(token, query, max_results=max_messages)
        out["fetched"] = len(ids)
        for mid in ids:
            try:
                raw = gmail.get_message(token, mid)
                mail = gmail.extract_message(raw)
            except Exception as exc:  # noqa: BLE001 — per-message soft fail
                log.warning("gmail message %s failed: %s", mid, exc)
                out["skipped"] += 1
                continue

            text = mail.get("text") or ""
            is_bill = gmail.looks_like_statement(mail.get("subject"), text)
            created_here = 0

            if is_bill:
                # Parent bill marker (no amount) so the inbox shows the statement.
                parent = _item_from_mail(
                    db, uid, mail,
                    {
                        "direction": "unknown", "amount": None, "payee": None,
                        "txn_date": None, "payment_method": "credit_card",
                        "suggested_category": None, "confidence": 0.3,
                        "snippet": mail.get("snippet"),
                    },
                    kind="bill",
                )
                if parent:
                    created_here += 1
                for line in _parse_bill_lines(text):
                    item = _item_from_mail(db, uid, mail, line, kind="bill_line")
                    if item:
                        created_here += 1
                        if item.status == "matched":
                            out["matched"] += 1
                        elif item.status == "missed":
                            out["missed"] += 1
            else:
                parsed = _classify_alert(text)
                if parsed.get("amount") is None and not (parsed.get("direction") in ("debit", "credit")):
                    out["skipped"] += 1
                    continue
                item = _item_from_mail(db, uid, mail, parsed, kind="alert")
                if item:
                    created_here += 1
                    if item.status == "matched":
                        out["matched"] += 1
                    elif item.status == "missed":
                        out["missed"] += 1
                else:
                    out["skipped"] += 1

            out["created"] += created_here
            if created_here == 0 and is_bill:
                out["skipped"] += 1

        row.last_sync_at = datetime.utcnow()
        row.last_ok = True
        row.last_error = None
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        row = get_or_create(db, user)
        row.last_sync_at = datetime.utcnow()
        row.last_ok = False
        row.last_error = str(exc)[:500]
        db.commit()
        out["error"] = str(exc)
        log.exception("expense analyser sync failed")
    return out


def list_items(
    db: Session,
    user: models.User,
    *,
    status: str | None = None,
    kind: str | None = None,
    limit: int = 100,
) -> list[models.ExpenseAnalyserItem]:
    uid = vault_id(user)
    q = db.query(models.ExpenseAnalyserItem).filter(models.ExpenseAnalyserItem.user_id == uid)
    if status:
        q = q.filter(models.ExpenseAnalyserItem.status == status)
    if kind:
        q = q.filter(models.ExpenseAnalyserItem.kind == kind)
    return (
        q.order_by(
            models.ExpenseAnalyserItem.created_at.desc(),
        )
        .limit(max(1, min(300, limit)))
        .all()
    )


def get_item(db: Session, user: models.User, item_id: str) -> models.ExpenseAnalyserItem:
    row = (
        db.query(models.ExpenseAnalyserItem)
        .filter(
            models.ExpenseAnalyserItem.id == item_id,
            models.ExpenseAnalyserItem.user_id == vault_id(user),
        )
        .first()
    )
    if not row:
        raise LookupError("Item not found")
    return row


def update_item(db: Session, user: models.User, item_id: str, data: dict[str, Any]) -> models.ExpenseAnalyserItem:
    row = get_item(db, user, item_id)
    if "direction" in data and data["direction"] in ("debit", "credit", "unknown"):
        row.direction = data["direction"]
    if "amount" in data and data["amount"] is not None:
        row.amount = _dec(data["amount"])
    if "payee" in data:
        row.payee = data["payee"]
    if "txn_date" in data:
        row.txn_date = data["txn_date"]
    if "payment_method" in data:
        row.payment_method = data["payment_method"]
    if "suggested_category" in data:
        row.suggested_category = data["suggested_category"]
    if "notes" in data:
        row.notes = data["notes"]
    if row.status in ("pending", "missed", "matched"):
        row.status = "corrected"
    db.commit()
    db.refresh(row)
    return row


def ignore_item(db: Session, user: models.User, item_id: str) -> models.ExpenseAnalyserItem:
    row = get_item(db, user, item_id)
    row.status = "ignored"
    db.commit()
    db.refresh(row)
    return row


def reconnect_matches(db: Session, user: models.User) -> int:
    """Re-run ledger matching for pending/missed items."""
    uid = vault_id(user)
    items = (
        db.query(models.ExpenseAnalyserItem)
        .filter(
            models.ExpenseAnalyserItem.user_id == uid,
            models.ExpenseAnalyserItem.status.in_(("pending", "missed", "matched")),
            models.ExpenseAnalyserItem.amount.isnot(None),
        )
        .all()
    )
    n = 0
    for item in items:
        match = _find_ledger_match(
            db, uid,
            amount=_f(item.amount),
            txn_date=item.txn_date,
            payee=item.payee,
        )
        if match and item.match_txn_id != match.id:
            item.match_txn_id = match.id
            item.status = "matched"
            n += 1
        elif not match and item.status == "matched":
            item.match_txn_id = None
            item.status = "missed" if item.kind == "bill_line" else "pending"
            n += 1
    db.commit()
    return n


def post_to_finance(
    db: Session,
    user: models.User,
    item_id: str,
    *,
    account_id: str | None = None,
    category_id: str | None = None,
) -> models.FinanceTransaction:
    """Create a Money Manager transaction from an analyser item (explicit bridge)."""
    from app.routers import finance as fn

    item = get_item(db, user, item_id)
    if item.status == "posted" and item.finance_txn_id:
        raise RuntimeError("Already posted to Money Manager")
    if not item.amount or float(item.amount) <= 0:
        raise RuntimeError("Item needs an amount before posting")
    if item.kind == "bill":
        raise RuntimeError("Post bill line items, not the statement header")

    fn.ensure_defaults(db, user)
    uid = vault_id(user)
    accounts = (
        db.query(models.FinanceAccount)
        .filter(models.FinanceAccount.user_id == uid)
        .all()
    )
    cats = (
        db.query(models.FinanceCategory)
        .filter(models.FinanceCategory.user_id == uid)
        .all()
    )
    override = None
    if account_id:
        override = next((a for a in accounts if a.id == account_id), None)
        if not override:
            raise RuntimeError("Account not found")

    method = fn._clean_method(item.payment_method) or "other"
    acc = fn._account_for_method(accounts, method, override)
    if not acc:
        raise RuntimeError("No suitable Money Manager account")

    kind = "income" if item.direction == "credit" else "expense"
    cat = None
    if category_id:
        cat = next((c for c in cats if c.id == category_id), None)
    if not cat and item.suggested_category:
        cat = fn._find_category(cats, item.suggested_category, kind, acc.id)
    desc = finance_ai.build_description(method, item.payee, item.suggested_category)
    notes = (item.notes or item.raw_snippet or item.subject or "")[:400]

    txn = models.FinanceTransaction(
        user_id=uid,
        account_id=acc.id,
        category_id=cat.id if cat else None,
        txn_type=kind,
        amount=item.amount,
        txn_date=item.txn_date or datetime.utcnow().strftime("%Y-%m-%d"),
        payee=item.payee,
        notes=notes,
        description=desc,
        payment_method=method if method != "other" else None,
        tags="expense-analyser",
        source="manual",
    )
    db.add(txn)
    db.flush()
    item.finance_txn_id = txn.id
    item.status = "posted"
    if not item.match_txn_id:
        item.match_txn_id = txn.id
    db.commit()
    db.refresh(txn)
    return txn


def disconnect(db: Session, user: models.User) -> None:
    row = get_or_create(db, user)
    row.refresh_token_enc = None
    row.connected_email = None
    row.last_ok = None
    row.last_error = None
    row.last_history_id = None
    db.commit()


def save_query(db: Session, user: models.User, sync_query: str | None) -> models.ExpenseAnalyserConnection:
    row = get_or_create(db, user)
    text = (sync_query or "").strip()
    row.sync_query = text or gmail.DEFAULT_SYNC_QUERY
    db.commit()
    db.refresh(row)
    return row
