"""Expense Analyser — Gmail spend inbox, separate from Money Manager.

Reads bank/UPI/card alert mail, classifies with the same heuristics as SMS AI,
reconciles against the ledger, and posts only when the user accepts.
"""
from __future__ import annotations

import logging
import re
import threading
import time
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
_TEXT_LIMIT = 6000
_SYNC_BUSY: dict[str, float] = {}
_SYNC_LOCK = threading.Lock()
_SYNC_STALE_SEC = 15 * 60
_RETAG_BUSY: dict[str, float] = {}
_RETAG_LOCK = threading.Lock()
_RETAG_STALE_SEC = 15 * 60
_RETAG_AI_LIMIT = 20
_RETAG_AI_PAUSE_SEC = 0.5

_BILL_LINE_RE = re.compile(
    r"(?P<date>\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{1,2}\s+[A-Za-z]{3}\s+\d{2,4})"
    r".{0,40}?"
    r"(?:rs\.?|inr|₹)\s*(?P<amount>[0-9]{1,3}(?:,[0-9]{2,3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)"
    r".{0,60}?"
    r"(?P<payee>[A-Za-z0-9 &._-]{3,40})?",
    re.I,
)


def _is_syncing(uid: str) -> bool:
    started = _SYNC_BUSY.get(uid)
    if not started:
        return False
    if time.time() - started > _SYNC_STALE_SEC:
        _SYNC_BUSY.pop(uid, None)
        return False
    return True


def _mark_syncing(uid: str, busy: bool) -> None:
    with _SYNC_LOCK:
        if busy:
            _SYNC_BUSY[uid] = time.time()
        else:
            _SYNC_BUSY.pop(uid, None)


def _is_retagging(uid: str) -> bool:
    started = _RETAG_BUSY.get(uid)
    if not started:
        return False
    if time.time() - started > _RETAG_STALE_SEC:
        _RETAG_BUSY.pop(uid, None)
        return False
    return True


def _mark_retagging(uid: str, busy: bool) -> None:
    with _RETAG_LOCK:
        if busy:
            _RETAG_BUSY[uid] = time.time()
        else:
            _RETAG_BUSY.pop(uid, None)


def _is_heavy_job(uid: str) -> bool:
    return _is_syncing(uid) or _is_retagging(uid)


def start_sync_background(user_id: str, *, trigger: str = "manual") -> bool:
    """Run Gmail sync on a worker thread so the Pi web process stays up."""
    if _is_heavy_job(user_id):
        return False
    _mark_syncing(user_id, True)

    def _run() -> None:
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            user = db.query(models.User).filter(models.User.id == user_id).first()
            if user:
                sync_gmail(db, user, trigger=trigger, use_ai=False)
        except Exception:
            log.exception("background expense analyser sync failed")
        finally:
            _mark_syncing(user_id, False)
            db.close()

    threading.Thread(target=_run, name=f"ea-sync-{user_id[:8]}", daemon=True).start()
    return True


def start_retag_background(
    user_id: str,
    *,
    limit: int = _RETAG_AI_LIMIT,
    use_ai: bool = True,
    item_ids: list[str] | None = None,
    force: bool = False,
) -> bool:
    """Re-tag open inbox rows on a worker thread (small AI batch for Pi safety)."""
    if _is_heavy_job(user_id):
        return False
    _mark_retagging(user_id, True)
    ids = [str(i).strip() for i in (item_ids or []) if str(i).strip()]
    if ids:
        ids = ids[:_RETAG_AI_LIMIT]
        batch = len(ids)
    else:
        batch = max(1, min(_RETAG_AI_LIMIT, int(limit or _RETAG_AI_LIMIT)))

    def _run() -> None:
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            user = db.query(models.User).filter(models.User.id == user_id).first()
            if user:
                retag_pending_items(
                    db, user, limit=batch, use_ai=use_ai, item_ids=ids or None, force=force,
                )
        except Exception:
            log.exception("background expense analyser retag failed")
        finally:
            _mark_retagging(user_id, False)
            db.close()

    threading.Thread(target=_run, name=f"ea-retag-{user_id[:8]}", daemon=True).start()
    return True


