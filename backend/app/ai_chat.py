"""Ask AI — vault-wide Q&A over Health, Money, Expense Analyser, Shopping List,
Digital Diary, Locker, URLs.

Secrets stay out of the prompt: no password vault plaintext or names, locker ID
numbers, medical record text, or API keys. Password and medical questions are
answered on this server with view links — they never go to the AI provider.
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
from app.config import settings, vault_now
from app.deps import vault_id
from app.finance_ai import DEFAULT_BASES, DEFAULT_MODELS

MAX_CONTEXT_CHARS = 22000
MAX_HISTORY = 20
CHAT_TIMEOUT = 60

SYSTEM_PROMPT = """You are Ask AI for a private household vault (Health, Money Manager, Expense Analyser, Shopping List, Digital Diary, Document Vault, URL Vault, Password Vault).

Language: The user may write in English, Malayalam script, or Manglish (Malayalam in Latin letters, e.g. “kazhinja maasam enna vaangiya?”, “atta podi koode list undaakkan”). Understand all three. Reply in the same style the user used when helpful (short Manglish is fine); otherwise use clear English. Always keep vault facts accurate. Treat “dairy” as a common typo for Digital Diary when the intent is clearly a journal/note.

Clarify first (smart, not chatty):
- If you cannot answer correctly without knowing which module, which person, which day/month, or posted ledger vs Gmail inbox, ask ONE short question. Then wait. Do not guess. Do not invent a ₹0 total while mail is still pending.
- One question at a time. Offer numbered choices when helpful (e.g. Money Manager ledger / Expense Analyser Gmail / both).
- Do not ask when they already named the module, person, or date, or when their message is a choice from your last question.
- After they clarify, answer from the snapshot only — still do not invent facts.

For questions about existing vault data, answer only from the VAULT SNAPSHOT. Do not invent hospitals, reports, transactions, balances, shopping items, or past diary entries. If the snapshot lacks the answer, say what is missing and which module to open.

When the user asks for:
- hospital reports / labs / bills: list matching Health Vault documents (title, date, category, amount, person). Group by hospital.
- a doctor / specialist / phone number (e.g. gynaecology, paediatrician, “Dr Mehta number”): use the Doctors directory in the snapshot. Answer with name, specialty, hospital, and phone. If several match, list them. If none match, say so and suggest opening Health Vault → Doctors.
- spend / income lookups: use Money Manager ledger figures only. Digital Diary charges/notes are journal text — never treat them as today’s (or any day’s) Money Manager expense total unless the user asked about the diary. Expense Analyser items are mail-parsed candidates (pending/matched/posted) — mention status if relevant; do not count unposted alerts as ledger spend.
- “today” / “todays” / “ippo” spend: use the snapshot line “Today (Money Manager)” and that date’s listed ledger rows. Do not use a different date from chat history or diary.
- highest / biggest / costliest paid item or purchase: use Money Manager ledger rows. The **payee** is the item/title (e.g. Home Purchase, HDFC Bank). Category names like Shopping are not the item. Shopping List grocery rows usually have no rupee amount — do not invent one. If a payee is listed, never say the name is missing.
- a credit-card (or any account) statement for a month: list that account's transactions for the month with date, payee, category, amount, and a total. Say if the account was not found.
- shopping / groceries / “did I buy X” / “X vaangiya?”: use the Shopping List section and any Manglish glossary hints. Prefer item names over merchant payees for products (oil/enna, rice/ari, atta, etc.).
- create / suggest a shopping list: propose a clear list from the snapshot (history frequencies and/or items the user named, including Manglish). Explain briefly, then emit ONE vault-action block (see below) so the user can approve creation.
- diary / journal / notes / “diary il undayirunno?” (lookups): use the Digital Diary section (titles, dates, categories, tags, body excerpts).
- add / save / write a diary note that is NOT primarily an expense (e.g. “add Thidanad trip to diary”, “diary il ittu”, “save this note”, including “dairy” typos): draft from the USER’S message — do not wait for that note to already exist in the snapshot. Confirm briefly, then emit ONE create_diary_entry vault-action. Prefer category Travel for trips; otherwise Personal or a matching snapshot folder name.
- create a diary folder / shelf / category (e.g. “make a Thidanad folder”, “new diary folder for Kerala trip”): confirm briefly, then emit ONE create_diary_folder vault-action. Do not invent folders that already exist in the Digital Diary snapshot — reuse the existing name instead.
- spent / paid / “adichu” / “vaangi” / petrol / food with an amount (expense-like):
  - If they already named Money Manager / ledger / finance / account → emit create_finance_txn (pick a snapshot account + expense category when possible).
  - If they already named Digital Diary / diary / dairy / note → emit create_diary_entry with charges[].
  - If destination is unclear → briefly confirm amount + what they spent on, then ask: Money Manager (ledger) or Digital Diary (journal)? Do NOT emit any vault-action until they choose.
  - Short follow-ups like “money”, “money manager”, “ledger”, “diary”, “dairy” refer to the latest expense in the thread — then emit the matching vault-action.
- calculate / total / split charges then save: show a markdown table with Total; ask Money Manager vs Diary if unclear; emit create_finance_txn or create_diary_entry only after they choose (or if they already chose).
- IDs / Aadhaar / PAN / medical records / passwords: those details are NOT in this snapshot and must not be guessed. The app answers those on the server with a view link. Never invent a password, ID number, lab value, or hospital report.

Creating a shopping list — after your normal markdown answer, if (and only if) the user wants a new list created, append exactly one fenced block:

```vault-action
{"type":"create_shop_list","name":"Short list title","items":[{"name":"Onion","quantity":1,"unit":"kg"},{"name":"Atta"}]}
```

Creating a diary entry — after your normal markdown answer, if (and only if) the user wants it saved to Digital Diary, append exactly one fenced block:

```vault-action
{"type":"create_diary_entry","title":"Short title","body":"Optional notes","charges":[{"label":"Cake","amount":1200},{"label":"Decor","amount":800}],"entry_date":"2026-08-15","category":"Personal","tags":"party, charges","mood":"","pinned":false}
```

Creating a diary folder — after your normal markdown answer, if (and only if) the user wants a new Digital Diary folder, append exactly one fenced block:

```vault-action
{"type":"create_diary_folder","name":"Thidanad trip","color":"#22D3EE"}
```

Creating a Money Manager ledger entry — after your normal markdown answer, if (and only if) the user wants it on the ledger, append exactly one fenced block:

```vault-action
{"type":"create_finance_txn","amount":250,"payee":"Petrol","account":"Cash","category":"Transport","txn_type":"expense","txn_date":"2026-08-15","notes":"Petrol filled","payment_method":"cash"}
```

Rules for vault-action:
- Emit at most ONE vault-action block per reply (shop list OR diary entry OR diary folder OR finance, not more than one)
- create_shop_list: name + items (1–60) with name required, optional quantity/unit; use English grocery names when known (ulli→Onion, enna→Coconut Oil, sharkara→Jaggery)
- create_diary_entry: title required; body may be the user’s note text (trips, events, freeform). Include charges[] only when you totalled money — the app formats a ₹ table with Total. Optional entry_date (YYYY-MM-DD, default today), category (folder name from snapshot), tags, mood, pinned
- create_diary_folder: name required (short English title); optional color as #RRGGBB. Prefer Travel-like teal (#22D3EE) for trips.
- create_finance_txn: amount > 0 required; payee short English label; account and category must match names from the Money Manager snapshot when possible; txn_type expense|income (default expense); optional txn_date (YYYY-MM-DD, default today), notes, payment_method (upi|credit_card|debit_card|atm|netbanking|cash|other)
- When charges[] or finance amount is present, show the numbers clearly in the visible reply
- Do NOT emit vault-action for pure questions (e.g. “did I buy oil?” / “diary il enthu ezhuthi?” / “how much petrol this month?”)
- Do NOT emit vault-action while asking Money Manager vs Diary — wait for their choice
- Do NOT emit vault-action while asking a clarifying question — wait for their choice
- For history-based shop lists, prefer frequent checked items from the months asked — do not invent past purchases. For new diary notes, folders, or ledger rows the user is dictating, use their words freely.

Household brain — if the snapshot has a HOUSEHOLD BRAIN section, treat those as lasting preferences (brands, aliases, default accounts, “we always…”). Do not let them override live ledger totals or shopping-list rows.

When the user teaches a lasting fact, preference, nickname, or correction (e.g. “remember…”, “always use Home for petrol”, “ulli means shallot here”), after your normal answer emit ONE vault-memory block. Skip one-off questions. Never store passwords, OTPs, ID numbers, card numbers, or medical report values.

```vault-memory
{"memories":[{"kind":"preference","slug":"cooking-oil","content":"Prefer coconut oil, not sunflower"}]}
```

kind must be fact, preference, alias, or habit. slug is a short kebab-case key. content is one short sentence.

