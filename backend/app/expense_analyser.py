"""Expense Analyser — Gmail spend inbox, separate from Money Manager.

Reads bank/UPI/card alert mail, classifies with the same heuristics as SMS AI,
reconciles against the ledger, and posts only when the user accepts.
"""
from __future__ import annotations

import logging
import re
import threading
import time
import calendar
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Session

from app import crypto, finance_ai, gmail, models
from app.config import settings, utc_naive_to_vault, vault_now
from app.deps import vault_id
from app.drive_backup import oauth_creds, oauth_ready

log = logging.getLogger("vault.expense_analyser")

STATUSES = ("pending", "matched", "corrected", "posted", "ignored", "missed")
METHOD_FILTERS = {
    "upi": ("upi",),
    "atm": ("atm",),
    "card": ("credit_card", "debit_card"),
}
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


def start_pdf_import_background(user_id: str) -> bool:
    """Download statement PDFs from Gmail on a worker thread."""
    if _is_heavy_job(user_id):
        return False
    _mark_syncing(user_id, True)

    def _run() -> None:
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            user = db.query(models.User).filter(models.User.id == user_id).first()
            if user:
                import_gmail_pdfs(db, user)
        except Exception:
            log.exception("background expense analyser pdf import failed")
        finally:
            _mark_syncing(user_id, False)
            db.close()

    threading.Thread(target=_run, name=f"ea-pdfs-{user_id[:8]}", daemon=True).start()
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
    pending_pdfs = (
        db.query(models.ShopStatementPdf)
        .filter(
            models.ShopStatementPdf.user_id == uid,
            models.ShopStatementPdf.status == "needs_password",
        )
        .count()
    )
    return {
        "connected": bool(row and row.refresh_token_enc),
        "email": row.connected_email if row else None,
        "server_oauth": oauth_ready(db),
        "sync_query": (row.sync_query if row and row.sync_query else gmail.DEFAULT_SYNC_QUERY),
        "enabled": bool(row.enabled) if row else False,
        "hour": int(row.hour if row and row.hour is not None else 6),
        "timezone": settings.VAULT_TIMEZONE,
        "last_sync_at": row.last_sync_at.isoformat() if row and row.last_sync_at else None,
        "last_ok": row.last_ok if row else None,
        "last_error": row.last_error if row else None,
        "syncing": _is_syncing(uid),
        "retagging": _is_retagging(uid),
        "pending_pdfs": int(pending_pdfs),
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
        q = gmail.DEFAULT_SYNC_QUERY
    sib_from = (
        "southindianbank.com OR southindianbank.co.in OR sib.co.in "
        "OR sib.bank.in OR sibalerts"
    )
    if "sib.bank.in" not in q.lower() or "sibalerts" not in q.lower():
        q = re.sub(
            r"from:\(([^)]+)\)",
            lambda m: f"from:({m.group(1)} OR {sib_from})",
            q,
            count=1,
            flags=re.I,
        )
    # Keep SIB debit alerts outside the long from:(…) group — Gmail drops later ORs.
    if "from:alerts@sib.co.in" not in q.lower():
        q = re.sub(
            r"\)\s*newer_than:",
            " OR from:alerts@sib.co.in OR from:sib.co.in) newer_than:",
            q,
            count=1,
            flags=re.I,
        )
        if "from:alerts@sib.co.in" not in q.lower():
            q = f"({q}) OR from:alerts@sib.co.in OR from:sib.co.in"
    return q


def _looks_like_bank_alert(mail: dict[str, Any]) -> bool:
    blob = f"{mail.get('from_addr') or ''} {mail.get('subject') or ''}".lower()
    banks = (
        "hdfc", "icici", "sbi", "axis", "kotak", "yesbank", "indusind", "rbl", "idfc",
        "amex", "southindianbank", "south indian bank", "sib alerts",
        "sib.bank.in", "sibalerts", "sib.co.in",
    )
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
        models.FinanceTransaction.deleted_at.is_(None),
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
    max_messages: int = 200,
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
        # SIB debit alerts use alerts@sib.co.in; Gmail drops them from the long from:(…) OR list.
        sib_ids = gmail.list_message_ids_paged(
            token, "from:alerts@sib.co.in newer_than:45d in:anywhere", limit=40,
        )
        ids = list(dict.fromkeys(list(sib_ids) + list(ids)))
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
                    snippet = (mail.get("snippet") or "").strip()
                    if snippet and finance_ai._parse_amount(mail.get("text") or "") is None:
                        mail["text"] = f"{mail.get('text') or ''}\n{snippet}".strip()
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
        try:
            pdf_out = import_gmail_pdfs(db, user, token=token)
            out["pdfs"] = pdf_out.get("pdfs", 0)
            out["pdf_rows"] = pdf_out.get("created_rows", 0)
            out["pdf_locked"] = pdf_out.get("needs_password", 0)
        except Exception:  # noqa: BLE001
            log.exception("gmail pdf import after sync failed")
            out["pdfs"] = 0
            out["pdf_rows"] = 0
            out["pdf_locked"] = 0
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


_PDF_IMPORT_LIMIT = 20
_BANK_HINTS = (
    ("HDFC", ("hdfc",)),
    ("SBI", ("sbi", "state bank", "onlinesbi")),
    ("ICICI", ("icici",)),
    ("Axis", ("axisbank", "axis bank")),
    ("Kotak", ("kotak",)),
    ("Yes Bank", ("yesbank", "yes bank")),
    ("IndusInd", ("indusind",)),
    ("RBL", ("rblbank", "rbl")),
    ("IDFC", ("idfc",)),
    ("Amex", ("americanexpress", "amex")),
    ("South Indian Bank", (
        "southindianbank", "south indian bank", "sib.co.in", "sib.bank.in",
        "sib alerts", "sibalerts",
    )),
)


def bank_hint_from_text(*parts: str | None) -> str | None:
    blob = " ".join(p or "" for p in parts).lower()
    for name, keys in _BANK_HINTS:
        if any(k in blob for k in keys):
            return name
    return None


def _pdf_part_key(part: dict[str, Any]) -> str:
    aid = (part.get("attachment_id") or "").strip()
    if aid:
        return aid
    name = (part.get("filename") or "statement.pdf").strip() or "statement.pdf"
    return f"inline:{name}"[:255]


def _download_gmail_pdf_bytes(
    token: str,
    message_id: str,
    attachment_id: str,
    *,
    filename: str | None = None,
) -> tuple[bytes, str]:
    """Fetch PDF bytes from Gmail; recover a full attachment id if the stored one was truncated."""
    mid = (message_id or "").strip()
    aid = (attachment_id or "").strip()
    if not mid or not aid or aid.startswith("inline:"):
        return b"", aid

    first_exc: BaseException | None = None
    try:
        data = gmail.get_attachment_bytes(token, mid, aid)
        if data:
            return data, aid
    except Exception as exc:  # noqa: BLE001
        first_exc = exc

    try:
        msg = gmail.get_message(token, mid)
    except Exception as exc:  # noqa: BLE001
        if first_exc is not None:
            raise first_exc from exc
        raise

    want_name = (filename or "").strip().lower()
    parts = gmail.extract_pdf_parts(msg)
    ordered: list[dict[str, Any]] = []
    for part in parts:
        paid = (part.get("attachment_id") or "").strip()
        pname = (part.get("filename") or "").strip().lower()
        if paid and (paid == aid or paid.startswith(aid)):
            ordered.insert(0, part)
        elif want_name and pname == want_name:
            ordered.append(part)
        elif part.get("data") and not paid and want_name and pname == want_name:
            ordered.append(part)

    for part in ordered:
        paid = (part.get("attachment_id") or "").strip()
        raw = part.get("data")
        if raw and not paid:
            return raw, aid
        if not paid:
            continue
        try:
            data = gmail.get_attachment_bytes(token, mid, paid)
        except Exception as exc:  # noqa: BLE001
            first_exc = first_exc or exc
            continue
        if data:
            return data, paid

    if first_exc is not None:
        raise first_exc
    return b"", aid


def _mail_pdf_row(
    db: Session, uid: str, message_id: str, attachment_id: str,
) -> models.ShopStatementPdf | None:
    row = (
        db.query(models.ShopStatementPdf)
        .filter(
            models.ShopStatementPdf.user_id == uid,
            models.ShopStatementPdf.gmail_message_id == message_id,
            models.ShopStatementPdf.gmail_attachment_id == attachment_id,
        )
        .first()
    )
    if row or not attachment_id or attachment_id.startswith("inline:"):
        return row
    # Older rows may have truncated attachment ids (VARCHAR 255 / [:255]).
    for cand in (
        db.query(models.ShopStatementPdf)
        .filter(
            models.ShopStatementPdf.user_id == uid,
            models.ShopStatementPdf.gmail_message_id == message_id,
        )
        .all()
    ):
        stored = (cand.gmail_attachment_id or "").strip()
        if not stored or stored.startswith("inline:"):
            continue
        if attachment_id.startswith(stored) or stored.startswith(attachment_id):
            return cand
    return None


def _upsert_mail_pdf(
    db: Session,
    user: models.User,
    mail: dict[str, Any],
    part: dict[str, Any],
    *,
    status: str,
    error: str | None = None,
    created_count: int = 0,
    skipped_count: int = 0,
) -> models.ShopStatementPdf:
    uid = vault_id(user)
    mid = str(mail.get("id") or "")
    key = _pdf_part_key(part)
    filename = (part.get("filename") or "statement.pdf")[:255]
    hint = bank_hint_from_text(mail.get("subject"), mail.get("from_addr"), filename)
    row = _mail_pdf_row(db, uid, mid, key)
    if row is None:
        row = models.ShopStatementPdf(
            user_id=uid, gmail_message_id=mid, gmail_attachment_id=key,
        )
        db.add(row)
    else:
        row.gmail_attachment_id = key
    row.filename = filename
    row.subject = (mail.get("subject") or None)
    row.from_addr = (mail.get("from_addr") or None)
    row.received_at = mail.get("received_at")
    row.status = status
    row.error = (error or None)
    row.bank_hint = hint
    row.created_count = int(created_count)
    row.skipped_count = int(skipped_count)
    row.updated_at = datetime.utcnow()
    db.flush()
    return row


def _download_pdf_bytes(token: str, mail: dict[str, Any], part: dict[str, Any]) -> bytes:
    from app.routers.tracker import MAX_PDF

    raw = part.get("data")
    if raw:
        return raw
    aid = part.get("attachment_id")
    mid = mail.get("id")
    if not aid or not mid or str(aid).startswith("inline:"):
        return b""
    data, resolved = _download_gmail_pdf_bytes(
        token, str(mid), str(aid), filename=part.get("filename"),
    )
    if resolved and resolved != aid:
        part["attachment_id"] = resolved
    if len(data) > MAX_PDF:
        raise ValueError("PDF is larger than 10 MB")
    return data


def _ingest_mail_pdf(
    db: Session,
    user: models.User,
    token: str,
    mail: dict[str, Any],
    part: dict[str, Any],
) -> dict[str, Any]:
    from app.routers.tracker import ingest_statement_bytes, resolve_pdf_password
    from app.statement_parsers import is_pdf_encrypted

    uid = vault_id(user)
    mid = str(mail.get("id") or "")
    key = _pdf_part_key(part)
    existing = _mail_pdf_row(db, uid, mid, key)
    if existing and existing.status in ("parsed", "ignored"):
        return {"status": existing.status, "created": 0, "skipped": 1}

    filename = (part.get("filename") or "statement.pdf")
    try:
        raw = _download_pdf_bytes(token, mail, part)
    except Exception as exc:  # noqa: BLE001
        _upsert_mail_pdf(db, user, mail, part, status="failed", error=str(exc)[:500])
        return {"status": "failed", "created": 0, "skipped": 0, "error": str(exc)}
    if not raw:
        _upsert_mail_pdf(db, user, mail, part, status="failed", error="Empty PDF attachment")
        return {"status": "failed", "created": 0, "skipped": 0}

    hint = " ".join(filter(None, [
        mail.get("subject"), mail.get("from_addr"), filename,
        bank_hint_from_text(mail.get("subject"), mail.get("from_addr"), filename),
    ]))
    try:
        pwd = resolve_pdf_password(db, user, raw, hint=hint)
        if is_pdf_encrypted(raw) and not pwd:
            _upsert_mail_pdf(
                db, user, mail, part, status="needs_password",
                error="Password-protected PDF. Add this bank's password, then load again.",
            )
            return {"status": "needs_password", "created": 0, "skipped": 0}
        result = ingest_statement_bytes(
            db, user, raw, filename, password=pwd,
            source_label=f"mail · {filename}",
        )
        _upsert_mail_pdf(
            db, user, mail, part, status="parsed",
            created_count=result.get("created", 0),
            skipped_count=result.get("skipped", 0),
        )
        return {
            "status": "parsed",
            "created": result.get("created", 0),
            "skipped": result.get("skipped", 0),
        }
    except ValueError as exc:
        msg = str(exc)
        status = "needs_password" if "password" in msg.lower() else "failed"
        _upsert_mail_pdf(db, user, mail, part, status=status, error=msg[:500])
        return {"status": status, "created": 0, "skipped": 0, "error": msg}
    except Exception as exc:  # noqa: BLE001
        _upsert_mail_pdf(db, user, mail, part, status="failed", error=str(exc)[:500])
        return {"status": "failed", "created": 0, "skipped": 0, "error": str(exc)}


def import_gmail_pdfs(
    db: Session,
    user: models.User,
    *,
    token: str | None = None,
    limit: int = _PDF_IMPORT_LIMIT,
) -> dict[str, Any]:
    """Find statement PDFs in Gmail and parse them with saved bank passwords."""
    row = get_or_create(db, user)
    if not row.refresh_token_enc:
        raise RuntimeError("Connect Gmail first")
    access = token or _access_token(db, row)
    ids = gmail.list_message_ids_paged(access, gmail.DEFAULT_PDF_QUERY, limit=limit)
    out = {
        "fetched": len(ids), "pdfs": 0, "created_rows": 0, "skipped": 0,
        "needs_password": 0, "failed": 0, "parsed": 0,
    }
    for mid in ids:
        try:
            raw_msg = gmail.get_message(access, mid)
            mail = gmail.extract_message(raw_msg)
            parts = gmail.extract_pdf_parts(raw_msg)
            raw_msg = None
        except Exception as exc:  # noqa: BLE001
            log.warning("gmail pdf message %s failed: %s", mid, exc)
            out["skipped"] += 1
            continue
        if not parts:
            out["skipped"] += 1
            continue
        for part in parts:
            result = _ingest_mail_pdf(db, user, access, mail, part)
            out["pdfs"] += 1
            status = result.get("status")
            out["created_rows"] += int(result.get("created") or 0)
            if status == "parsed":
                out["parsed"] += 1
            elif status == "needs_password":
                out["needs_password"] += 1
            elif status == "failed":
                out["failed"] += 1
            else:
                out["skipped"] += int(result.get("skipped") or 1)
        db.commit()
    return out


def retry_locked_pdfs(db: Session, user: models.User) -> dict[str, Any]:
    """Re-download PDFs that needed a password after the user saved a bank password."""
    row = _row(db, user)
    if not row or not row.refresh_token_enc:
        return {"retried": 0, "parsed": 0, "created_rows": 0, "needs_password": 0}
    try:
        token = _access_token(db, row)
    except Exception:
        return {"retried": 0, "parsed": 0, "created_rows": 0, "needs_password": 0}
    uid = vault_id(user)
    locked = (
        db.query(models.ShopStatementPdf)
        .filter(
            models.ShopStatementPdf.user_id == uid,
            models.ShopStatementPdf.status.in_(("needs_password", "failed")),
        )
        .all()
    )
    out = {"retried": 0, "parsed": 0, "created_rows": 0, "needs_password": 0}
    for rec in locked:
        aid = rec.gmail_attachment_id or ""
        if not rec.gmail_message_id or aid.startswith("inline:"):
            continue
        mail = {
            "id": rec.gmail_message_id,
            "subject": rec.subject,
            "from_addr": rec.from_addr,
            "received_at": rec.received_at,
        }
        part = {"filename": rec.filename or "statement.pdf", "attachment_id": aid}
        result = _ingest_mail_pdf(db, user, token, mail, part)
        out["retried"] += 1
        out["created_rows"] += int(result.get("created") or 0)
        if result.get("status") == "parsed":
            out["parsed"] += 1
        elif result.get("status") == "needs_password":
            out["needs_password"] += 1
    db.commit()
    return out


def list_mail_pdfs(
    db: Session,
    user: models.User,
    *,
    status: str | None = None,
    limit: int = 50,
) -> list[models.ShopStatementPdf]:
    q = db.query(models.ShopStatementPdf).filter(models.ShopStatementPdf.user_id == vault_id(user))
    if status:
        q = q.filter(models.ShopStatementPdf.status == status)
    return (
        q.order_by(models.ShopStatementPdf.created_at.desc())
        .limit(max(1, min(100, limit)))
        .all()
    )


def ignore_mail_pdf(db: Session, user: models.User, pdf_id: str) -> models.ShopStatementPdf:
    row = (
        db.query(models.ShopStatementPdf)
        .filter(
            models.ShopStatementPdf.id == pdf_id,
            models.ShopStatementPdf.user_id == vault_id(user),
        )
        .first()
    )
    if not row:
        raise LookupError("PDF not found")
    row.status = "ignored"
    row.error = None
    db.commit()
    db.refresh(row)
    return row


def get_mail_pdf(db: Session, user: models.User, pdf_id: str) -> models.ShopStatementPdf:
    row = (
        db.query(models.ShopStatementPdf)
        .filter(
            models.ShopStatementPdf.id == pdf_id,
            models.ShopStatementPdf.user_id == vault_id(user),
        )
        .first()
    )
    if not row:
        raise LookupError("PDF not found")
    return row


def fetch_mail_pdf_bytes(db: Session, user: models.User, pdf_id: str) -> tuple[bytes, str]:
    """Re-download a tracked Gmail PDF attachment. Returns (bytes, filename)."""
    from app.routers.tracker import MAX_PDF

    row = get_mail_pdf(db, user, pdf_id)
    conn = _row(db, user)
    if not conn or not conn.refresh_token_enc:
        raise RuntimeError("Connect Gmail first")
    mid = (row.gmail_message_id or "").strip()
    aid = (row.gmail_attachment_id or "").strip()
    if not mid:
        raise RuntimeError("This PDF has no Gmail message id")
    if not aid or aid.startswith("inline:"):
        raise RuntimeError("This PDF was embedded in the email and cannot be re-downloaded")
    token = _access_token(db, conn)
    try:
        data, resolved = _download_gmail_pdf_bytes(
            token, mid, aid, filename=row.filename,
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Could not download from Gmail: {exc}") from exc
    if not data:
        raise RuntimeError("Empty PDF attachment")
    if len(data) > MAX_PDF:
        raise RuntimeError("PDF is larger than 10 MB")
    if resolved and resolved != aid:
        row.gmail_attachment_id = resolved
        db.commit()
    name = (row.filename or "statement.pdf").strip() or "statement.pdf"
    if not name.lower().endswith(".pdf"):
        name = f"{name}.pdf"
    return data, name


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

def _item_date_expr():
    return func.coalesce(
        func.nullif(models.ExpenseAnalyserItem.txn_date, ""),
        func.strftime("%Y-%m-%d", models.ExpenseAnalyserItem.received_at),
        func.strftime("%Y-%m-%d", models.ExpenseAnalyserItem.created_at),
    )


def _clean_day(value: str | None) -> str | None:
    raw = (value or "").strip()[:10]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        return raw
    return None


def _items_query(
    db: Session,
    user: models.User,
    *,
    status: str | None = None,
    statuses: list[str] | tuple[str, ...] | None = None,
    kind: str | None = None,
    method: str | None = None,
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    direction: str | None = None,
):
    uid = vault_id(user)
    qry = db.query(models.ExpenseAnalyserItem).filter(models.ExpenseAnalyserItem.user_id == uid)
    if status:
        qry = qry.filter(models.ExpenseAnalyserItem.status == status)
    elif statuses:
        qry = qry.filter(models.ExpenseAnalyserItem.status.in_(list(statuses)))
    if kind:
        qry = qry.filter(models.ExpenseAnalyserItem.kind == kind)
    methods = METHOD_FILTERS.get((method or "").strip().lower())
    if methods:
        qry = qry.filter(models.ExpenseAnalyserItem.payment_method.in_(methods))
    flow = (direction or "").strip().lower()
    if flow == "credit":
        qry = qry.filter(models.ExpenseAnalyserItem.direction == "credit")
    elif flow == "debit":
        qry = qry.filter(models.ExpenseAnalyserItem.direction != "credit")
    needle = (q or "").strip()
    if needle:
        like = f"%{needle}%"
        clauses = [
            models.ExpenseAnalyserItem.payee.ilike(like),
            models.ExpenseAnalyserItem.subject.ilike(like),
            models.ExpenseAnalyserItem.from_addr.ilike(like),
            models.ExpenseAnalyserItem.raw_snippet.ilike(like),
        ]
        digits = re.sub(r"[^\d.]", "", needle)
        if digits:
            clauses.append(cast(models.ExpenseAnalyserItem.amount, String).like(f"%{digits}%"))
            try:
                clauses.append(models.ExpenseAnalyserItem.amount == Decimal(digits))
            except Exception:
                pass
        qry = qry.filter(or_(*clauses))
    start = _clean_day(date_from)
    end = _clean_day(date_to)
    if start or end:
        day = _item_date_expr()
        if start:
            qry = qry.filter(day >= start)
        if end:
            qry = qry.filter(day <= end)
    return qry


def list_items(
    db: Session,
    user: models.User,
    *,
    status: str | None = None,
    statuses: list[str] | tuple[str, ...] | None = None,
    kind: str | None = None,
    method: str | None = None,
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    direction: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[models.ExpenseAnalyserItem]:
    qry = _items_query(
        db, user, status=status, statuses=statuses, kind=kind, method=method, q=q,
        date_from=date_from, date_to=date_to, direction=direction,
    )
    date_key = _item_date_expr()
    return (
        qry.order_by(date_key.desc(), models.ExpenseAnalyserItem.created_at.desc())
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
    method: str | None = None,
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    direction: str | None = None,
) -> int:
    qry = _items_query(
        db, user, status=status, statuses=statuses, kind=kind, method=method, q=q,
        date_from=date_from, date_to=date_to, direction=direction,
    )
    return int(qry.count() or 0)


def filter_totals(
    db: Session,
    user: models.User,
    **kwargs,
) -> dict[str, Any]:
    """Debit/credit sums for the current inbox filter (all matching rows, not one page)."""
    qry = _items_query(db, user, **kwargs)
    debit = 0.0
    credit = 0.0
    n = 0
    for direction, amount, kind in qry.with_entities(
        models.ExpenseAnalyserItem.direction,
        models.ExpenseAnalyserItem.amount,
        models.ExpenseAnalyserItem.kind,
    ).all():
        if kind == "bill" or amount is None:
            continue
        n += 1
        amt = abs(float(amount))
        if (direction or "") == "credit":
            credit += amt
        else:
            debit += amt
    return {
        "debit": round(debit, 2),
        "credit": round(credit, 2),
        "net": round(credit - debit, 2),
        "count": n,
    }


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
    payee: str | None = None,
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

    custom_payee = (payee or "").strip() if payee is not None else None
    if payee is not None:
        # Explicit form/API value wins (including clear → fall back to category below).
        item.payee = (
            (finance_ai.normalize_payee(custom_payee) or custom_payee[:255])
            if custom_payee
            else None
        )

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
    # Empty title → category / subcategory (never account · payment description junk).
    if not (item.payee or "").strip():
        item.payee = (item.suggested_category or (cat.name if cat else None) or None)
        if item.payee:
            item.payee = (finance_ai.normalize_payee(item.payee) or item.payee)[:255]
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
    now = now or vault_now()
    if now.hour < int(row.hour or 6):
        return False
    if not row.last_sync_at:
        return True
    last_local = utc_naive_to_vault(row.last_sync_at)
    if last_local.date() != now.date():
        return True
    if row.last_ok:
        return False
    # Failed earlier today — retry after a half hour instead of every minute.
    return (now - last_local).total_seconds() >= 30 * 60


_STALLED_SCHEDULES_FIXED = False


def _enable_connected_without_schedule(db: Session) -> None:
    """Turn daily sync on for mailboxes that were connected but never scheduled.

    The old default left ``enabled`` off, so the in-process job never ran.
    Skip vaults that already have a scheduled log — they chose the setting.
    """
    global _STALLED_SCHEDULES_FIXED
    if _STALLED_SCHEDULES_FIXED:
        return
    rows = (
        db.query(models.ExpenseAnalyserConnection)
        .filter(
            models.ExpenseAnalyserConnection.refresh_token_enc.isnot(None),
            models.ExpenseAnalyserConnection.enabled.is_(False),
        )
        .all()
    )
    for row in rows:
        had_scheduled = (
            db.query(models.ExpenseAnalyserSyncLog.id)
            .filter(
                models.ExpenseAnalyserSyncLog.user_id == row.user_id,
                models.ExpenseAnalyserSyncLog.trigger == "scheduled",
            )
            .first()
        )
        if had_scheduled:
            continue
        row.enabled = True
        if row.hour is None:
            row.hour = 6
        log.info("Enabled daily Gmail sync for connected vault %s", row.user_id)
    db.commit()
    _STALLED_SCHEDULES_FIXED = True


def run_due_syncs() -> None:
    """Daily Gmail sync for vaults with auto-sync enabled (called from scheduler)."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        _enable_connected_without_schedule(db)
        rows = (
            db.query(models.ExpenseAnalyserConnection)
            .filter(
                models.ExpenseAnalyserConnection.enabled.is_(True),
                models.ExpenseAnalyserConnection.refresh_token_enc.isnot(None),
            )
            .all()
        )
        now = vault_now()
        due_ids = []
        for row in rows:
            if not should_run_now(row, now):
                continue
            if _is_syncing(row.user_id):
                continue
            due_ids.append(row.user_id)
    finally:
        db.close()

    for uid in due_ids:
        if start_sync_background(uid, trigger="scheduled"):
            log.info("Started scheduled Expense Analyser sync for %s", uid)
        else:
            log.info("Scheduled Expense Analyser sync already running for %s", uid)


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

    y, m = [int(p) for p in ym.split("-")]
    last_day = calendar.monthrange(y, m)[1]
    credit_by_day: dict[str, float] = {}
    count_by_day: dict[str, int] = {}
    weekday_amt = [0.0] * 7
    weekday_n = [0] * 7
    hist_n = [0] * 7
    hist_amt = [0.0] * 7
    hist_labels = (
        "Under ₹100", "₹100–500", "₹500–1k", "₹1k–2k", "₹2k–5k", "₹5k–10k", "₹10k+",
    )
    hist_bounds = (100, 500, 1000, 2000, 5000, 10000, None)
    for item in month_rows:
        day = _item_day(item) or f"{ym}-01"
        count_by_day[day] = count_by_day.get(day, 0) + 1
        amt = float(item.amount or 0)
        if item.direction == "credit":
            credit_by_day[day] = credit_by_day.get(day, 0) + amt
            continue
        try:
            wd = datetime.strptime(day, "%Y-%m-%d").weekday()
        except ValueError:
            wd = 0
        weekday_amt[wd] += amt
        weekday_n[wd] += 1
        placed = False
        for i, hi in enumerate(hist_bounds):
            lo = 0 if i == 0 else hist_bounds[i - 1]
            if amt >= lo and (hi is None or amt < hi):
                hist_n[i] += 1
                hist_amt[i] += amt
                placed = True
                break
        if not placed:
            hist_n[-1] += 1
            hist_amt[-1] += amt

    daily = []
    for day_n in range(1, last_day + 1):
        key = f"{ym}-{day_n:02d}"
        daily.append({
            "date": key,
            "day": day_n,
            "expense": round(by_day.get(key, 0.0), 2),
            "income": round(credit_by_day.get(key, 0.0), 2),
            "count": count_by_day.get(key, 0),
        })
    wd_names = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    wd_total = sum(weekday_amt) or 1.0
    weekday = [
        {
            "name": wd_names[i],
            "amount": round(weekday_amt[i], 2),
            "count": weekday_n[i],
            "pct": round(100.0 * weekday_amt[i] / wd_total, 1),
            "color": "#E8615C" if i < 5 else "#D4A657",
        }
        for i in range(7)
    ]
    hist_total = sum(hist_n) or 1
    histogram = [
        {
            "name": hist_labels[i],
            "amount": round(hist_amt[i], 2),
            "count": hist_n[i],
            "pct": round(100.0 * hist_n[i] / hist_total, 1),
            "color": "#4DD8E0",
        }
        for i in range(7)
    ]
    now = vault_now()
    is_current = ym == now.strftime("%Y-%m")
    today_day = now.day if is_current else None
    days_elapsed = now.day if is_current else last_day
    days_logged = sum(1 for d in daily if d["expense"] or d["income"])
    avg_day = round(debit_total / last_day, 2) if last_day else 0.0
    projected = round(debit_total, 2)
    if is_current and days_elapsed > 0:
        projected = round(debit_total / days_elapsed * last_day, 2)
    month_pct = round(100.0 * days_elapsed / last_day, 1) if last_day else 0.0
    first_wd = datetime(y, m, 1).weekday()
    heatmap_pad = (first_wd + 1) % 7
    net = round(credit_total - debit_total, 2)

    trend = []
    for i in range(-11, 1):
        ty, tm = y, m + i
        while tm < 1:
            tm += 12
            ty -= 1
        while tm > 12:
            tm -= 12
            ty += 1
        t_ym = f"{ty:04d}-{tm:02d}"
        t_deb = 0.0
        t_cred = 0.0
        for item in rows:
            day = _item_day(item)
            if not day or not day.startswith(t_ym):
                continue
            amt = float(item.amount or 0)
            if item.direction == "credit":
                t_cred += amt
            else:
                t_deb += amt
        trend.append({
            "year_month": t_ym,
            "label": datetime(ty, tm, 1).strftime("%b"),
            "income": round(t_cred, 2),
            "expense": round(t_deb, 2),
            "net": round(t_cred - t_deb, 2),
        })

    return {
        "year_month": ym,
        "label": label,
        "prev": prev,
        "next": nxt,
        "debit_total": round(debit_total, 2),
        "credit_total": round(credit_total, 2),
        "net": net,
        "item_count": len(month_rows),
        "avg_day": avg_day,
        "days_in_month": last_day,
        "days_elapsed": days_elapsed,
        "days_logged": days_logged,
        "month_pct": month_pct,
        "projected": projected,
        "today_day": today_day,
        "heatmap_pad": heatmap_pad,
        "by_category": _slices(by_cat, cat_count),
        "by_method": _slices(by_method, method_count),
        "by_day": day_bars,
        "daily": daily,
        "weekday": weekday,
        "histogram": histogram,
        "by_status": [
            {"name": k, "count": v, "color": _CHART_COLORS[i % len(_CHART_COLORS)]}
            for i, (k, v) in enumerate(sorted(status_count.items(), key=lambda x: -x[1]))
        ],
        "top_payees": _slices(by_payee, payee_count)[:10],
        "trend": trend,
    }