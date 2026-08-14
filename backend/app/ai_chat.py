"""Ask AI — vault-wide Q&A over Health, Money, Expense Analyser, Locker, URLs.

Secrets stay out of the prompt: no password vault plaintext, locker ID numbers,
hospital patient IDs, or API keys. The model only sees titles, dates, amounts,
and similar metadata.
"""
from __future__ import annotations

import calendar
import json
import re
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import ai_providers as ap
from app import crypto, models
from app.deps import vault_id
from app.finance_ai import DEFAULT_BASES, DEFAULT_MODELS

MAX_CONTEXT_CHARS = 22000
MAX_HISTORY = 20
CHAT_TIMEOUT = 60

SYSTEM_PROMPT = """You are Ask AI for a private household vault (Health, Money Manager, Expense Analyser, Document Vault, URL Vault, Password Vault).

Answer only from the VAULT SNAPSHOT attached to each turn. Do not invent hospitals, reports, transactions, balances, or dates. If the snapshot does not contain the answer, say what is missing and which module to open.

When the user asks for:
- hospital reports / labs / bills: list matching Health Vault documents (title, date, category, amount, person). Group by hospital.
- a credit-card (or any account) statement for a month: list that account's transactions for the month with date, payee, category, amount, and a total. Say if the account was not found.
- spend / income: use Money Manager ledger figures. Expense Analyser items are mail-parsed candidates (pending/matched/posted) — mention status if relevant.
- IDs / Aadhaar / PAN: you may name the Document Vault item and expiry, never an ID number (those are omitted on purpose).
- passwords / logins: you may name entries. Never claim to know a password.

Use Indian rupee amounts as written in the snapshot. Prefer compact markdown (short headings, bullets, tables). Be specific and concise. Today is in the snapshot header.
"""


def _uid(user: models.User) -> str:
    return vault_id(user)


def _inr(val) -> str:
    try:
        n = float(val or 0)
    except (TypeError, ValueError):
        return "₹ —"
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


def _f(val) -> float:
    try:
        return float(val or 0)
    except (TypeError, ValueError):
        return 0.0


def _clip(text: str | None, n: int = 180) -> str:
    s = re.sub(r"\s+", " ", (text or "")).strip()
    if len(s) <= n:
        return s
    return s[: n - 1].rstrip() + "…"


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


def _enum(val) -> str:
    if val is None:
        return ""
    return val.value if hasattr(val, "value") else str(val)


_MONTH_NAME = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
_MONTH_NAME.update({name.lower(): i for i, name in enumerate(calendar.month_abbr) if name})


def detect_months(question: str, today: datetime | None = None) -> list[str]:
    """YYYY-MM values mentioned or implied in the question."""
    today = today or datetime.utcnow()
    this = f"{today:%Y-%m}"
    q = (question or "").lower()
    found: list[str] = []
    if re.search(r"\b(this month|current month)\b", q):
        found.append(this)
    if re.search(r"\blast month\b", q):
        found.append(_shift_month(this, -1))
    for m in re.findall(r"\b(20\d{2})-(\d{2})\b", q):
        found.append(f"{m[0]}-{m[1]}")
    for name, year in re.findall(
        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
        r"dec(?:ember)?)\s+(20\d{2})\b",
        q,
    ):
        mi = _MONTH_NAME.get(name[:3].lower()) or _MONTH_NAME.get(name.lower())
        if mi:
            found.append(f"{year}-{mi:02d}")
    for year, name in re.findall(
        r"\b(20\d{2})\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
        r"dec(?:ember)?)\b",
        q,
    ):
        mi = _MONTH_NAME.get(name[:3].lower()) or _MONTH_NAME.get(name.lower())
        if mi:
            found.append(f"{year}-{mi:02d}")
    # Bare month name → this year (or last year if that month is still in the future? use this year)
    if not found:
        for name in _MONTH_NAME:
            if len(name) >= 3 and re.search(rf"\b{re.escape(name)}\b", q):
                mi = _MONTH_NAME[name]
                found.append(f"{today.year}-{mi:02d}")
                break
    # Dedup preserve order
    out, seen = [], set()
    for ym in found:
        if ym not in seen:
            seen.add(ym)
            out.append(ym)
    return out