def _known_gmail_ids(db: Session, uid: str) -> set[str]:
    rows = (
        db.query(models.ExpenseAnalyserItem.gmail_message_id)
        .filter(models.ExpenseAnalyserItem.user_id == uid)
        .distinct()
        .all()
    )
    return {r[0] for r in rows if r[0]}


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
    counts = {"pending": 0, "matched": 0, "missed": 0, "posted": 0, "corrected": 0}
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
        "enabled": bool(row.enabled) if row else False,
        "hour": int(row.hour if row and row.hour is not None else 6),
        "last_sync_at": row.last_sync_at.isoformat() if row and row.last_sync_at else None,
        "last_ok": row.last_ok if row else None,
        "last_error": row.last_error if row else None,
        "syncing": _is_syncing(uid),
        "retagging": _is_retagging(uid),
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


def _received_day(mail: dict[str, Any] | None) -> str | None:
    received = (mail or {}).get("received_at")
    if received is None:
        return None
    if hasattr(received, "strftime"):
        return received.strftime("%Y-%m-%d")
    text = str(received)
    return text[:10] if len(text) >= 10 else None


def _best_txn_date(parsed: dict[str, Any], mail: dict[str, Any] | None, *, kind: str) -> str | None:
    raw = parsed.get("txn_date") or parsed.get("date")
    recv = _received_day(mail)
    if kind == "bill_line" and raw:
        return raw
    if raw and recv:
        try:
            parsed_d = datetime.strptime(str(raw)[:10], "%Y-%m-%d")
            recv_d = datetime.strptime(recv, "%Y-%m-%d")
            if abs((parsed_d - recv_d).days) > 5:
                return recv
        except ValueError:
            return recv
    return raw or recv


def _effective_sync_query(row: models.ExpenseAnalyserConnection) -> str:
    q = (row.sync_query or "").strip()
    if not q:
        return gmail.DEFAULT_SYNC_QUERY
    # Older shipped defaults omitted hdfcbank.com / instalerts — upgrade in place.
    if "hdfcbank.net OR alerts.hdfcbank.net" in q and "hdfcbank.com" not in q:
        return gmail.DEFAULT_SYNC_QUERY
    return q


def _looks_like_bank_alert(mail: dict[str, Any]) -> bool:
    blob = f"{mail.get('from_addr') or ''} {mail.get('subject') or ''}".lower()
    banks = ("hdfc", "icici", "sbi", "axis", "kotak", "yesbank", "indusind", "rbl", "idfc", "amex")
    keys = ("txn", "transaction", "debited", "credited", "spent", "upi", "credit card")
    return any(b in blob for b in banks) and any(k in blob for k in keys)


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


def _classify_alert(text: str, ai: dict[str, Any] | None = None) -> dict[str, Any]:
    return finance_ai.classify_message(text or "", ai=ai)


def _find_ledger_match(
    db: Session,
    uid: str,
    *,
    amount: float | None,
    txn_date: str | None,
    payee: str | None,
) -> models.FinanceTransaction | None:
    if amount is None or not txn_date:
        return None
    amt = Decimal(str(amount))
    q = db.query(models.FinanceTransaction).filter(
        models.FinanceTransaction.user_id == uid,
        models.FinanceTransaction.amount == amt,
        models.FinanceTransaction.txn_type.in_(("expense", "income", "transfer")),
    )
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

    amount = parsed.get("amount")
    txn_date = _best_txn_date(parsed, mail, kind=kind)
    payee = parsed.get("payee")
    existing = (
        db.query(models.ExpenseAnalyserItem)
        .filter(
            models.ExpenseAnalyserItem.user_id == uid,
            models.ExpenseAnalyserItem.gmail_message_id == gmail_id,
            models.ExpenseAnalyserItem.kind == kind,
            models.ExpenseAnalyserItem.amount == _dec(amount),
            models.ExpenseAnalyserItem.txn_date == txn_date,
            models.ExpenseAnalyserItem.payee == payee,
        )
        .first()
    )
    if existing:
        return None
    # One alert row per Gmail message (ignore amount/date churn from re-parse)
    if kind == "alert":
        prior = (
            db.query(models.ExpenseAnalyserItem)
            .filter(
                models.ExpenseAnalyserItem.user_id == uid,
                models.ExpenseAnalyserItem.gmail_message_id == gmail_id,
                models.ExpenseAnalyserItem.kind == "alert",
            )
            .first()
        )
        if prior:
            return None
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