Use Indian rupee amounts as written in the snapshot. Prefer compact markdown (short headings, bullets, tables). Be specific and concise. Today is in the snapshot header.
"""

_VAULT_ACTION_RE = re.compile(
    r"```vault-action\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)


def _uid(user: models.User) -> str:
    return vault_id(user)


def vault_today() -> str:
    return vault_now().strftime("%Y-%m-%d")


_SPEND_RE = re.compile(
    r"\b(expense|expenses|spend|spent|spending|total|kharcha?|adichu|vaangi|"
    r"paid|payment|outflow|debit|trans?actions?|trasactions?|trasnactions?|txn)\b",
    re.I,
)
_UPI_RE = re.compile(r"\bupi\b", re.I)
_TODAY_RE = re.compile(
    r"\b(today|todays|today'?s|ippo|innu|ee\s*divasam|ee\s*naal)\b",
    re.I,
)
_YESTERDAY_RE = re.compile(
    r"\b(yesterday|yesterdays|yesterday'?s|innale|kazinja\s*divasam)\b",
    re.I,
)
_FOLLOWUP_RE = re.compile(
    r"\b(sure|really|confirm|which|list|they|them|details|break\s*down|itemize|"
    r"what was that|what is that|item name|the name|"
    r"double\s*check(?:it)?|checkit|re-?check|check\s+(?:it\s+)?(?:once\s+more|again)|"
    r"once more|refresh)\b",
    re.I,
)
_CHOICE_SOURCE = {
    "1": "ledger", "one": "ledger",
    "2": "analyser", "two": "analyser",
    "3": "both", "three": "both",
}
_HIGHEST_RE = re.compile(
    r"\b(highest|highst|hight|hght|costliest|biggest|largest|max(?:imum)?|"
    r"most\s+expensive|kooduthal)\b",
    re.I,
)
_PURCHASE_RE = re.compile(
    r"\b(paid|pay|pid|price|priced|item|purchase|purchases|expense|expenses|"
    r"spend|spent|adichu|vaangi|cost)\b",
    re.I,
)


def resolve_ledger_day(question: str, today: datetime | None = None) -> str | None:
    """YYYY-MM-DD when the question is about that calendar day's Money Manager spend."""
    today = today or vault_now()
    q = (question or "").strip()
    if not q:
        return None
    spendish = bool(_SPEND_RE.search(q)) or bool(
        re.search(r"\b(petrol|upi|atm|ledger|money\s*manager)\b", q, re.I)
    )
    if _TODAY_RE.search(q) and (spendish or len(q.split()) <= 4):
        return today.strftime("%Y-%m-%d")
    if _YESTERDAY_RE.search(q) and (spendish or len(q.split()) <= 6):
        return (today - timedelta(days=1)).strftime("%Y-%m-%d")
    return None


def should_answer_ledger_day(
    question: str,
    history: list[dict] | None = None,
    today: datetime | None = None,
) -> str | None:
    """Day to answer from Money Manager, including short follow-ups in a spend thread."""
    today = today or vault_now()
    day = resolve_ledger_day(question, today)
    if day:
        return day
    if not (
        _FOLLOWUP_RE.search(question or "")
        or _source_from_text(question, numbered=_clarify_pending(history))
    ):
        return None
    for m in reversed(history or []):
        if (m.get("role") or "") != "user":
            continue
        day = resolve_ledger_day(m.get("content") or "", today)
        if day:
            return day
    return None


_SOURCE_LEDGER_RE = re.compile(r"\b(ledger|money\s*manager|posted|finance)\b", re.I)
_SOURCE_GMAIL_RE = re.compile(
    r"\b(gmail|inbox|pending|analyser|analyzer|mail|alerts?)\b", re.I,
)
_SOURCE_BOTH_RE = re.compile(r"\b(both|all(\s+of\s+them)?|everywhere)\b", re.I)
_LEDGER_INTENT_RE = re.compile(
    r"\b(total\s+(expense|expenses|spend|spending)|how much(\s+\w+){0,3}\s+spend)\b",
    re.I,
)
_CLARIFY_MARK = "Which should I check?"


def _clarify_pending(history: list[dict] | None) -> bool:
    for m in reversed(history or []):
        if (m.get("role") or "") != "assistant":
            continue
        return _CLARIFY_MARK in (m.get("content") or "")
    return False


def _thread_asked_clarify(history: list[dict] | None) -> bool:
    return any(
        (m.get("role") or "") == "assistant" and _CLARIFY_MARK in (m.get("content") or "")
        for m in (history or [])
    )


def _source_from_text(question: str, *, numbered: bool = False) -> str | None:
    q = (question or "").strip()
    if not q:
        return None
    if numbered:
        key = re.sub(r"[.\)\:]$", "", q.strip().lower())
        if key in _CHOICE_SOURCE:
            return _CHOICE_SOURCE[key]
    both = bool(_SOURCE_BOTH_RE.search(q))
    gmail = bool(_SOURCE_GMAIL_RE.search(q))
    ledger = bool(_SOURCE_LEDGER_RE.search(q))
    if both or (gmail and ledger):
        return "both"
    if gmail:
        return "analyser"
    if ledger:
        return "ledger"
    return None


def resolve_spend_source(question: str, history: list[dict] | None = None) -> str | None:
    numbered_now = _clarify_pending(history)
    source = _source_from_text(question, numbered=numbered_now)
    if source:
        return source
    asked = _thread_asked_clarify(history)
    for m in reversed(history or []):
        if (m.get("role") or "") != "user":
            continue
        source = _source_from_text(m.get("content") or "", numbered=asked)
        if source:
            return source
        if len((m.get("content") or "").split()) > 12:
            continue
    return None


def needs_spend_clarify(question: str, history: list[dict] | None = None) -> bool:
    """Ask which source when a day/UPI question does not name ledger vs Gmail."""
    if resolve_spend_source(question, history):
        return False
    if _LEDGER_INTENT_RE.search(question or ""):
        return False
    for m in reversed(history or []):
        if (m.get("role") or "") != "assistant":
            continue
        if _CLARIFY_MARK in (m.get("content") or ""):
            return False
        break
    q = question or ""
    if wants_upi(q, history):
        return True
    if re.search(r"\b(trans?actions?|trasactions?|alerts?)\b", q, re.I):
        return True
    if re.search(r"\bany\b", q, re.I) and (_TODAY_RE.search(q) or _YESTERDAY_RE.search(q)):
        return True
    return False


def format_spend_clarify(day: str, question: str = "") -> str:
    try:
        label = datetime.strptime(day, "%Y-%m-%d").strftime("%A %d %B %Y")
    except ValueError:
        label = day
    topic = "UPI" if wants_upi(question) else "transactions"
    return (
        f"I can check **{topic}** for {label} in two places — they are not the same:\n\n"
        "1. **Money Manager (ledger)** — already posted as spend\n"
        "2. **Expense Analyser (Gmail)** — bank/UPI alerts still waiting in Inbox\n\n"
        f"{_CLARIFY_MARK} Reply **1**, **2**, **both**, **ledger**, or **gmail**."
    )


_ANALYSER_RE = re.compile(
    r"analy[sz]er|analayser|anlyser|gmail|inbox",
    re.I,
)
_RUPEE_AMT_RE = re.compile(
    r"(\d{1,3}(?:,\d{2,3})+(?:\.\d{1,2})?|\d{4,}(?:\.\d{1,2})?)",
)


def parse_question_amount(question: str) -> float | None:
    m = _RUPEE_AMT_RE.search(question or "")
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def wants_analyser_upi_breakdown(question: str) -> bool:
    q = question or ""
    if not _UPI_RE.search(q):
        return False
    if _ANALYSER_RE.search(q):
        return True
    if parse_question_amount(q) and re.search(r"\b(list|break\s*down|itemize|total)\b", q, re.I):
        return True
    return False


def format_analyser_upi_breakdown(db: Session, user: models.User, question: str = "") -> str:
    """Full Expense Analyser UPI list for the month — matches Insights category total."""
    from app.expense_analyser import insights, _item_day

    today = vault_now()
    months = detect_months(question, today) or [f"{today:%Y-%m}"]
    ym = months[0]
    report = insights(db, user, ym)
    asked = parse_question_amount(question)
    uid = _uid(user)
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
    month_rows = []
    for item in rows:
        day = _item_day(item)
        if day and day.startswith(ym) and (item.direction or "") != "credit":
            month_rows.append(item)

    def _is_cat_upi(it) -> bool:
        return "upi" in (it.suggested_category or "").lower()

    def _is_method_upi(it) -> bool:
        return (it.payment_method or "").lower() == "upi" or _looks_like_upi(
            it.payment_method, it.subject, it.raw_snippet,
        )

    cat_rows = [it for it in month_rows if _is_cat_upi(it)]
    method_rows = [it for it in month_rows if _is_method_upi(it)]
    cat_total = sum(abs(_f(it.amount)) for it in cat_rows)
    method_total = sum(abs(_f(it.amount)) for it in method_rows)
    label = report.get("label") or ym

    lines = [
        f"**Expense Analyser UPI for {label}** (live inbox, not Money Manager)",
        "",
    ]
    if asked and abs(asked - cat_total) < 1:
        lines.append(
            f"₹ {asked:,.2f} is the Insights **category total** for "
            f"**UPI / transfers** — it is the sum of **{len(cat_rows)}** debit alerts, not one payment."
        )
        lines.append("")
    lines.append(f"UPI / transfers (category): **{_inr(cat_total)}** · {len(cat_rows)} items")
    lines.append(f"UPI (payment method): **{_inr(method_total)}** · {len(method_rows)} items")
    if abs(cat_total - method_total) >= 1:
        lines.append(
            "Those two numbers differ when a card/ATM/netbanking alert is tagged "
            "“UPI / transfers”. Insights uses the **category** figure."
        )
    lines.append("")

    show = sorted(cat_rows, key=lambda it: abs(_f(it.amount)), reverse=True)
    if not show:
        show = sorted(method_rows, key=lambda it: abs(_f(it.amount)), reverse=True)
    if not show:
        lines.append("No UPI-tagged debit alerts in this month.")
        return "\n".join(lines)

    lines.append("| Date | Status | Payee | Method | Amount |")
    lines.append("| --- | --- | --- | --- | ---: |")
    running = 0.0
    extra = 0
    extra_sum = 0.0
    for i, it in enumerate(show):
        amt = abs(_f(it.amount))
        if i >= 80:
            extra += 1
            extra_sum += amt
            continue
        running += amt
        lines.append(
            f"| {it.txn_date or '—'} | {it.status or 'pending'} | "
            f"{it.payee or it.subject or '—'} | "
            f"{(it.payment_method or '—').replace('_', ' ')} | {_inr(it.amount).replace('₹ ', '')} |"
        )
    if extra:
        lines.append(f"| | | _{extra} more_ | | {_inr(extra_sum).replace('₹ ', '')} |")
        running += extra_sum
    lines.append(f"| | | **Listed total** | | **{_inr(running).replace('₹ ', '')}** |")
    lines.append("")
    lines.append("_Source: Expense Analyser inbox. Ignored rows and credits are excluded, same as Insights._")
    return "\n".join(lines)