def _match_names(question: str, names: list[str], min_len: int = 4) -> list[str]:
    q = (question or "").lower()
    hits = []
    for name in names:
        n = (name or "").strip()
        if len(n) < min_len:
            continue
        if n.lower() in q:
            hits.append(n)
    return hits


def suggestion_hints(db: Session, user: models.User) -> list[dict]:
    """Starter chips for the empty chat, based on what the vault actually has."""
    uid = _uid(user)
    hints: list[dict] = []
    pids = [
        r[0]
        for r in db.query(models.Person.id).filter(models.Person.user_id == uid).all()
    ]
    hospital = None
    if pids:
        hospital = (
            db.query(models.HospitalCard.hospital_name)
            .filter(models.HospitalCard.person_id.in_(pids))
            .order_by(models.HospitalCard.created_at.desc())
            .first()
        )
        if not hospital:
            hospital = (
                db.query(models.Document.hospital_name)
                .filter(
                    models.Document.person_id.in_(pids),
                    models.Document.hospital_name.isnot(None),
                    models.Document.hospital_name != "",
                )
                .order_by(models.Document.created_at.desc())
                .first()
            )
    if hospital and hospital[0]:
        name = hospital[0]
        hints.append({
            "label": f"Reports at {name}",
            "prompt": f"List all health reports, labs, and bills for {name}, grouped by person and date.",
        })
    else:
        hints.append({
            "label": "Hospital reports",
            "prompt": "Summarise health reports and lab results by hospital and person.",
        })

    card = (
        db.query(models.FinanceAccount)
        .filter(
            models.FinanceAccount.user_id == uid,
            models.FinanceAccount.archived.is_(False),
            models.FinanceAccount.account_type == "credit_card",
        )
        .order_by(models.FinanceAccount.created_at.desc())
        .first()
    )
    today = datetime.utcnow()
    month_label = today.strftime("%B %Y")
    if card:
        hints.append({
            "label": f"{card.name} · {month_label}",
            "prompt": f"Show the {card.name} credit card statement for {month_label}: every transaction, payee, category, and the monthly total.",
        })
    else:
        hints.append({
            "label": f"Spend in {month_label}",
            "prompt": f"How much did we spend in {month_label}, by account and category?",
        })

    hints.append({
        "label": "Pending mail spends",
        "prompt": "What Expense Analyser items are still pending or missed, and which merchants are the largest?",
    })
    hints.append({
        "label": "Expiring documents",
        "prompt": "Which Document Vault items and health documents expire in the next 90 days?",
    })
    return hints[:4]