def sync_gmail(
    db: Session,
    user: models.User,
    *,
    max_messages: int = 80,
    trigger: str = "manual",
    use_ai: bool = False,
) -> dict[str, Any]:
    row = get_or_create(db, user)
    uid = vault_id(user)
    started = datetime.utcnow()
    out = {"fetched": 0, "created": 0, "skipped": 0, "matched": 0, "missed": 0, "error": None}
    try:
        token = _access_token(db, row)
        query = _effective_sync_query(row)
        if row.sync_query != query:
            row.sync_query = query
        ids = gmail.list_message_ids_paged(token, query, limit=max_messages)
        out["fetched"] = len(ids)
        known = _known_gmail_ids(db, uid)
        ai_bundle = None
        if use_ai:
            from app.ai_providers import get_default_bundle
            from app.ai_usage import attach_log_context
            ai_bundle = attach_log_context(get_default_bundle(db, user), db, user, "expense_analyser")
        processed = 0
        for mid in ids:
            if mid in known:
                out["skipped"] += 1
                continue
            try:
                raw = gmail.get_message(token, mid)
                mail = gmail.extract_message(raw)
                raw = None
                body = mail.get("text") or ""
                if len(body) < 80 or finance_ai._parse_amount(body) is None:
                    mail = gmail.hydrate_message_text(token, mail)
                mail["text"] = (mail.get("text") or "")[:_TEXT_LIMIT]
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
                parsed = _classify_alert(text, ai=ai_bundle)
                if parsed.get("amount") is None and not (parsed.get("direction") in ("debit", "credit")):
                    if _looks_like_bank_alert(mail):
                        subj = (mail.get("subject") or "").lower()
                        direction = "credit" if ("credited" in subj or "received" in subj) else "debit"
                        parsed = {
                            **parsed,
                            "direction": direction,
                            "snippet": mail.get("snippet") or mail.get("subject"),
                            "confidence": min(float(parsed.get("confidence") or 0.3), 0.35),
                        }
                    else:
                        out["skipped"] += 1
                        known.add(mid)
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
            known.add(mid)
            if created_here == 0 and is_bill:
                out["skipped"] += 1
            processed += 1
            if processed % 12 == 0:
                db.commit()

        row.last_sync_at = datetime.utcnow()
        row.last_ok = True
        row.last_error = None
        _record_sync_log(db, uid, trigger=trigger, started=started, out=out, ok=True)
        db.commit()
        try:
            fix = retag_pending_items(db, user, limit=30, use_ai=False)
            out["retagged"] = fix.get("updated", 0)
        except Exception:  # noqa: BLE001
            log.exception("expense analyser retag after sync failed")
            out["retagged"] = 0
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        row = get_or_create(db, user)
        row.last_sync_at = datetime.utcnow()
        row.last_ok = False
        row.last_error = str(exc)[:500]
        out["error"] = str(exc)
        _record_sync_log(db, vault_id(user), trigger=trigger, started=started, out=out, ok=False)
        db.commit()
        log.exception("expense analyser sync failed")
    return out