def wants_upi(question: str, history: list[dict] | None = None) -> bool:
    if _UPI_RE.search(question or ""):
        return True
    for m in reversed(history or []):
        if (m.get("role") or "") != "user":
            continue
        if _UPI_RE.search(m.get("content") or ""):
            return True
        break
    return False


def _looks_like_upi(*parts: str | None) -> bool:
    hay = " ".join(p or "" for p in parts).lower()
    return bool(_UPI_RE.search(hay))


def format_money_manager_day_reply(
    db: Session,
    user: models.User,
    day: str,
    question: str = "",
    history: list[dict] | None = None,
    source: str | None = None,
) -> str:
    """Deterministic day spend: Money Manager ledger, plus unposted Gmail alerts."""
    uid = _uid(user)
    source = source or resolve_spend_source(question, history) or "both"
    show_ledger = source in ("ledger", "both")
    show_ea = source in ("analyser", "both")
    upi_only = wants_upi(question, history)
    cats = {
        c.id: c.name
        for c in db.query(models.FinanceCategory).filter(models.FinanceCategory.user_id == uid).all()
    }
    acct_by_id = {
        a.id: a
        for a in db.query(models.FinanceAccount).filter(models.FinanceAccount.user_id == uid).all()
    }
    txns = (
        db.query(models.FinanceTransaction)
        .filter(
            models.FinanceTransaction.user_id == uid,
            models.FinanceTransaction.deleted_at.is_(None),
            models.FinanceTransaction.txn_date == day,
            models.FinanceTransaction.txn_type == "expense",
        )
        .order_by(models.FinanceTransaction.created_at.desc())
        .all()
    )
    if upi_only:
        txns = [
            t for t in txns
            if _looks_like_upi(t.payment_method, t.payee, t.notes, getattr(t, "description", None))
        ]
    if not show_ledger:
        txns = []
    total = sum(_f(t.amount) for t in txns)
    try:
        label = datetime.strptime(day, "%Y-%m-%d").strftime("%A %d %B %Y")
    except ValueError:
        label = day
    topic = "UPI" if upi_only else "expenses"
    lines: list[str] = []
    if show_ledger:
        lines.extend([
            f"**Money Manager {topic} for {label}**",
            "",
            f"Ledger total: **{_inr(total)}**",
            "",
        ])
        if not txns:
            lines.append("No matching expense entries on the Money Manager ledger for this date.")
            lines.append("")
        else:
            lines.append("| Payee | Category | Account | Amount |")
            lines.append("| --- | --- | --- | ---: |")
            for t in txns:
                acct = acct_by_id.get(t.account_id)
                lines.append(
                    f"| {t.payee or '—'} | {cats.get(t.category_id) or '—'} | "
                    f"{acct.name if acct else '—'} | {_inr(t.amount).replace('₹ ', '')} |"
                )
            lines.append("")

    ea_rows = (
        db.query(models.ExpenseAnalyserItem)
        .filter(
            models.ExpenseAnalyserItem.user_id == uid,
            models.ExpenseAnalyserItem.txn_date == day,
            models.ExpenseAnalyserItem.status.notin_(("posted", "ignored")),
            models.ExpenseAnalyserItem.kind.in_(("alert", "bill_line")),
        )
        .order_by(models.ExpenseAnalyserItem.created_at.desc())
        .all()
    )
    if upi_only:
        ea_rows = [
            it for it in ea_rows
            if _looks_like_upi(it.payment_method, it.subject, it.raw_snippet, it.from_addr)
        ]
    if not show_ea:
        ea_rows = []
    if ea_rows:
        ea_total = sum(abs(_f(it.amount)) for it in ea_rows if it.amount is not None)
        if source == "analyser":
            lines.extend([
                f"**Expense Analyser {topic} for {label}** (live Gmail inbox)",
                "",
                f"Total: **{_inr(ea_total)}** · {len(ea_rows)} alert(s), not posted to Money Manager yet.",
                "",
            ])
        else:
            lines.append("**Expense Analyser — Gmail alerts not yet on the ledger**")
            lines.append("")
            lines.append(f"Inbox total: **{_inr(ea_total)}** · {len(ea_rows)} item(s) still pending review.")
            lines.append("")
        lines.append("| Status | Payee | Method | Amount |")
        lines.append("| --- | --- | --- | ---: |")
        for it in ea_rows[:25]:
            lines.append(
                f"| {it.status or 'pending'} | {it.payee or it.subject or '—'} | "
                f"{(it.payment_method or '—').replace('_', ' ')} | "
                f"{_inr(it.amount).replace('₹ ', '') if it.amount is not None else '—'} |"
            )
        lines.append("")
        lines.append("These are in Expense Analyser Inbox — post them to Money Manager if they should count as spend.")
        lines.append("")
    elif show_ea and not txns:
        lines.append("No matching Gmail alerts in Expense Analyser for this date either.")
        lines.append("")

    lines.append("_Ledger source: Money Manager. Unposted mail: Expense Analyser. Digital Diary is not counted._")
    return "\n".join(lines)


def wants_highest_expense(question: str) -> bool:
    q = (question or "").strip()
    if not q:
        return False
    if not _HIGHEST_RE.search(q):
        return False
    return bool(_PURCHASE_RE.search(q) or re.search(r"\b(item|purchase|purchases)\b", q, re.I))


def should_answer_highest_expense(
    question: str,
    history: list[dict] | None = None,
) -> bool:
    if wants_highest_expense(question):
        return True
    if not _FOLLOWUP_RE.search(question or ""):
        return False
    for m in reversed(history or []):
        if (m.get("role") or "") != "user":
            continue
        if wants_highest_expense(m.get("content") or ""):
            return True
        break
    return False


def format_highest_expense_reply(db: Session, user: models.User, question: str = "") -> str:
    """Largest Money Manager expense in the asked months — never Shopping List or diary."""
    uid = _uid(user)
    today = vault_now()
    months = detect_months(question, today) or [f"{today:%Y-%m}"]
    starts = [_month_bounds(ym)[0] for ym in months]
    ends = [_month_bounds(ym)[1] for ym in months]
    cats = {
        c.id: c.name
        for c in db.query(models.FinanceCategory).filter(models.FinanceCategory.user_id == uid).all()
    }
    accts = {
        a.id: a.name
        for a in db.query(models.FinanceAccount).filter(models.FinanceAccount.user_id == uid).all()
    }
    rows = (
        db.query(models.FinanceTransaction)
        .filter(
            models.FinanceTransaction.user_id == uid,
            models.FinanceTransaction.deleted_at.is_(None),
            models.FinanceTransaction.txn_type == "expense",
            models.FinanceTransaction.txn_date >= min(starts),
            models.FinanceTransaction.txn_date <= max(ends),
        )
        .order_by(models.FinanceTransaction.amount.desc(), models.FinanceTransaction.txn_date.desc())
        .limit(5)
        .all()
    )
    window = ", ".join(
        datetime.strptime(ym + "-01", "%Y-%m-%d").strftime("%b %Y") for ym in months
    )
    lines = [
        f"**Largest Money Manager expense ({window})**",
        "",
    ]
    if not rows:
        lines.append("There is no expense on the Money Manager ledger in this window.")
        lines.append("Open Money Manager → Transactions to add one.")
        lines.append("")
        lines.append("_Source: Money Manager ledger (not Shopping List, not Digital Diary)._")
        return "\n".join(lines)
    top = rows[0]
    title = (top.payee or "").strip() or cats.get(top.category_id) or "Expense"
    lines.append(f"**{title}** · **{_inr(top.amount)}**")
    lines.append(f"- Date: {top.txn_date}")
    lines.append(f"- Category: {cats.get(top.category_id) or '—'}")
    lines.append(f"- Account: {accts.get(top.account_id) or '—'}")
    if top.payment_method:
        lines.append(f"- Paid by: {top.payment_method.replace('_', ' ')}")
    if top.description and top.payee and top.description != top.payee:
        lines.append(f"- Note: {top.description}")
    if len(rows) > 1:
        lines.append("")
        lines.append("Next largest:")
        for t in rows[1:]:
            name = (t.payee or "").strip() or cats.get(t.category_id) or "Expense"
            lines.append(f"- {t.txn_date} · {name} · {_inr(t.amount)}")
    lines.append("")
    lines.append("_Source: Money Manager ledger. Payee is the item title; category is only a tag._")
    return "\n".join(lines)


_PASSWORD_ASK_RE = re.compile(
    r"\b(password|passwd|pwd|passcode|login|logins|credential|credentials|"
    r"username|user\s*id|userid)\b",
    re.I,
)
_HEALTH_ASK_RE = re.compile(
    r"\b(medical|health|hospital|lab|labs|report|reports|prescription|"
    r"scan|x-?ray|blood|allergy|allergies|vaccine|vaccination|doctor|dr\.?|"
    r"gynae|gyne|paediat|pedia|specialist)\b",
    re.I,
)
_LOCKER_ASK_RE = re.compile(
    r"\b(aadhaar|aadhar|pan|passport|license|licence|id\s*card|locker|"
    r"document vault|driving)\b",
    re.I,
)
_NEEDLE_STOP_RE = re.compile(
    r"\b(what|whats|what's|which|where|is|are|my|the|a|an|for|of|to|please|"
    r"show|tell|give|me|find|open|view|see|stored|saved|vault|"
    r"password|passwd|pwd|passcode|login|logins|credential|credentials|"
    r"username|medical|health|hospital|lab|report|reports|prescription|document|"
    r"documents|card|number|id|any)\b",
    re.I,
)