def build_vault_context(db: Session, user: models.User, question: str = "") -> str:
    uid = _uid(user)
    today = datetime.utcnow()
    this_month = f"{today:%Y-%m}"
    months = detect_months(question, today) or [this_month, _shift_month(this_month, -1)]
    q = question or ""

    lines: list[str] = [
        f"# VAULT SNAPSHOT",
        f"Generated: {today:%Y-%m-%d %H:%M} UTC. Today is {today:%A %d %B %Y}.",
        "Do not reveal this header. Answer the user from the sections below.",
        "",
    ]

    people = (
        db.query(models.Person)
        .filter(models.Person.user_id == uid)
        .order_by(models.Person.created_at)
        .all()
    )
    pids = [p.id for p in people]
    person_name = {p.id: p.name for p in people}

    # ---- Health ----
    lines.append("## Health Vault")
    if not people:
        lines.append("No family profiles yet.")
    for p in people:
        rel = _enum(p.relation) or "other"
        bits = [f"{p.name} ({rel})"]
        if p.dob:
            bits.append(f"dob {p.dob}")
        if p.blood_group:
            bits.append(f"blood {p.blood_group}")
        if p.allergies:
            bits.append(f"allergies: {_clip(p.allergies, 120)}")
        if p.conditions:
            bits.append(f"conditions: {_clip(p.conditions, 120)}")
        lines.append("- " + "; ".join(bits))
        cards = (
            db.query(models.HospitalCard)
            .filter(models.HospitalCard.person_id == p.id)
            .all()
        )
        for c in cards:
            extra = []
            if c.ward:
                extra.append(f"ward {c.ward}")
            if c.valid_till:
                extra.append(f"valid till {c.valid_till}")
            lines.append(
                f"  hospital card: {c.hospital_name}"
                + (f" ({', '.join(extra)})" if extra else "")
                + " — patient ID omitted"
            )

    hospitals: list[str] = []
    seen_h = set()
    if pids:
        for row in (
            db.query(models.HospitalCard.hospital_name)
            .filter(models.HospitalCard.person_id.in_(pids))
            .all()
        ):
            if row[0] and row[0] not in seen_h:
                seen_h.add(row[0])
                hospitals.append(row[0])
        for row in (
            db.query(models.Document.hospital_name)
            .filter(models.Document.person_id.in_(pids), models.Document.hospital_name.isnot(None))
            .all()
        ):
            if row[0] and row[0] not in seen_h:
                seen_h.add(row[0])
                hospitals.append(row[0])
    hit_hospitals = _match_names(q, hospitals, min_len=3)

    docs_q = db.query(models.Document)
    if pids:
        docs_q = docs_q.filter(models.Document.person_id.in_(pids))
    else:
        docs_q = docs_q.filter(False)
    docs = docs_q.order_by(models.Document.doc_date.desc(), models.Document.created_at.desc()).limit(80).all()

    extra_docs: list[models.Document] = []
    if hit_hospitals and pids:
        extra_docs = (
            db.query(models.Document)
            .filter(
                models.Document.person_id.in_(pids),
                models.Document.hospital_name.in_(hit_hospitals),
            )
            .order_by(models.Document.doc_date.desc())
            .limit(60)
            .all()
        )
    seen_doc = {d.id for d in docs}
    for d in extra_docs:
        if d.id not in seen_doc:
            docs.append(d)
            seen_doc.add(d.id)

    if docs:
        lines.append("Health documents (title / hospital / date / category / amount):")
        for d in docs[:100]:
            who = person_name.get(d.person_id, "")
            cat = _enum(d.category)
            amt = f" {_inr(d.amount)}" if d.amount else ""
            lines.append(
                f"- {d.doc_date or 'undated'} · {who} · {cat}"
                f"{' / ' + d.custom_category if d.custom_category else ''}"
                f" · {d.title} · {d.hospital_name or '—'}"
                f"{amt}"
            )
            if hit_hospitals and d.extracted_text and (
                (d.hospital_name or "") in hit_hospitals
                or re.search(r"\b(report|lab|bill|result)\b", q, re.I)
            ):
                lines.append(f"  excerpt: {_clip(d.extracted_text, 280)}")
    else:
        lines.append("No health documents stored.")

    if pids:
        visits = (
            db.query(models.Visit)
            .filter(models.Visit.person_id.in_(pids))
            .order_by(models.Visit.visit_date.desc())
            .limit(20)
            .all()
        )
        if visits:
            lines.append("Recent visits:")
            for v in visits:
                lines.append(
                    f"- {v.visit_date or 'undated'} · {person_name.get(v.person_id, '')} · "
                    f"{v.hospital_name or '—'} · {v.doctor_name or ''} · {v.reason or ''}"
                )
        labs = (
            db.query(models.LabReading)
            .filter(models.LabReading.person_id.in_(pids))
            .order_by(models.LabReading.measured_at.desc())
            .limit(30)
            .all()
        )
        if labs:
            lines.append("Lab readings:")
            for r in labs:
                lines.append(
                    f"- {r.measured_at or 'undated'} · {person_name.get(r.person_id, '')} · "
                    f"{r.metric} {r.value} {r.unit or ''}"
                )
        meds = (
            db.query(models.Medicine)
            .filter(models.Medicine.person_id.in_(pids))
            .order_by(models.Medicine.created_at.desc())
            .limit(20)
            .all()
        )
        if meds:
            lines.append("Medicines:")
            for m in meds:
                lines.append(
                    f"- {person_name.get(m.person_id, '')} · {m.name} {m.dose or ''} {m.timing or ''}"
                )
        claims = (
            db.query(models.Claim)
            .filter(models.Claim.person_id.in_(pids))
            .order_by(models.Claim.created_at.desc())
            .limit(15)
            .all()
        )
        if claims:
            lines.append("Insurance claims:")
            for c in claims:
                lines.append(
                    f"- {person_name.get(c.person_id, '')} · {c.insurer or '—'} · "
                    f"{c.status} · {c.amount or ''} · {c.claim_number or ''}"
                )
        reminders = (
            db.query(models.Reminder)
            .filter(models.Reminder.person_id.in_(pids), models.Reminder.is_active.is_(True))
            .order_by(models.Reminder.remind_at)
            .limit(15)
            .all()
        )
        if reminders:
            lines.append("Active reminders:")
            for r in reminders:
                when = r.remind_at.strftime("%Y-%m-%d") if r.remind_at else ""
                lines.append(f"- {when} · {person_name.get(r.person_id, '')} · {r.title}")

    # ---- Money ----
    lines.append("")
    lines.append("## Money Manager")
    accounts = (
        db.query(models.FinanceAccount)
        .filter(models.FinanceAccount.user_id == uid, models.FinanceAccount.archived.is_(False))
        .order_by(models.FinanceAccount.name)
        .all()
    )
    acct_by_id = {a.id: a for a in accounts}
    if not accounts:
        lines.append("No accounts yet.")
    for a in accounts:
        extra = [a.account_type]
        if a.institution:
            extra.append(a.institution)
        if a.last4:
            extra.append(f"last4 {a.last4}")
        if a.credit_limit is not None:
            extra.append(f"limit {_inr(a.credit_limit)}")
        lines.append(f"- Account: {a.name} ({', '.join(extra)})")

    cats = {
        c.id: c.name
        for c in db.query(models.FinanceCategory).filter(models.FinanceCategory.user_id == uid).all()
    }
    account_names = [a.name for a in accounts] + [a.institution or "" for a in accounts]
    hit_accounts = _match_names(q, [n for n in account_names if n], min_len=3)
    hit_acct_ids = [
        a.id for a in accounts
        if a.name in hit_accounts
        or (a.institution and a.institution in hit_accounts)
        or (a.last4 and re.search(rf"\b{re.escape(a.last4)}\b", q))
    ]
    # If they said "credit card" with no name, include all cards
    if not hit_acct_ids and re.search(r"\b(credit\s*card|card statement)\b", q, re.I):
        hit_acct_ids = [a.id for a in accounts if a.account_type == "credit_card"]

    for ym in months:
        start, end = _month_bounds(ym)
        txns = (
            db.query(models.FinanceTransaction)
            .filter(
                models.FinanceTransaction.user_id == uid,
                models.FinanceTransaction.txn_date >= start,
                models.FinanceTransaction.txn_date <= end,
            )
            .order_by(models.FinanceTransaction.txn_date, models.FinanceTransaction.created_at)
            .all()
        )
        exp = sum(_f(t.amount) for t in txns if t.txn_type == "expense")
        inc = sum(_f(t.amount) for t in txns if t.txn_type == "income")
        lines.append(
            f"{ym} totals: expense {_inr(exp)}, income {_inr(inc)}, "
            f"{len(txns)} entries."
        )
        by_acct: dict[str, dict[str, float]] = defaultdict(lambda: {"expense": 0.0, "income": 0.0})
        by_cat: dict[str, float] = defaultdict(float)
        for t in txns:
            name = acct_by_id[t.account_id].name if t.account_id in acct_by_id else t.account_id
            by_acct[name][t.txn_type] = by_acct[name].get(t.txn_type, 0) + _f(t.amount)
            if t.txn_type == "expense":
                by_cat[cats.get(t.category_id) or "Uncategorised"] += _f(t.amount)
        if by_acct:
            lines.append(f"{ym} by account:")
            for name, vals in sorted(by_acct.items()):
                bits = []
                if vals.get("expense"):
                    bits.append(f"out {_inr(vals['expense'])}")
                if vals.get("income"):
                    bits.append(f"in {_inr(vals['income'])}")
                lines.append(f"- {name}: {', '.join(bits) or '—'}")
        if by_cat:
            top = sorted(by_cat.items(), key=lambda kv: kv[1], reverse=True)[:8]
            lines.append(f"{ym} expense categories: " + ", ".join(f"{n} {_inr(v)}" for n, v in top))

        focus_ids = hit_acct_ids or ([a.id for a in accounts if a.account_type == "credit_card"] if ym in months[:1] else [])
        # Always list month txns for matched accounts; otherwise a short recent slice of this month
        list_txns = [t for t in txns if not focus_ids or t.account_id in focus_ids]
        cap = 80 if hit_acct_ids else 25
        if list_txns:
            label = "matched account(s)" if hit_acct_ids else "sample"
            lines.append(f"{ym} transactions ({label}):")
            for t in list_txns[:cap]:
                acct = acct_by_id.get(t.account_id)
                lines.append(
                    f"- {t.txn_date} · {acct.name if acct else '?'} · {t.txn_type} · "
                    f"{_inr(t.amount)} · {t.payee or '—'} · {cats.get(t.category_id) or '—'} · "
                    f"{t.payment_method or ''}"
                )

    emis = (
        db.query(models.FinanceEmi)
        .filter(models.FinanceEmi.user_id == uid, models.FinanceEmi.active.is_(True))
        .all()
    )
    if emis:
        lines.append("Active EMIs / recurring loans:")
        for e in emis:
            acct = acct_by_id.get(e.account_id)
            lines.append(
                f"- {e.name} ({e.kind}) {_inr(e.amount)} from {acct.name if acct else '?'} "
                f"next {e.next_due or '—'}"
            )

    # ---- Expense Analyser ----
    lines.append("")
    lines.append("## Expense Analyser (Gmail bank/card alerts)")
    conn = (
        db.query(models.ExpenseAnalyserConnection)
        .filter(models.ExpenseAnalyserConnection.user_id == uid)
        .first()
    )
    if conn:
        lines.append(
            f"Gmail: {'connected ' + (conn.connected_email or '') if conn.refresh_token_enc else 'not connected'}; "
            f"daily sync {'on' if conn.enabled else 'off'}."
        )
    items = (
        db.query(models.ExpenseAnalyserItem)
        .filter(models.ExpenseAnalyserItem.user_id == uid)
        .order_by(models.ExpenseAnalyserItem.txn_date.desc(), models.ExpenseAnalyserItem.created_at.desc())
        .limit(60)
        .all()
    )
    if items:
        by_st: dict[str, int] = defaultdict(int)
        for it in items:
            by_st[it.status or "pending"] += 1
        lines.append("Recent item status counts (last 60): " + ", ".join(f"{k} {v}" for k, v in sorted(by_st.items())))
        lines.append("Recent analyser items:")
        for it in items[:40]:
            lines.append(
                f"- {it.txn_date or 'undated'} · {it.status} · {it.direction} · "
                f"{_inr(it.amount) if it.amount is not None else '—'} · {it.payee or '—'} · "
                f"{it.suggested_category or '—'} · {it.payment_method or ''} · {_clip(it.subject, 80)}"
            )
    else:
        lines.append("No analyser items yet.")

    # ---- Locker ----
    lines.append("")
    lines.append("## Document Vault (IDs & papers — ID numbers omitted)")
    locker = (
        db.query(models.LockerItem)
        .filter(models.LockerItem.user_id == uid)
        .order_by(models.LockerItem.expiry_date.asc(), models.LockerItem.created_at.desc())
        .limit(40)
        .all()
    )
    if locker:
        soon = (today + timedelta(days=90)).strftime("%Y-%m-%d")
        for it in locker:
            flag = ""
            if it.expiry_date and it.expiry_date <= soon:
                flag = " EXPIRING"
            lines.append(
                f"- {it.title} · {it.doc_type}"
                f"{' / ' + it.custom_type if it.custom_type else ''} · "
                f"{it.holder_name or ''} · {it.issuer or ''} · expiry {it.expiry_date or '—'}{flag}"
            )
    else:
        lines.append("No locker items.")

    # ---- URLs ----
    url_n = (
        db.query(models.UrlItem)
        .filter(models.UrlItem.user_id == uid)
        .count()
    )
    fav_n = (
        db.query(models.UrlItem)
        .filter(models.UrlItem.user_id == uid, models.UrlItem.favorite.is_(True))
        .count()
    )
    lines.append("")
    lines.append(f"## URL Vault: {url_n} bookmarks ({fav_n} favorites). Titles:")
    urls = (
        db.query(models.UrlItem)
        .filter(models.UrlItem.user_id == uid)
        .order_by(models.UrlItem.updated_at.desc())
        .limit(25)
        .all()
    )
    cat_map = {
        c.id: c.name
        for c in db.query(models.UrlCategory).filter(models.UrlCategory.user_id == uid).all()
    }
    for u in urls:
        lines.append(f"- {u.title} · {cat_map.get(u.category_id) or 'uncategorised'}" + (" ★" if u.favorite else ""))

    # ---- Passwords (counts + names only) ----
    pw_q = db.query(models.VaultItem).filter(
        models.VaultItem.user_id == uid, models.VaultItem.deleted_at.is_(None)
    )
    pw_n = pw_q.count()
    by_type: dict[str, int] = defaultdict(int)
    names = []
    for it in pw_q.order_by(models.VaultItem.name).limit(40).all():
        by_type[it.item_type or "login"] += 1
        names.append(f"{it.name} ({it.item_type})")
    lines.append("")
    lines.append(
        f"## Password Vault: {pw_n} items "
        + ("(" + ", ".join(f"{k} {v}" for k, v in sorted(by_type.items())) + "). " if pw_n else "")
        + "Secrets are not included. Names: "
        + (", ".join(names) if names else "none")
    )

    text = "\n".join(lines)
    if len(text) > MAX_CONTEXT_CHARS:
        text = text[: MAX_CONTEXT_CHARS - 20] + "\n… [truncated]"
    return text