def _record_sync_log(
    db: Session,
    uid: str,
    *,
    trigger: str,
    started: datetime,
    out: dict[str, Any],
    ok: bool,
) -> None:
    db.add(models.ExpenseAnalyserSyncLog(
        user_id=uid,
        trigger=(trigger if trigger in ("manual", "scheduled") else "manual"),
        ok=ok,
        fetched=int(out.get("fetched") or 0),
        created=int(out.get("created") or 0),
        skipped=int(out.get("skipped") or 0),
        matched=int(out.get("matched") or 0),
        missed=int(out.get("missed") or 0),
        error=(out.get("error") or None),
        started_at=started,
        finished_at=datetime.utcnow(),
    ))


def count_sync_logs(db: Session, user: models.User) -> int:
    return (
        db.query(models.ExpenseAnalyserSyncLog)
        .filter(models.ExpenseAnalyserSyncLog.user_id == vault_id(user))
        .count()
    )


def list_sync_logs(
    db: Session,
    user: models.User,
    *,
    limit: int = 30,
    offset: int = 0,
) -> list[models.ExpenseAnalyserSyncLog]:
    return (
        db.query(models.ExpenseAnalyserSyncLog)
        .filter(models.ExpenseAnalyserSyncLog.user_id == vault_id(user))
        .order_by(models.ExpenseAnalyserSyncLog.finished_at.desc())
        .offset(max(0, offset))
        .limit(max(1, min(100, limit)))
        .all()
    )


def retag_pending_items(
    db: Session,
    user: models.User,
    *,
    limit: int = _RETAG_AI_LIMIT,
    use_ai: bool = True,
    item_ids: list[str] | None = None,
    force: bool = False,
) -> dict[str, int]:
    """Re-run classify + hard_correct on open inbox rows (fixes bad ATM/credit tags).

    Already-tagged (`corrected`) rows are skipped unless `force` is set or the
    caller passed explicit `item_ids` (selected / per-item re-tag).
    """
    from app.ai_providers import get_default_bundle
    from app.ai_usage import attach_log_context

    uid = vault_id(user)
    ai = attach_log_context(get_default_bundle(db, user), db, user, "expense_analyser") if use_ai else None
    ids = [str(i).strip() for i in (item_ids or []) if str(i).strip()]
    include_corrected = bool(force or ids)
    open_statuses = (
        ("pending", "missed", "matched", "corrected")
        if include_corrected
        else ("pending", "missed", "matched")
    )
    if ids:
        ids = ids[:_RETAG_AI_LIMIT]
        rows = (
            db.query(models.ExpenseAnalyserItem)
            .filter(
                models.ExpenseAnalyserItem.user_id == uid,
                models.ExpenseAnalyserItem.id.in_(ids),
                models.ExpenseAnalyserItem.status.in_(open_statuses),
                models.ExpenseAnalyserItem.kind.in_(("alert", "bill_line")),
            )
            .all()
        )
        # Keep the caller's selection order when possible.
        by_id = {r.id: r for r in rows}
        rows = [by_id[i] for i in ids if i in by_id]
    else:
        batch = max(1, min(_RETAG_AI_LIMIT if use_ai else 80, int(limit or _RETAG_AI_LIMIT)))
        rows = (
            db.query(models.ExpenseAnalyserItem)
            .filter(
                models.ExpenseAnalyserItem.user_id == uid,
                models.ExpenseAnalyserItem.status.in_(open_statuses),
                models.ExpenseAnalyserItem.kind.in_(("alert", "bill_line")),
            )
            .order_by(models.ExpenseAnalyserItem.created_at.desc())
            .limit(batch)
            .all()
        )
    updated = 0
    scanned = 0
    for i, item in enumerate(rows):
        text = crypto.decrypt_text(item.raw_text_enc) or item.raw_snippet or item.subject or ""
        if not text.strip():
            continue
        scanned += 1
        parsed = finance_ai.classify_message(text, ai=ai)
        before = (
            item.direction, _f(item.amount), item.payee, item.txn_date,
            item.payment_method, item.suggested_category,
        )
        item.direction = parsed.get("direction") or item.direction
        if parsed.get("amount") is not None:
            item.amount = _dec(parsed.get("amount"))
        if parsed.get("payee"):
            item.payee = finance_ai.normalize_payee(parsed.get("payee")) or parsed.get("payee")
        elif item.payee:
            item.payee = finance_ai.normalize_payee(item.payee) or item.payee
        if parsed.get("date") or parsed.get("txn_date"):
            mail_proxy = {"received_at": item.received_at}
            item.txn_date = _best_txn_date(
                {"date": parsed.get("date"), "txn_date": parsed.get("txn_date")},
                mail_proxy,
                kind=item.kind or "alert",
            ) or item.txn_date
        elif not item.txn_date and item.received_at:
            item.txn_date = item.received_at.strftime("%Y-%m-%d")
        if parsed.get("payment_method"):
            item.payment_method = parsed.get("payment_method")
        if parsed.get("category") or parsed.get("suggested_category"):
            item.suggested_category = parsed.get("category") or parsed.get("suggested_category")
        if parsed.get("confidence") is not None:
            item.confidence = _dec(parsed.get("confidence"))
        after = (
            item.direction, _f(item.amount), item.payee, item.txn_date,
            item.payment_method, item.suggested_category,
        )
        if before != after:
            if item.status in ("pending", "missed", "matched"):
                item.status = "corrected"
            updated += 1
        # Keep memory pressure low and let the Pi breathe between AI calls.
        if use_ai and i + 1 < len(rows):
            time.sleep(_RETAG_AI_PAUSE_SEC)
        if (i + 1) % 5 == 0:
            db.commit()
    db.commit()
    return {"scanned": scanned, "updated": updated}