def _search_needle(question: str) -> str:
    cleaned = re.sub(r"[^\w\u0d00-\u0d7f]+", " ", question or "", flags=re.UNICODE)
    cleaned = _NEEDLE_STOP_RE.sub(" ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _tokens_match(hay: str, needle: str) -> bool:
    hay = (hay or "").lower()
    fillers = {"have", "has", "had", "with", "from", "about", "this", "that", "does", "did", "any"}
    tokens = [
        t for t in (needle or "").lower().split()
        if len(t) >= 3 and t not in fillers
    ]
    if not tokens:
        return False
    if all(t in hay for t in tokens):
        return True
    return any(len(t) >= 4 and t in hay for t in tokens)


def wants_password_lookup(question: str) -> bool:
    q = (question or "").strip()
    if not q:
        return False
    return bool(_PASSWORD_ASK_RE.search(q))


def wants_health_lookup(question: str) -> bool:
    q = (question or "").strip()
    if not q:
        return False
    if wants_password_lookup(q) or _SPEND_RE.search(q):
        return False
    return bool(_HEALTH_ASK_RE.search(q))


def wants_locker_lookup(question: str) -> bool:
    q = (question or "").strip()
    if not q:
        return False
    if wants_password_lookup(q) or _SPEND_RE.search(q):
        return False
    return bool(_LOCKER_ASK_RE.search(q))


def format_password_lookup_reply(db: Session, user: models.User, question: str) -> str:
    """Local Password Vault links — secrets never leave this server."""
    uid = _uid(user)
    items = (
        db.query(models.VaultItem)
        .filter(models.VaultItem.user_id == uid, models.VaultItem.deleted_at.is_(None))
        .order_by(models.VaultItem.name)
        .all()
    )
    needle = _search_needle(question)
    hits = []
    for it in items:
        hay = " ".join([it.name or "", it.item_type or "", it.uris or ""])
        if needle and _tokens_match(hay, needle):
            hits.append(it)
        elif needle and needle.lower() in hay.lower():
            hits.append(it)
    if needle and not hits:
        hits = [
            it for it in items
            if any(t in " ".join([it.name or "", it.uris or ""]).lower()
                   for t in needle.lower().split() if len(t) >= 3)
        ]
    lines = [
        "**Password Vault**",
        "",
        "The password stays on this server. It is **not** sent to the AI provider.",
        "Open the login here to view or copy it:",
        "",
    ]
    shown = hits[:12] if needle else items[:8]
    if not items:
        lines.append("No logins saved yet. Open [Password Vault](/admin/passwords) to add one.")
        return "\n".join(lines)
    if needle and not shown:
        lines.append(f"No login matched **{needle}**.")
        lines.append("Open [Password Vault](/admin/passwords) to browse.")
        return "\n".join(lines)
    for it in shown:
        kind = (it.item_type or "login").replace("_", " ")
        lines.append(f"- [{it.name}](/admin/passwords/{it.id}) · {kind}")
    if not needle and len(items) > 8:
        lines.append(f"- …and {len(items) - 8} more in [Password Vault](/admin/passwords)")
    return "\n".join(lines)


def format_health_lookup_reply(db: Session, user: models.User, question: str) -> str:
    """Local Health Vault links — reports never go to the AI provider."""
    uid = _uid(user)
    people = (
        db.query(models.Person)
        .filter(models.Person.user_id == uid)
        .all()
    )
    pids = [p.id for p in people]
    person_name = {p.id: p.name for p in people}
    needle = _search_needle(question)
    lines = [
        "**Health Vault**",
        "",
        "Medical records stay on this server. They are **not** sent to the AI provider.",
        "",
    ]
    if re.search(r"\b(doctor|dr\.?|gynae|gyne|paediat|pedia|specialist|phone|number)\b", question or "", re.I):
        doctors = (
            db.query(models.Doctor)
            .filter(models.Doctor.user_id == uid)
            .order_by(models.Doctor.name)
            .all()
        )
        matched = []
        for d in doctors:
            hay = " ".join(x for x in [d.name, d.specialty, d.hospital_name, d.notes] if x)
            if not needle or _tokens_match(hay, needle) or needle.lower() in hay.lower():
                matched.append(d)
        if matched:
            lines.append("Doctors (open Health Vault to edit):")
            for d in matched[:12]:
                phone = f" · {d.phone}" if d.phone else ""
                lines.append(
                    f"- {d.name} · {d.specialty or '—'} · {d.hospital_name or '—'}{phone}"
                )
            lines.append("")
            lines.append("[Open Doctors](/admin/doctors)")
            return "\n".join(lines)
        lines.append("No matching doctor in the directory.")
        lines.append("[Open Doctors](/admin/doctors)")
        return "\n".join(lines)

    if not pids:
        lines.append("No family profiles yet. [Open Health Vault](/admin)")
        return "\n".join(lines)
    docs = (
        db.query(models.Document)
        .filter(
            models.Document.person_id.in_(pids),
            models.Document.deleted_at.is_(None),
        )
        .order_by(models.Document.doc_date.desc(), models.Document.created_at.desc())
        .limit(80)
        .all()
    )
    hits = []
    for d in docs:
        hay = " ".join([
            d.title or "", d.hospital_name or "", _enum(d.category) or "",
            d.custom_category or "", person_name.get(d.person_id, ""),
        ])
        if not needle or _tokens_match(hay, needle) or needle.lower() in hay.lower():
            hits.append(d)
    shown = hits[:12] if needle else docs[:8]
    if not shown:
        lines.append("No matching health document.")
        lines.append("[Open Health Vault](/admin)")
        return "\n".join(lines)
    lines.append("Open the record to view it (nothing below is sent off-server):")
    for d in shown:
        who = person_name.get(d.person_id, "")
        title = d.title or "Document"
        lines.append(
            f"- [{title}](/admin/documents/{d.id}) · {who} · "
            f"{d.hospital_name or '—'} · {d.doc_date or 'undated'}"
        )
    lines.append("")
    lines.append("[All documents](/admin)")
    return "\n".join(lines)


def format_locker_lookup_reply(db: Session, user: models.User, question: str) -> str:
    """Local Document Vault (locker) links — ID numbers stay on this server."""
    uid = _uid(user)
    items = (
        db.query(models.LockerItem)
        .filter(models.LockerItem.user_id == uid)
        .order_by(models.LockerItem.title)
        .all()
    )
    needle = _search_needle(question)
    hits = []
    for it in items:
        hay = " ".join([it.title or "", it.doc_type or "", it.custom_type or "", it.holder_name or ""])
        if not needle or _tokens_match(hay, needle) or needle.lower() in hay.lower():
            hits.append(it)
    shown = hits[:12] if needle else items[:8]
    lines = [
        "**Document Vault**",
        "",
        "ID numbers stay on this server. They are **not** sent to the AI provider.",
        "Open the document here:",
        "",
    ]
    if not items:
        lines.append("No locker documents yet. [Open Document Vault](/admin/locker)")
        return "\n".join(lines)
    if needle and not shown:
        lines.append(f"No document matched **{needle}**.")
        lines.append("[Open Document Vault](/admin/locker)")
        return "\n".join(lines)
    for it in shown:
        lines.append(
            f"- [{it.title}](/admin/locker/{it.id}) · "
            f"{(it.doc_type or '').replace('_', ' ')}"
            + (f" · expiry {it.expiry_date}" if it.expiry_date else "")
        )
    return "\n".join(lines)


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
        today = vault_now()
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
    """YYYY-MM values mentioned or implied in the question (English + common Manglish)."""
    today = today or vault_now()
    this = f"{today:%Y-%m}"
    q = (question or "").lower()
    # Fold Malayalam virama so script forms match more easily in regex-less checks later
    q_flat = q.replace("\u0d4d", "")
    found: list[str] = []
    if re.search(r"\b(this month|current month)\b", q):
        found.append(this)
    if re.search(r"\b(ee\s*maasam|ee\s*masam|ippo[l]?athe?\s*maasam)\b", q):
        found.append(this)
    if re.search(r"\blast month\b", q):
        found.append(_shift_month(this, -1))
    # Manglish / Malayalam: kazhinja maasam, korsa maasam, കഴിഞ്ഞ മാസം
    if re.search(
        r"\b(kazhinja|kazinja|kors[a]?|poyi)\s*maa?sam\b|"
        r"കഴിഞ്ഞ\s*മാസ|കഴിഞ്ഞമാസ",
        q_flat,
    ):
        found.append(_shift_month(this, -1))
    # last/past N months (including “two” / Manglish randu/moonnu maasam)
    span = None
    m = re.search(r"\b(?:last|past)\s+(\d{1,2})\s+months?\b", q)
    if m:
        span = max(1, min(12, int(m.group(1))))
    elif re.search(r"\b(?:last|past)\s+two\s+months?\b", q):
        span = 2
    elif re.search(r"\b(?:last|past)\s+three\s+months?\b", q):
        span = 3
    elif re.search(r"\b(randu|rendu|2)\s*maa?sam\b|രണ്ട്?\s*മാസ", q_flat):
        span = 2
    elif re.search(r"\b(moonnu|munnu|3)\s*maa?sam\b|മൂന്ന്?\s*മാസ", q_flat):
        span = 3
    elif re.search(r"\b(naalu|nalu|4)\s*maa?sam\b|നാല്?\s*മാസ", q_flat):
        span = 4
    if span:
        for i in range(1, span + 1):
            found.append(_shift_month(this, -i))
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


def _manglish_query_hints(question: str) -> list[str]:
    """Map Manglish / Malayalam tokens in the question to English grocery names."""
    from app.grocery import SEED_KEYS, _all_catalog, _fold

    q = question or ""
    q_fold = _fold(q)
    if len(q_fold) < 3 and not re.search(r"[\u0d00-\u0d7f]", q):
        return []
    hits: list[str] = []
    seen: set[str] = set()

    # Prefer longer Manglish keys first so "pachamulaku" wins over "mulaku"
    for key, english in sorted(SEED_KEYS.items(), key=lambda kv: -len(kv[0])):
        kf = _fold(key)
        if len(kf) < 3:
            continue
        matched = False
        if re.search(rf"\b{re.escape(key)}\b", q, re.I):
            matched = True
        elif len(kf) >= 5 and kf in q_fold:
            matched = True
        if matched:
            line = f"{key} → {english}"
            if line not in seen:
                seen.add(line)
                hits.append(line)

    for row in _all_catalog():
        en = row.get("english") or ""
        ml = row.get("malayalam") or ""
        if ml and ml in q:
            line = f"{ml} → {en}"
            if line not in seen:
                seen.add(line)
                hits.append(line)
        en_fold = _fold(en)
        if len(en_fold) >= 4 and en_fold in q_fold:
            line = f"{en} (catalog)"
            if line not in seen:
                seen.add(line)
                hits.append(line)
    return hits[:40]


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
                    models.Document.deleted_at.is_(None),
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

    doctor_n = (
        db.query(models.Doctor)
        .filter(models.Doctor.user_id == uid)
        .count()
    )
    if doctor_n:
        hints.append({
            "label": "Find a doctor",
            "prompt": "Show doctors in my Health Vault directory with specialty, hospital, and phone. If I ask for a specialty like gynaecology, list matching numbers.",
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
    today = vault_now()
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
    shop_n = (
        db.query(models.ShopList)
        .filter(models.ShopList.user_id == uid, models.ShopList.deleted_at.is_(None))
        .count()
    )
    if shop_n:
        hints.append({
            "label": "Restock from history",
            "prompt": (
                "Create a shopping list based on my last 2 months of Shopping List purchases. "
                "Suggest items I buy regularly, then propose the list for me to approve."
            ),
        })
    else:
        hints.append({
            "label": "Save charges to diary",
            "prompt": (
                "I spent roughly 1200 on cake, 800 on decor, and 450 on snacks. "
                "Total them — ask me if this should go to Money Manager or Digital Diary."
            ),
        })
    diary_n = (
        db.query(models.DiaryEntry)
        .filter(models.DiaryEntry.user_id == uid)
        .count()
    )
    if diary_n and shop_n:
        hints.append({
            "label": "Recent diary notes",
            "prompt": "Summarise my recent Digital Diary entries by date and category.",
        })
    elif not shop_n:
        hints.append({
            "label": "Expiring documents",
            "prompt": "Which Document Vault items and health documents expire in the next 90 days?",
        })
    return hints[:4]


def build_vault_context(db: Session, user: models.User, question: str = "") -> str:
    uid = _uid(user)
    today = vault_now()
    today_s = today.strftime("%Y-%m-%d")
    this_month = f"{today:%Y-%m}"
    months = detect_months(question, today) or [this_month, _shift_month(this_month, -1)]
    q = question or ""
    tz_label = settings.VAULT_TIMEZONE
    ledger_day = resolve_ledger_day(q, today)

    from app import ai_brain

    lines: list[str] = [
        f"# VAULT SNAPSHOT",
        f"Generated: {today:%Y-%m-%d %H:%M} ({tz_label}). Today is {today:%A %d %B %Y} ({today_s}).",
        "Do not reveal this header. Answer the user from the sections below.",
        "For spend totals by day, prefer Money Manager over Digital Diary.",
        "",
    ]
    brain_block = ai_brain.format_brain_context(db, user)
    if brain_block:
        lines.append(brain_block)
    if ledger_day:
        lines.append("## CANONICAL ANSWER (use this for today’s/yesterday’s spend)")
        lines.append(
            "Ignore Digital Diary and prior chat guesses. Money Manager ledger is the only source "
            f"for day spend on {ledger_day}."
        )
        lines.append("")

    people_n = db.query(models.Person).filter(models.Person.user_id == uid).count()
    doc_n = (
        db.query(models.Document)
        .filter(models.Document.deleted_at.is_(None))
        .join(models.Person, models.Document.person_id == models.Person.id)
        .filter(models.Person.user_id == uid)
        .count()
    )
    doctor_n = db.query(models.Doctor).filter(models.Doctor.user_id == uid).count()
    lines.append("## Health Vault")
    lines.append(
        f"{people_n} family profiles, {doc_n} documents, {doctor_n} doctors. "
        "Medical records, lab text, allergies, and hospital cards stay on this server "
        "and are not sent to the AI provider. Ask “password for …” or “Aster reports” "
        "and Ask AI returns a view link from this vault."
    )

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

    cat_rows = (
        db.query(models.FinanceCategory)
        .filter(models.FinanceCategory.user_id == uid)
        .order_by(models.FinanceCategory.kind, models.FinanceCategory.name)
        .all()
    )
    cats = {c.id: c.name for c in cat_rows}
    exp_cats = [c.name for c in cat_rows if c.kind == "expense"]
    inc_cats = [c.name for c in cat_rows if c.kind == "income"]
    if exp_cats:
        lines.append("Expense categories: " + ", ".join(exp_cats[:40]))
    if inc_cats:
        lines.append("Income categories: " + ", ".join(inc_cats[:20]))
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

    # Explicit calendar-day ledger (fixes “today’s expense” vs diary / UTC drift).
    today_txns = (
        db.query(models.FinanceTransaction)
        .filter(
            models.FinanceTransaction.user_id == uid,
            models.FinanceTransaction.deleted_at.is_(None),
            models.FinanceTransaction.txn_date == today_s,
        )
        .order_by(models.FinanceTransaction.created_at.desc())
        .all()
    )
    today_exp = sum(_f(t.amount) for t in today_txns if t.txn_type == "expense")
    today_inc = sum(_f(t.amount) for t in today_txns if t.txn_type == "income")
    lines.append(
        f"Today (Money Manager) {today_s}: expense {_inr(today_exp)}, income {_inr(today_inc)}, "
        f"{len(today_txns)} entries."
    )
    if today_txns:
        lines.append(f"Today's Money Manager transactions ({today_s}):")
        for t in today_txns:
            acct = acct_by_id.get(t.account_id)
            lines.append(
                f"- {t.txn_date} · {acct.name if acct else '?'} · {t.txn_type} · "
                f"{_inr(t.amount)} · {t.payee or '—'} · {cats.get(t.category_id) or '—'} · "
                f"{t.payment_method or ''}"
            )
    else:
        lines.append(f"No Money Manager ledger entries dated {today_s}.")

    for ym in months:
        start, end = _month_bounds(ym)
        txns = (
            db.query(models.FinanceTransaction)
            .filter(
                models.FinanceTransaction.user_id == uid,
                models.FinanceTransaction.deleted_at.is_(None),
                models.FinanceTransaction.txn_date >= start,
                models.FinanceTransaction.txn_date <= end,
            )
            .order_by(models.FinanceTransaction.txn_date.desc(), models.FinanceTransaction.created_at.desc())
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
        cap = 80 if hit_acct_ids else 40
        if list_txns:
            label = "matched account(s)" if hit_acct_ids else "recent sample"
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
        try:
            from app.expense_analyser import insights as ea_insights
            ins = ea_insights(db, user, this_month)
            lines.append(
                f"Insights {ins.get('label') or this_month}: debit {_inr(ins.get('debit_total'))} "
                f"across {ins.get('item_count') or 0} inbox items (not ledger)."
            )
            cats = ins.get("by_category") or []
            if cats:
                lines.append(
                    "Insights by category: "
                    + ", ".join(f"{c['name']} {_inr(c['amount'])} ({c.get('count') or 0})" for c in cats[:8])
                )
            methods = ins.get("by_method") or []
            if methods:
                lines.append(
                    "Insights by method: "
                    + ", ".join(f"{m['name']} {_inr(m['amount'])} ({m.get('count') or 0})" for m in methods[:6])
                )
        except Exception:
            pass
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

    # ---- Shopping List ----
    lines.append("")
    lines.append("## Shopping List")
    manglish_hits = _manglish_query_hints(q)
    if manglish_hits:
        lines.append("Manglish / Malayalam grocery hints from this question:")
        for h in manglish_hits:
            lines.append(f"- {h}")
    lines.extend(_shopping_snapshot_lines(db, uid, months, today, q))
    # Compact glossary so the model can resolve common Manglish even when not in the question
    from app.grocery import SEED_KEYS
    gloss = sorted({f"{k}={v}" for k, v in SEED_KEYS.items()}, key=lambda s: s.lower())
    lines.append("Manglish grocery glossary (subset): " + ", ".join(gloss[:80]))

    # ---- Digital Diary ----
    lines.append("")
    lines.append("## Digital Diary")
    if ledger_day:
        lines.append(
            f"Omitted for this question — user asked about Money Manager day spend ({ledger_day})."
        )
    else:
        lines.append(
            "Journal notes only — diary charge tables are not Money Manager ledger spend. "
            "Do not use diary amounts for “today’s expense” unless the user asked about the diary."
        )
        lines.extend(_diary_snapshot_lines(db, uid, q))

    # ---- Locker (counts only — IDs never leave this server) ----
    locker_n = db.query(models.LockerItem).filter(models.LockerItem.user_id == uid).count()
    lines.append("")
    lines.append(
        f"## Document Vault: {locker_n} ID/paper items. Titles and ID numbers stay on this "
        "server and are not sent to the AI provider. Ask for an ID document to get a view link."
    )

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

    # ---- Passwords (count only — names and secrets never leave this server) ----
    pw_n = (
        db.query(models.VaultItem)
        .filter(models.VaultItem.user_id == uid, models.VaultItem.deleted_at.is_(None))
        .count()
    )
    lines.append("")
    lines.append(
        f"## Password Vault: {pw_n} items. Login names and passwords stay on this server "
        "and are not sent to the AI provider. Ask “password for Gmail” to get a view link."
    )

    text = "\n".join(lines)
    if len(text) > MAX_CONTEXT_CHARS:
        text = text[: MAX_CONTEXT_CHARS - 20] + "\n… [truncated]"
    return text


def _item_when(item: models.ShopItem, lst: models.ShopList) -> datetime | None:
    if item.checked and item.updated_at:
        return item.updated_at
    if lst.completed_at:
        return lst.completed_at
    return item.created_at or lst.created_at or item.updated_at


def _ym(dt: datetime | None) -> str:
    if not dt:
        return ""
    return f"{dt:%Y-%m}"


def _shopping_snapshot_lines(
    db: Session,
    uid: str,
    months: list[str],
    today: datetime,
    question: str,
) -> list[str]:
    lines: list[str] = []
    lists = (
        db.query(models.ShopList)
        .filter(models.ShopList.user_id == uid, models.ShopList.deleted_at.is_(None))
        .order_by(models.ShopList.updated_at.desc())
        .limit(40)
        .all()
    )
    if not lists:
        lines.append("No shopping lists yet.")
        return lines

    month_set = set(months or [])
    if not month_set:
        month_set = {f"{today:%Y-%m}", _shift_month(f"{today:%Y-%m}", -1)}

    open_lists = [lst for lst in lists if not lst.completed][:12]
    lines.append(f"Active lists ({len([l for l in lists if not l.completed])} open / {len(lists)} total):")
    if open_lists:
        for lst in open_lists:
            items = [i for i in (lst.items or []) if (i.status or "approved") != "rejected"]
            checked = sum(1 for i in items if i.checked)
            names = ", ".join((i.name or "")[:40] for i in items[:12]) or "(empty)"
            more = f" +{len(items) - 12} more" if len(items) > 12 else ""
            lines.append(
                f"- {lst.name} · {checked}/{len(items)} checked · created "
                f"{lst.created_at.strftime('%Y-%m-%d') if lst.created_at else '—'} · items: {names}{more}"
            )
    else:
        lines.append("- (none open)")

    # Purchased / checked items in focus months
    freq: dict[str, dict] = {}
    month_hits: list[str] = []
    for lst in lists:
        for item in lst.items or []:
            if (item.status or "approved") == "rejected":
                continue
            if not item.checked and not lst.completed:
                continue
            when = _item_when(item, lst)
            ym = _ym(when)
            if ym and ym not in month_set:
                continue
            key = (item.name or "").strip()
            if not key:
                continue
            slot = freq.setdefault(key.lower(), {
                "name": key, "count": 0, "category": item.category, "dates": [],
            })
            slot["count"] += 1
            if ym and ym not in slot["dates"]:
                slot["dates"].append(ym)
            day = when.strftime("%Y-%m-%d") if when else ""
            if day:
                month_hits.append(
                    f"- {day} · {key}"
                    + (f" · {item.category}" if item.category else "")
                    + f" · list {lst.name}"
                    + (" · checked" if item.checked else " · on completed list")
                )

    lines.append(
        f"Purchased/checked grocery items in months {', '.join(sorted(month_set))} "
        f"(date ≈ check/complete time):"
    )
    if month_hits:
        for row in month_hits[:80]:
            lines.append(row)
    else:
        lines.append("- none recorded in those months")

    if freq:
        top = sorted(freq.values(), key=lambda r: (-r["count"], r["name"].lower()))[:30]
        lines.append("Most frequent purchased items in that window (for restock suggestions):")
        for row in top:
            lines.append(
                f"- {row['name']} ×{row['count']}"
                + (f" · {row['category']}" if row.get("category") else "")
                + (f" · months {', '.join(sorted(row['dates']))}" if row.get("dates") else "")
            )

    # Recent list names for “which lists do I have”
    done = [lst for lst in lists if lst.completed][:8]
    if done:
        lines.append("Recently completed lists:")
        for lst in done:
            when = lst.completed_at or lst.updated_at
            lines.append(
                f"- {lst.name} · completed "
                f"{when.strftime('%Y-%m-%d') if when else '—'} · "
                f"{len(lst.items or [])} items"
            )
    return lines


def _diary_snapshot_lines(db: Session, uid: str, question: str = "") -> list[str]:
    lines: list[str] = []
    cats = (
        db.query(models.DiaryCategory)
        .filter(models.DiaryCategory.user_id == uid)
        .order_by(models.DiaryCategory.sort_order, models.DiaryCategory.name)
        .all()
    )
    if cats:
        lines.append("Folders: " + ", ".join(c.name for c in cats))
    else:
        lines.append(
            "Folders: Personal, Work, Travel, Health, Family, Ideas, Other "
            "(defaults are created when the diary is first opened)"
        )

    entries = (
        db.query(models.DiaryEntry)
        .filter(models.DiaryEntry.user_id == uid)
        .order_by(
            models.DiaryEntry.pinned.desc(),
            models.DiaryEntry.entry_date.desc(),
            models.DiaryEntry.created_at.desc(),
        )
        .limit(40)
        .all()
    )
    if not entries:
        lines.append("No diary entries yet.")
        return lines

    q = (question or "").casefold().strip()
    lines.append(f"Recent entries ({min(len(entries), 30)} shown):")
    shown = 0
    for e in entries:
        cat = e.category.name if e.category else "—"
        body = crypto.decrypt_text(e.body_enc) or ""
        hay = " ".join([e.title or "", cat, e.tags or "", e.mood or "", body]).casefold()
        if q and len(q) >= 3 and q not in hay and shown >= 15:
            continue
        pin = " · pinned" if e.pinned else ""
        lines.append(
            f"- {e.entry_date or 'undated'} · {e.title} · {cat}"
            f"{' · tags ' + e.tags if e.tags else ''}"
            f"{' · mood ' + e.mood if e.mood else ''}{pin}"
        )
        # Diary body stays on this server — titles only go to the provider.
        shown += 1
        if shown >= 30:
            break
    return lines


def format_diary_charges_table(charges: list[dict], preface: str | None = None) -> str:
    """Build markdown table with Item / Amount / Total for diary bodies."""
    parts: list[str] = []
    note = (preface or "").strip()
    if note:
        parts.append(note)
        parts.append("")
    parts.append("| Item | Amount (₹) |")
    parts.append("| --- | ---: |")
    total = 0.0
    for raw in charges:
        if not isinstance(raw, dict):
            continue
        label = re.sub(r"\s+", " ", str(raw.get("label") or raw.get("name") or "")).strip()[:120]
        if not label:
            continue
        amt = _f(raw.get("amount"))
        total += amt
        # Keep numeric cell clean for alignment; currency in header.
        cell = f"{amt:,.2f}"
        parts.append(f"| {label} | {cell} |")
    parts.append(f"| **Total** | **{total:,.2f}** |")
    return "\n".join(parts)


def extract_vault_action(text: str) -> tuple[str, dict | None]:
    """Split assistant reply into display text + optional vault action."""
    raw = text or ""
    m = _VAULT_ACTION_RE.search(raw)
    if not m:
        return raw.strip(), None
    try:
        data = json.loads(m.group(1))
    except (TypeError, json.JSONDecodeError):
        return raw.strip(), None
    cleaned = _VAULT_ACTION_RE.sub("", raw).strip()
    action = normalize_vault_action(data)
    return cleaned, action


def normalize_vault_action(data: dict | None) -> dict | None:
    if not isinstance(data, dict):
        return None
    kind = (data.get("type") or "").strip()
    if kind == "create_shop_list":
        return normalize_shop_list_action(data)
    if kind == "create_diary_entry":
        return normalize_diary_entry_action(data)
    if kind == "create_diary_folder":
        return normalize_diary_folder_action(data)
    if kind == "create_finance_txn":
        return normalize_finance_txn_action(data)
    return None


def normalize_shop_list_action(data: dict | None) -> dict | None:
    if not isinstance(data, dict):
        return None
    if (data.get("type") or "") != "create_shop_list":
        return None
    name = re.sub(r"\s+", " ", str(data.get("name") or "Shopping list")).strip()[:120]
    if not name:
        name = "Shopping list"
    items_in = data.get("items") if isinstance(data.get("items"), list) else []
    items: list[dict] = []
    seen: set[str] = set()
    for raw in items_in[:60]:
        if isinstance(raw, str):
            raw = {"name": raw}
        if not isinstance(raw, dict):
            continue
        label = re.sub(r"\s+", " ", str(raw.get("name") or "")).strip()[:255]
        if not label:
            continue
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        qty = raw.get("quantity", 1)
        try:
            qty_f = float(qty if qty not in (None, "") else 1)
        except (TypeError, ValueError):
            qty_f = 1.0
        if qty_f <= 0:
            qty_f = 1.0
        unit = re.sub(r"\s+", " ", str(raw.get("unit") or "")).strip()[:40] or None
        items.append({"name": label, "quantity": qty_f, "unit": unit})
    if not items:
        return None
    return {"type": "create_shop_list", "name": name, "items": items}


def normalize_diary_entry_action(data: dict | None) -> dict | None:
    if not isinstance(data, dict):
        return None
    if (data.get("type") or "") != "create_diary_entry":
        return None
    title = re.sub(r"\s+", " ", str(data.get("title") or "")).strip()[:255]
    if not title:
        return None
    body = str(data.get("body") or "").strip()
    charges_in = data.get("charges") if isinstance(data.get("charges"), list) else []
    charges: list[dict] = []
    for raw in charges_in[:40]:
        if isinstance(raw, str):
            continue
        if not isinstance(raw, dict):
            continue
        label = re.sub(r"\s+", " ", str(raw.get("label") or raw.get("name") or "")).strip()[:120]
        if not label:
            continue
        charges.append({"label": label, "amount": _f(raw.get("amount"))})
    if charges:
        body = format_diary_charges_table(charges, preface=body or None)
    if not body:
        body = title
    entry_date = str(data.get("entry_date") or "").strip()[:10]
    if entry_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry_date):
        entry_date = ""
    if not entry_date:
        entry_date = vault_today()
    category = re.sub(r"\s+", " ", str(data.get("category") or "")).strip()[:80] or None
    tags = re.sub(r"\s+", " ", str(data.get("tags") or "")).strip()[:255] or None
    mood = re.sub(r"\s+", " ", str(data.get("mood") or "")).strip()[:80] or None
    pinned = bool(data.get("pinned"))
    return {
        "type": "create_diary_entry",
        "title": title,
        "body": body[:20000],
        "charges": charges,
        "entry_date": entry_date,
        "category": category,
        "tags": tags,
        "mood": mood,
        "pinned": pinned,
    }


_PAYMENT_METHODS = {"upi", "credit_card", "debit_card", "atm", "netbanking", "cash", "other"}


def normalize_diary_folder_action(data: dict | None) -> dict | None:
    if not isinstance(data, dict):
        return None
    if (data.get("type") or "") != "create_diary_folder":
        return None
    name = re.sub(r"\s+", " ", str(data.get("name") or data.get("title") or "")).strip()[:80]
    if not name:
        return None
    color = str(data.get("color") or "").strip()[:16] or None
    if color and not re.fullmatch(r"#?[0-9A-Fa-f]{3,8}", color):
        color = None
    if color and not color.startswith("#"):
        color = f"#{color}"
    return {"type": "create_diary_folder", "name": name, "color": color}


def apply_diary_folder_action(db: Session, user: models.User, action: dict) -> dict:
    """Create a Digital Diary folder (category) from an approved Ask AI action."""
    from fastapi import HTTPException

    from app.routers import diary as dy
    from app import schemas as sc

    normalized = normalize_diary_folder_action(action)
    if not normalized:
        raise ValueError("Invalid diary folder action")
    dy.ensure_defaults(db, user)
    uid = _uid(user)
    existing = (
        db.query(models.DiaryCategory)
        .filter(
            models.DiaryCategory.user_id == uid,
            models.DiaryCategory.name.ilike(normalized["name"]),
        )
        .first()
    )
    if existing:
        return {
            "folder_id": existing.id,
            "name": existing.name,
            "created": False,
            "url": f"/admin/diary?category_id={existing.id}",
        }
    try:
        row = dy.create_category(
            sc.DiaryCategoryIn(name=normalized["name"], color=normalized.get("color")),
            db=db,
            current_user=user,
        )
    except HTTPException as exc:
        raise ValueError(str(exc.detail)) from exc
    return {
        "folder_id": row.id,
        "name": row.name,
        "created": True,
        "url": f"/admin/diary?category_id={row.id}",
    }


def normalize_finance_txn_action(data: dict | None) -> dict | None:
    if not isinstance(data, dict):
        return None
    if (data.get("type") or "") != "create_finance_txn":
        return None
    amount = _f(data.get("amount"))
    if amount <= 0:
        return None
    payee = re.sub(r"\s+", " ", str(data.get("payee") or data.get("label") or "")).strip()[:255]
    if not payee:
        payee = "Expense"
    account = re.sub(r"\s+", " ", str(data.get("account") or "")).strip()[:255] or None
    category = re.sub(r"\s+", " ", str(data.get("category") or "")).strip()[:120] or None
    txn_type = str(data.get("txn_type") or "expense").strip().lower()
    if txn_type not in {"expense", "income"}:
        txn_type = "expense"
    txn_date = str(data.get("txn_date") or "").strip()[:10]
    if txn_date and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", txn_date):
        txn_date = ""
    if not txn_date:
        txn_date = vault_today()
    notes = str(data.get("notes") or "").strip()[:2000] or None
    method = str(data.get("payment_method") or "").strip().lower().replace(" ", "_")
    if method not in _PAYMENT_METHODS:
        method = None
    return {
        "type": "create_finance_txn",
        "amount": amount,
        "payee": payee,
        "account": account,
        "category": category,
        "txn_type": txn_type,
        "txn_date": txn_date,
        "notes": notes,
        "payment_method": method,
    }


def _resolve_finance_account(db: Session, uid: str, name: str | None, payment_method: str | None):
    accounts = (
        db.query(models.FinanceAccount)
        .filter(models.FinanceAccount.user_id == uid, models.FinanceAccount.archived.is_(False))
        .order_by(models.FinanceAccount.name)
        .all()
    )
    if not accounts:
        return None
    if name:
        needle = name.casefold()
        for a in accounts:
            if a.name.casefold() == needle:
                return a
        for a in accounts:
            if needle in a.name.casefold() or (a.institution and needle in a.institution.casefold()):
                return a
    if payment_method == "cash":
        for a in accounts:
            if a.account_type == "cash" or "cash" in (a.name or "").casefold():
                return a
    if payment_method in {"credit_card", "debit_card"}:
        want = "credit_card" if payment_method == "credit_card" else "bank"
        for a in accounts:
            if a.account_type == want or a.account_type == "credit_card":
                return a
    return accounts[0]


def _resolve_finance_category(db: Session, uid: str, name: str | None, txn_type: str, payee: str):
    rows = (
        db.query(models.FinanceCategory)
        .filter(models.FinanceCategory.user_id == uid, models.FinanceCategory.kind == txn_type)
        .order_by(models.FinanceCategory.name)
        .all()
    )
    if not rows:
        return None
    if name:
        needle = name.casefold()
        for c in rows:
            if c.name.casefold() == needle:
                return c
        for c in rows:
            if needle in c.name.casefold():
                return c
    hay = f"{payee} {name or ''}".casefold()
    for hint, keys in (
        ("Transport", ("petrol", "diesel", "fuel", "uber", "ola", "auto", "bus", "train")),
        ("Food", ("food", "tea", "coffee", "lunch", "dinner", "snacks", "restaurant")),
        ("Groceries", ("grocery", "groceries", "supermarket", "bigbasket")),
        ("Shopping", ("shopping", "amazon", "flipkart")),
    ):
        if any(k in hay for k in keys):
            for c in rows:
                if c.name.casefold() == hint.casefold() or hint.casefold() in c.name.casefold():
                    return c
    return None


def apply_shop_list_action(db: Session, user: models.User, action: dict) -> dict:
    """Create a ShopList + items from an approved Ask AI action."""
    from app import schemas as sc
    from app.routers.tracker import _add_item_row, _list_out

    normalized = normalize_shop_list_action(action)
    if not normalized:
        raise ValueError("Invalid shopping list action")
    lst = models.ShopList(
        user_id=_uid(user),
        name=normalized["name"].title(),
        description="Created from Ask AI",
    )
    db.add(lst)
    db.flush()
    for row in normalized["items"]:
        body = sc.ShopItemIn(
            name=row["name"],
            quantity=row.get("quantity") or 1,
            unit=row.get("unit"),
        )
        _add_item_row(db, lst, body, added_by=user.id, status="approved")
    db.commit()
    db.refresh(lst)
    out = _list_out(db, lst, with_items=True)
    return {
        "list_id": out.id,
        "name": out.name,
        "item_count": out.item_count,
        "url": f"/admin/tracker/lists/{out.id}",
    }


def apply_diary_entry_action(db: Session, user: models.User, action: dict) -> dict:
    """Create a Digital Diary entry from an approved Ask AI action."""
    from app.routers import diary as dy

    normalized = normalize_diary_entry_action(action)
    if not normalized:
        raise ValueError("Invalid diary entry action")
    dy.ensure_defaults(db, user)
    uid = _uid(user)
    category_id = None
    cat_name = normalized.get("category")
    if cat_name:
        row = (
            db.query(models.DiaryCategory)
            .filter(
                models.DiaryCategory.user_id == uid,
                models.DiaryCategory.name.ilike(cat_name),
            )
            .first()
        )
        if row:
            category_id = row.id
    entry = models.DiaryEntry(
        user_id=uid,
        title=normalized["title"],
        body_enc=crypto.encrypt_text(normalized["body"]),
        entry_date=normalized["entry_date"],
        category_id=category_id,
        tags=normalized.get("tags"),
        mood=normalized.get("mood"),
        pinned=bool(normalized.get("pinned")),
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return {
        "entry_id": entry.id,
        "title": entry.title,
        "url": f"/admin/diary/{entry.id}",
    }


def apply_finance_txn_action(db: Session, user: models.User, action: dict) -> dict:
    """Create a Money Manager transaction from an approved Ask AI action."""
    from decimal import Decimal

    from app.routers import finance as fn

    normalized = normalize_finance_txn_action(action)
    if not normalized:
        raise ValueError("Invalid finance transaction action")
    fn.ensure_defaults(db, user)
    uid = _uid(user)
    acc = _resolve_finance_account(
        db, uid, normalized.get("account"), normalized.get("payment_method"),
    )
    if not acc:
        raise ValueError("Add a Money Manager account first")
    cat = _resolve_finance_category(
        db, uid, normalized.get("category"), normalized["txn_type"], normalized["payee"],
    )
    method = normalized.get("payment_method")
    desc = normalized["payee"]
    row = models.FinanceTransaction(
        user_id=uid,
        account_id=acc.id,
        category_id=cat.id if cat else None,
        txn_type=normalized["txn_type"],
        amount=Decimal(str(round(normalized["amount"], 2))),
        txn_date=normalized["txn_date"],
        payee=normalized["payee"],
        notes=normalized.get("notes"),
        description=desc,
        payment_method=method,
        source="ask_ai",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {
        "txn_id": row.id,
        "payee": row.payee or desc,
        "amount": float(row.amount),
        "account_name": acc.name,
        "url": f"/admin/finance?q={row.payee or ''}",
    }


def complete_chat(
    *,
    kind: str,
    api_key: str | None,
    model: str | None,
    base_url: str | None,
    system: str,
    messages: list[dict[str, str]],
) -> dict:
    """Return {content, kind, model, prompt_tokens, completion_tokens, total_tokens}."""
    kind = (kind or "openai").lower()
    model = model or DEFAULT_MODELS.get(kind, "gpt-4o-mini")
    base = (base_url or DEFAULT_BASES.get(kind) or "https://api.openai.com/v1").rstrip("/")
    if kind == "anthropic":
        if not api_key:
            raise ValueError("Anthropic needs an API key")
        content, usage = _anthropic_messages(api_key, model, system, messages)
    else:
        content, usage = _openai_messages(base, api_key, model, system, messages)
    return {
        "content": content or "",
        "kind": kind,
        "model": usage.get("model") or model,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }


def _openai_messages(
    base_url: str, api_key: str | None, model: str, system: str, messages: list[dict[str, str]]
) -> tuple[str, dict]:
    from app.ai_usage import parse_usage

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
    content = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    usage = parse_usage(data)
    usage["model"] = data.get("model") or model
    return content, usage


def _anthropic_messages(
    api_key: str, model: str, system: str, messages: list[dict[str, str]]
) -> tuple[str, dict]:
    from app.ai_usage import parse_usage

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
    content = "".join(p.get("text") or "" for p in parts if isinstance(p, dict))
    usage = parse_usage(data)
    usage["model"] = data.get("model") or model
    return content, usage


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


def _store_deterministic_reply(
    db: Session,
    user: models.User,
    thread: models.AiChatThread,
    text: str,
    reply: str,
) -> dict:
    now = datetime.utcnow()
    db.add(models.AiChatMessage(
        thread_id=thread.id, role="user", content_enc=crypto.encrypt_text(text), created_at=now,
    ))
    db.add(models.AiChatMessage(
        thread_id=thread.id, role="assistant", content_enc=crypto.encrypt_text(reply),
        created_at=now + timedelta(seconds=1),
    ))
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
        "action": None,
        "messages": detail["messages"] if detail else [],
    }


def ask(db: Session, user: models.User, message: str, thread_id: str | None = None) -> dict:
    import time
    from app import ai_usage

    text = (message or "").strip()
    if not text:
        raise ValueError("Type a question first")

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

    from app import ai_brain
    brain_only = ai_brain.apply_brain_command(db, user, text)
    if brain_only:
        reply, learned, _forgotten = brain_only
        result = _store_deterministic_reply(db, user, thread, text, reply)
        result["learned"] = learned
        return result

    # Secrets and ledger facts stay on this server — never sent to the AI provider.
    ledger_day = should_answer_ledger_day(text, history)
    if ledger_day:
        if needs_spend_clarify(text, history):
            reply = format_spend_clarify(ledger_day, text)
        else:
            reply = format_money_manager_day_reply(
                db, user, ledger_day, question=text, history=history,
                source=resolve_spend_source(text, history),
            )
        return _store_deterministic_reply(db, user, thread, text, reply)
    if wants_analyser_upi_breakdown(text):
        reply = format_analyser_upi_breakdown(db, user, text)
        return _store_deterministic_reply(db, user, thread, text, reply)
    if should_answer_highest_expense(text, history):
        source_q = text
        if not wants_highest_expense(text):
            for m in reversed(history or []):
                if (m.get("role") or "") == "user" and wants_highest_expense(m.get("content") or ""):
                    source_q = m.get("content") or text
                    break
        reply = format_highest_expense_reply(db, user, source_q)
        return _store_deterministic_reply(db, user, thread, text, reply)
    if wants_password_lookup(text):
        reply = format_password_lookup_reply(db, user, text)
        return _store_deterministic_reply(db, user, thread, text, reply)
    if wants_locker_lookup(text):
        reply = format_locker_lookup_reply(db, user, text)
        return _store_deterministic_reply(db, user, thread, text, reply)
    if wants_health_lookup(text):
        reply = format_health_lookup_reply(db, user, text)
        return _store_deterministic_reply(db, user, thread, text, reply)

    bundle = ap.get_default_bundle(db, user)
    if not bundle:
        raise LookupError("Add an AI provider first")

    snapshot = build_vault_context(db, user, text)
    system = SYSTEM_PROMPT + "\n\n" + snapshot
    payload = [{"role": m["role"], "content": m["content"]} for m in history]
    payload.append({"role": "user", "content": text})

    started = time.monotonic()
    try:
        result = complete_chat(
            kind=bundle["kind"],
            api_key=bundle.get("api_key"),
            model=bundle.get("model"),
            base_url=bundle.get("base_url"),
            system=system,
            messages=payload,
        )
        latency = int((time.monotonic() - started) * 1000)
        reply = (result.get("content") or "").strip()
        ai_usage.record(
            db, user,
            client="ask_ai",
            provider_name=bundle.get("name"),
            provider_kind=bundle.get("kind"),
            model=result.get("model") or bundle.get("model"),
            prompt_tokens=result.get("prompt_tokens"),
            completion_tokens=result.get("completion_tokens"),
            total_tokens=result.get("total_tokens"),
            latency_ms=latency,
            ok=True,
            request_text=text,
            response_text=reply,
        )
    except ValueError as exc:
        latency = int((time.monotonic() - started) * 1000)
        ai_usage.record(
            db, user,
            client="ask_ai",
            provider_name=bundle.get("name"),
            provider_kind=bundle.get("kind"),
            model=bundle.get("model"),
            latency_ms=latency,
            ok=False,
            error=str(exc)[:200],
            request_text=text,
        )
        raise
    except Exception as exc:
        latency = int((time.monotonic() - started) * 1000)
        ai_usage.record(
            db, user,
            client="ask_ai",
            provider_name=bundle.get("name"),
            provider_kind=bundle.get("kind"),
            model=bundle.get("model"),
            latency_ms=latency,
            ok=False,
            error=str(exc)[:200],
            request_text=text,
        )
        raise ValueError(f"Provider failed: {exc}") from exc
    if not reply:
        reply = "The provider returned an empty reply. Try again, or test the key on the Providers page."

    display_reply, action = extract_vault_action(reply)
    # Persist display text + action fence so the UI can re-offer Approve after reload.
    store_reply = display_reply
    if action:
        store_reply = (
            display_reply.rstrip()
            + "\n\n```vault-action\n"
            + json.dumps(action, ensure_ascii=False)
            + "\n```"
        )

    now = datetime.utcnow()
    user_row = models.AiChatMessage(
        thread_id=thread.id, role="user", content_enc=crypto.encrypt_text(text), created_at=now,
    )
    asst_row = models.AiChatMessage(
        thread_id=thread.id, role="assistant", content_enc=crypto.encrypt_text(store_reply),
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
        "reply": display_reply,
        "action": action,
        "messages": detail["messages"] if detail else [],
    }


_CATALOG_TRANSLATE_SYSTEM = """You translate Kerala grocery names from Manglish (Malayalam in Latin letters)
or Malayalam script into a short English grocery label for a shopping-list catalog.

Reply with JSON only — no markdown fences, no commentary:
{"english":"...","malayalam":"...","emoji":"...","category":"..."}

Rules:
- english: common Indian English grocery name (e.g. Brinjal not Eggplant when Kerala-typical)
- malayalam: Malayalam script when you know it, else empty string
- emoji: one grocery emoji
- category: one of vegetables, fruits, spices, dals, grains, essentials, dairy, fish, meat, snacks, household, custom
- If the input is already clear English, keep english as that name (title case)
"""


def _parse_translate_json(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("AI did not return JSON")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("AI JSON was not an object")
    return data


def translate_manglish_catalog(db: Session, user: models.User, text: str) -> dict:
    """Dictionary-first Manglish → English; AI fallback when no strong match."""
    import time
    from app import ai_usage
    from app.grocery import CATALOG_CATEGORIES, translate_via_dictionary

    raw = (text or "").strip()
    if len(raw) < 2:
        raise ValueError("Type at least 2 characters")

    hit = translate_via_dictionary(db, raw, user_id=_uid(user))
    if hit and hit.get("source") in ("dictionary", "unchanged"):
        return hit

    bundle = ap.get_default_bundle(db, user)
    if not bundle:
        raise LookupError("Add an AI provider first (Ask AI → Providers)")

    started = time.monotonic()
    try:
        result = complete_chat(
            kind=bundle["kind"],
            api_key=bundle.get("api_key"),
            model=bundle.get("model"),
            base_url=bundle.get("base_url"),
            system=_CATALOG_TRANSLATE_SYSTEM,
            messages=[{"role": "user", "content": raw}],
        )
        latency = int((time.monotonic() - started) * 1000)
        parsed = _parse_translate_json(result.get("content") or "")
        en = (parsed.get("english") or "").strip()
        if not en:
            raise ValueError("AI returned an empty English name")
        cat = (parsed.get("category") or "custom").strip().lower()
        if cat not in CATALOG_CATEGORIES:
            cat = "custom"
        ml = (parsed.get("malayalam") or "").strip() or None
        emoji = (parsed.get("emoji") or "🛒").strip() or "🛒"
        same = raw.lower() == en.lower()
        out = {
            "english": en,
            "malayalam": ml,
            "emoji": emoji[:16],
            "category": cat,
            "source": "unchanged" if same else "ai",
            "manglish": raw,
        }
        ai_usage.record(
            db, user,
            client="catalog_translate",
            provider_name=bundle.get("name"),
            provider_kind=bundle.get("kind"),
            model=result.get("model") or bundle.get("model"),
            prompt_tokens=result.get("prompt_tokens"),
            completion_tokens=result.get("completion_tokens"),
            total_tokens=result.get("total_tokens"),
            latency_ms=latency,
            ok=True,
            request_text=raw,
            response_text=json.dumps(out, ensure_ascii=False),
        )
        return out
    except Exception as exc:
        latency = int((time.monotonic() - started) * 1000)
        ai_usage.record(
            db, user,
            client="catalog_translate",
            provider_name=bundle.get("name"),
            provider_kind=bundle.get("kind"),
            model=bundle.get("model"),
            latency_ms=latency,
            ok=False,
            error=str(exc)[:200],
            request_text=raw,
        )
        raise