def complete_chat(
    *,
    kind: str,
    api_key: str | None,
    model: str | None,
    base_url: str | None,
    system: str,
    messages: list[dict[str, str]],
) -> str:
    kind = (kind or "openai").lower()
    model = model or DEFAULT_MODELS.get(kind, "gpt-4o-mini")
    base = (base_url or DEFAULT_BASES.get(kind) or "https://api.openai.com/v1").rstrip("/")
    if kind == "anthropic":
        if not api_key:
            raise ValueError("Anthropic needs an API key")
        return _anthropic_messages(api_key, model, system, messages)
    return _openai_messages(base, api_key, model, system, messages)


def _openai_messages(
    base_url: str, api_key: str | None, model: str, system: str, messages: list[dict[str, str]]
) -> str:
    payload = [{"role": "system", "content": system}] + messages
    body = json.dumps({
        "model": model,
        "temperature": 0.2,
        "max_tokens": 2500,
        "messages": payload,
    }).encode()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=body, headers=headers, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=CHAT_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise ValueError(f"Provider HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise ValueError(f"Provider unreachable: {exc.reason}") from exc
    return (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""


def _anthropic_messages(
    api_key: str, model: str, system: str, messages: list[dict[str, str]]
) -> str:
    # Anthropic requires alternating user/assistant, first must be user.
    cleaned: list[dict[str, str]] = []
    for m in messages:
        role = "assistant" if m.get("role") == "assistant" else "user"
        content = m.get("content") or ""
        if cleaned and cleaned[-1]["role"] == role:
            cleaned[-1]["content"] += "\n" + content
        else:
            cleaned.append({"role": role, "content": content})
    if cleaned and cleaned[0]["role"] != "user":
        cleaned.insert(0, {"role": "user", "content": "(continue)"})
    body = json.dumps({
        "model": model,
        "max_tokens": 2500,
        "temperature": 0.2,
        "system": system,
        "messages": cleaned,
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=CHAT_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise ValueError(f"Anthropic HTTP {exc.code}: {detail}") from exc
    parts = data.get("content") or []
    return "".join(p.get("text") or "" for p in parts if isinstance(p, dict))


def _title_from(message: str) -> str:
    t = re.sub(r"\s+", " ", (message or "").strip())
    if len(t) > 72:
        t = t[:71].rstrip() + "…"
    return t or "New chat"


def _iso(dt) -> str | None:
    if dt is None:
        return None
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)


def _msg_out(row: models.AiChatMessage) -> dict:
    return {
        "id": row.id,
        "role": row.role,
        "content": crypto.decrypt_text(row.content_enc) or "",
        "created_at": _iso(row.created_at),
    }


def _thread_out(row: models.AiChatThread, preview: str | None = None) -> dict:
    return {
        "id": row.id,
        "title": row.title,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at or row.created_at),
        "preview": preview,
    }


def list_threads(db: Session, user: models.User) -> list[dict]:
    uid = _uid(user)
    rows = (
        db.query(models.AiChatThread)
        .filter(models.AiChatThread.user_id == uid)
        .order_by(models.AiChatThread.updated_at.desc())
        .limit(50)
        .all()
    )
    out = []
    for t in rows:
        last = (
            db.query(models.AiChatMessage)
            .filter(models.AiChatMessage.thread_id == t.id)
            .order_by(models.AiChatMessage.created_at.desc())
            .first()
        )
        preview = None
        if last:
            preview = _clip(crypto.decrypt_text(last.content_enc), 90)
        out.append(_thread_out(t, preview))
    return out


def get_thread(db: Session, user: models.User, thread_id: str) -> models.AiChatThread | None:
    return (
        db.query(models.AiChatThread)
        .filter(models.AiChatThread.id == thread_id, models.AiChatThread.user_id == _uid(user))
        .first()
    )


def thread_detail(db: Session, user: models.User, thread_id: str) -> dict | None:
    row = get_thread(db, user, thread_id)
    if not row:
        return None
    msgs = (
        db.query(models.AiChatMessage)
        .filter(models.AiChatMessage.thread_id == row.id)
        .order_by(models.AiChatMessage.created_at)
        .all()
    )
    return {
        **_thread_out(row),
        "messages": [_msg_out(m) for m in msgs],
    }


def delete_thread(db: Session, user: models.User, thread_id: str) -> bool:
    row = get_thread(db, user, thread_id)
    if not row:
        return False
    db.query(models.AiChatMessage).filter(models.AiChatMessage.thread_id == row.id).delete()
    db.delete(row)
    db.commit()
    return True


def ask(db: Session, user: models.User, message: str, thread_id: str | None = None) -> dict:
    text = (message or "").strip()
    if not text:
        raise ValueError("Type a question first")
    bundle = ap.get_default_bundle(db, user)
    if not bundle:
        raise LookupError("Add an AI provider first")

    thread = get_thread(db, user, thread_id) if thread_id else None
    if thread_id and not thread:
        raise LookupError("Chat not found")
    if not thread:
        thread = models.AiChatThread(user_id=_uid(user), title=_title_from(text))
        db.add(thread)
        db.flush()

    prior = (
        db.query(models.AiChatMessage)
        .filter(models.AiChatMessage.thread_id == thread.id)
        .order_by(models.AiChatMessage.created_at)
        .all()
    )
    history = [_msg_out(m) for m in prior[-MAX_HISTORY:]]

    snapshot = build_vault_context(db, user, text)
    system = SYSTEM_PROMPT + "\n\n" + snapshot
    payload = [{"role": m["role"], "content": m["content"]} for m in history]
    payload.append({"role": "user", "content": text})

    try:
        reply = complete_chat(
            kind=bundle["kind"],
            api_key=bundle.get("api_key"),
            model=bundle.get("model"),
            base_url=bundle.get("base_url"),
            system=system,
            messages=payload,
        ).strip()
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Provider failed: {exc}") from exc
    if not reply:
        reply = "The provider returned an empty reply. Try again, or test the key on the Providers page."

    now = datetime.utcnow()
    user_row = models.AiChatMessage(
        thread_id=thread.id, role="user", content_enc=crypto.encrypt_text(text), created_at=now,
    )
    asst_row = models.AiChatMessage(
        thread_id=thread.id, role="assistant", content_enc=crypto.encrypt_text(reply),
        created_at=now + timedelta(seconds=1),
    )
    db.add(user_row)
    db.add(asst_row)
    if thread.title in {"New chat", ""}:
        thread.title = _title_from(text)
    thread.updated_at = now
    db.commit()
    db.refresh(thread)

    detail = thread_detail(db, user, thread.id)
    return {
        "thread_id": thread.id,
        "title": thread.title,
        "reply": reply,
        "messages": detail["messages"] if detail else [],
    }