def list_items(
    db: Session,
    user: models.User,
    *,
    status: str | None = None,
    statuses: list[str] | tuple[str, ...] | None = None,
    kind: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[models.ExpenseAnalyserItem]:
    from sqlalchemy import func

    uid = vault_id(user)
    q = db.query(models.ExpenseAnalyserItem).filter(models.ExpenseAnalyserItem.user_id == uid)
    if status:
        q = q.filter(models.ExpenseAnalyserItem.status == status)
    elif statuses:
        q = q.filter(models.ExpenseAnalyserItem.status.in_(list(statuses)))
    if kind:
        q = q.filter(models.ExpenseAnalyserItem.kind == kind)
    return (
        q.order_by(
            func.coalesce(
                models.ExpenseAnalyserItem.received_at,
                models.ExpenseAnalyserItem.created_at,
            ).desc(),
            models.ExpenseAnalyserItem.created_at.desc(),
        )
        .offset(max(0, offset))
        .limit(max(1, min(300, limit)))
        .all()
    )


def count_items(
    db: Session,
    user: models.User,
    *,
    status: str | None = None,
    statuses: list[str] | tuple[str, ...] | None = None,
    kind: str | None = None,
) -> int:
    uid = vault_id(user)
    q = db.query(models.ExpenseAnalyserItem).filter(models.ExpenseAnalyserItem.user_id == uid)
    if status:
        q = q.filter(models.ExpenseAnalyserItem.status == status)
    elif statuses:
        q = q.filter(models.ExpenseAnalyserItem.status.in_(list(statuses)))
    if kind:
        q = q.filter(models.ExpenseAnalyserItem.kind == kind)
    return int(q.count() or 0)


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


def clear_inbox(db: Session, user: models.User) -> dict[str, int]:
    """Delete every Expense Analyser inbox row for this vault (not Money Manager)."""
    uid = vault_id(user)
    deleted = (
        db.query(models.ExpenseAnalyserItem)
        .filter(models.ExpenseAnalyserItem.user_id == uid)
        .delete(synchronize_session=False)
    )
    db.commit()
    return {"deleted": int(deleted or 0)}


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


def _get_or_create_category(
    db: Session,
    user: models.User,
    *,
    name: str,
    kind: str,
    parent_id: str | None = None,
    account_id: str | None = None,
) -> models.FinanceCategory:
    from app.routers.finance import CAT_COLORS, _find_category

    uid = vault_id(user)
    want = (name or "").strip()
    if not want:
        raise RuntimeError("Category name required")
    cats = (
        db.query(models.FinanceCategory)
        .filter(models.FinanceCategory.user_id == uid)
        .all()
    )
    if parent_id:
        parent = next((c for c in cats if c.id == parent_id), None)
        if parent and parent.parent_id:
            raise RuntimeError("Only one subcategory level is allowed")
        for c in cats:
            if c.parent_id == parent_id and c.name.lower() == want.lower():
                return c
    else:
        for c in cats:
            if (
                not c.parent_id
                and c.name.lower() == want.lower()
                and (c.kind == kind or not kind)
            ):
                if account_id and c.account_id and c.account_id != account_id:
                    continue
                return c
        found = _find_category(cats, want, kind, account_id)
        if found and not found.parent_id:
            return found
    row = models.FinanceCategory(
        user_id=uid,
        name=want[:120],
        kind=kind if kind in ("expense", "income") else "expense",
        color=CAT_COLORS[0],
        account_id=account_id,
        parent_id=parent_id,
    )
    db.add(row)
    db.flush()
    return row


def resolve_post_category(
    db: Session,
    user: models.User,
    item: models.ExpenseAnalyserItem,
    *,
    category_id: str | None = None,
    subcategory_id: str | None = None,
    new_category: str | None = None,
    new_subcategory: str | None = None,
    account_id: str | None = None,
) -> models.FinanceCategory | None:
    uid = vault_id(user)
    kind = "income" if item.direction == "credit" else "expense"
    cats = (
        db.query(models.FinanceCategory)
        .filter(models.FinanceCategory.user_id == uid)
        .all()
    )
    parent = None
    if (new_category or "").strip():
        parent = _get_or_create_category(
            db, user, name=new_category, kind=kind, account_id=account_id,
        )
    elif category_id:
        parent = next((c for c in cats if c.id == category_id), None)

    leaf = None
    if (new_subcategory or "").strip():
        if not parent:
            raise RuntimeError("Pick or add a category before adding a subcategory")
        leaf = _get_or_create_category(
            db, user, name=new_subcategory, kind=parent.kind,
            parent_id=parent.id, account_id=account_id or parent.account_id,
        )
    elif subcategory_id:
        leaf = next((c for c in cats if c.id == subcategory_id), None)
    return leaf or parent


def match_category_ids(
    cats: list[models.FinanceCategory],
    suggested: str | None,
    kind: str,
) -> tuple[str, str]:
    """Return (parent_id, subcategory_id) for a suggested category name."""
    want = (suggested or "").strip()
    if not want:
        return "", ""
    parent_name, sub_name = want, ""
    if " / " in want:
        parent_name, sub_name = want.split(" / ", 1)

    def _kind_ok(c: models.FinanceCategory) -> bool:
        return (not kind) or c.kind == kind

    if sub_name:
        for c in cats:
            if not _kind_ok(c) or not c.parent_id:
                continue
            if c.name.lower() != sub_name.strip().lower():
                continue
            parent = next((p for p in cats if p.id == c.parent_id), None)
            if parent and parent.name.lower() == parent_name.lower():
                return parent.id, c.id
        for c in cats:
            if _kind_ok(c) and not c.parent_id and c.name.lower() == parent_name.lower():
                kid = next(
                    (
                        k for k in cats
                        if k.parent_id == c.id and k.name.lower() == sub_name.strip().lower()
                    ),
                    None,
                )
                return c.id, kid.id if kid else ""
    for c in cats:
        if not _kind_ok(c):
            continue
        if c.name.lower() == want.lower():
            if c.parent_id:
                return c.parent_id, c.id
            return c.id, ""
    for c in cats:
        if _kind_ok(c) and not c.parent_id and c.name.lower() == parent_name.lower():
            return c.id, ""
    return "", ""


def post_to_finance(
    db: Session,
    user: models.User,
    item_id: str,
    *,
    account_id: str | None = None,
    category_id: str | None = None,
    subcategory_id: str | None = None,
    new_category: str | None = None,
    new_subcategory: str | None = None,
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
    cat = resolve_post_category(
        db, user, item,
        category_id=category_id,
        subcategory_id=subcategory_id,
        new_category=new_category,
        new_subcategory=new_subcategory,
        account_id=acc.id,
    )
    if not cat and item.suggested_category:
        cat = fn._find_category(cats, item.suggested_category.split(" / ")[0], kind, acc.id)
        if " / " in (item.suggested_category or ""):
            parent, sub = match_category_ids(cats, item.suggested_category, kind)
            cat = next((c for c in cats if c.id == (sub or parent)), cat)
    if cat:
        if cat.parent_id:
            parent_row = next((c for c in cats if c.id == cat.parent_id), None)
            if parent_row is None:
                parent_row = db.query(models.FinanceCategory).filter_by(id=cat.parent_id).first()
            item.suggested_category = (
                f"{parent_row.name} / {cat.name}" if parent_row else cat.name
            )
        else:
            item.suggested_category = cat.name
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
    row.enabled = False
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


def save_schedule(
    db: Session,
    user: models.User,
    *,
    enabled: bool,
    hour: int,
) -> models.ExpenseAnalyserConnection:
    row = get_or_create(db, user)
    row.hour = max(0, min(23, int(hour)))
    row.enabled = bool(enabled) and bool(row.refresh_token_enc)
    db.commit()
    db.refresh(row)
    return row


def should_run_now(row: models.ExpenseAnalyserConnection, now: datetime | None = None) -> bool:
    if not row.enabled or not row.refresh_token_enc:
        return False
    now = now or datetime.now()
    if now.hour < int(row.hour or 6):
        return False
    if row.last_sync_at and row.last_ok and row.last_sync_at.date() == now.date():
        return False
    return True


def run_due_syncs() -> None:
    """Daily Gmail sync for vaults with auto-sync enabled (called from scheduler)."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        rows = (
            db.query(models.ExpenseAnalyserConnection)
            .filter(
                models.ExpenseAnalyserConnection.enabled.is_(True),
                models.ExpenseAnalyserConnection.refresh_token_enc.isnot(None),
            )
            .all()
        )
        now = datetime.now()
        for row in rows:
            if not should_run_now(row, now):
                continue
            user = db.query(models.User).filter(models.User.id == row.user_id).first()
            if not user:
                continue
            try:
                result = sync_gmail(db, user, trigger="scheduled")
                log.info(
                    "Expense Analyser sync for %s: created=%s error=%s",
                    user.email, result.get("created"), result.get("error"),
                )
            except Exception:
                log.exception("Expense Analyser sync failed for %s", user.email)
    finally:
        db.close()


_CHART_COLORS = [
    "#5EEAD4", "#F87171", "#FBBF24", "#60A5FA", "#A78BFA",
    "#34D399", "#FB7185", "#F0C36A", "#38BDF8", "#C0A8FF",
    "#4ADE9B", "#F97316", "#22D3EE", "#E879F9", "#94A3B8",
]


def _month_bounds(year_month: str) -> tuple[str, str, str, str]:
    """Return ym, label, prev, next for a YYYY-MM string."""
    try:
        year, month = [int(x) for x in year_month.split("-", 1)]
        base = datetime(year, month, 1)
    except (ValueError, TypeError):
        now = datetime.utcnow()
        base = datetime(now.year, now.month, 1)
        year_month = base.strftime("%Y-%m")
    if base.month == 1:
        prev = datetime(base.year - 1, 12, 1)
    else:
        prev = datetime(base.year, base.month - 1, 1)
    if base.month == 12:
        nxt = datetime(base.year + 1, 1, 1)
    else:
        nxt = datetime(base.year, base.month + 1, 1)
    label = base.strftime("%B %Y")
    return year_month, label, prev.strftime("%Y-%m"), nxt.strftime("%Y-%m")


def _item_day(item: models.ExpenseAnalyserItem) -> str | None:
    if item.txn_date and len(item.txn_date) >= 10:
        return item.txn_date[:10]
    if item.received_at:
        return item.received_at.strftime("%Y-%m-%d")
    return None


def insights(db: Session, user: models.User, year_month: str | None = None) -> dict[str, Any]:
    """Chart-ready spend summary from analyser inbox (not Money Manager ledger)."""
    ym = year_month or datetime.utcnow().strftime("%Y-%m")
    ym, label, prev, nxt = _month_bounds(ym)
    uid = vault_id(user)
    rows = (
        db.query(models.ExpenseAnalyserItem)
        .filter(
            models.ExpenseAnalyserItem.user_id == uid,
            models.ExpenseAnalyserItem.kind != "bill",
            models.ExpenseAnalyserItem.status != "ignored",
            models.ExpenseAnalyserItem.amount.isnot(None),
        )
        .all()
    )
    month_rows: list[models.ExpenseAnalyserItem] = []
    for item in rows:
        day = _item_day(item)
        if day and day.startswith(ym):
            month_rows.append(item)

    debit_total = 0.0
    credit_total = 0.0
    by_cat: dict[str, float] = {}
    by_method: dict[str, float] = {}
    by_day: dict[str, float] = {}
    by_payee: dict[str, float] = {}
    cat_count: dict[str, int] = {}
    method_count: dict[str, int] = {}
    payee_count: dict[str, int] = {}
    status_count: dict[str, int] = {}

    for item in month_rows:
        amt = float(item.amount or 0)
        status_count[item.status] = status_count.get(item.status, 0) + 1
        if item.direction == "credit":
            credit_total += amt
            continue
        debit_total += amt
        cat = (item.suggested_category or "Other").strip() or "Other"
        method = (item.payment_method or "other").strip() or "other"
        payee = finance_ai.normalize_payee(item.payee) or finance_ai.format_payee(item.payee) or "Unknown"
        day = _item_day(item) or ym + "-01"
        by_cat[cat] = by_cat.get(cat, 0) + amt
        cat_count[cat] = cat_count.get(cat, 0) + 1
        by_method[method] = by_method.get(method, 0) + amt
        method_count[method] = method_count.get(method, 0) + 1
        by_day[day] = by_day.get(day, 0) + amt
        by_payee[payee] = by_payee.get(payee, 0) + amt
        payee_count[payee] = payee_count.get(payee, 0) + 1

    def _slices(mapping: dict[str, float], counts: dict[str, int] | None = None) -> list[dict]:
        total = sum(mapping.values()) or 1.0
        ordered = sorted(mapping.items(), key=lambda x: x[1], reverse=True)
        out = []
        for i, (name, amount) in enumerate(ordered):
            out.append({
                "name": name,
                "amount": round(amount, 2),
                "count": (counts or {}).get(name, 0),
                "pct": round(100.0 * amount / total, 1),
                "color": _CHART_COLORS[i % len(_CHART_COLORS)],
            })
        return out

    days_sorted = sorted(by_day.items())
    day_max = max((v for _, v in days_sorted), default=0) or 1.0
    day_bars = [
        {
            "date": d,
            "label": d[8:10],
            "amount": round(v, 2),
            "pct": round(100.0 * v / day_max, 1),
        }
        for d, v in days_sorted
    ]

    return {
        "year_month": ym,
        "label": label,
        "prev": prev,
        "next": nxt,
        "debit_total": round(debit_total, 2),
        "credit_total": round(credit_total, 2),
        "item_count": len(month_rows),
        "by_category": _slices(by_cat, cat_count),
        "by_method": _slices(by_method, method_count),
        "by_day": day_bars,
        "by_status": [
            {"name": k, "count": v, "color": _CHART_COLORS[i % len(_CHART_COLORS)]}
            for i, (k, v) in enumerate(sorted(status_count.items(), key=lambda x: -x[1]))
        ],
        "top_payees": _slices(by_payee, payee_count)[:10],
    }