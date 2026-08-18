"""Classify bank/UPI/SMS messages into debit vs credit and a money-manager category.

Works offline with heuristics. If an AI provider key is configured, that result
wins when confidence is higher than the heuristic.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-3-5-haiku-latest",
    "openrouter": "openai/gpt-4o-mini",
    "kimi": "moonshot-v1-8k",
    "groq": "llama-3.3-70b-versatile",
    "ollama": "llama3.2",
    "custom": "gpt-4o-mini",
}

DEFAULT_BASES = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "kimi": "https://api.moonshot.ai/v1",
    "groq": "https://api.groq.com/openai/v1",
    "ollama": "http://127.0.0.1:11434/v1",
}

EXPENSE_CATEGORIES = [
    "Food & dining", "Groceries", "Transport", "Fuel", "Shopping",
    "Bills & utilities", "Rent", "Health", "Education", "Entertainment",
    "Travel", "Subscriptions", "UPI / transfers", "ATM / cash",
    "EMI / loans", "Insurance", "Family", "Other",
]

PAYMENT_METHODS = (
    "upi", "credit_card", "debit_card", "atm", "netbanking", "cash", "other",
)
PAYMENT_LABELS = {
    "upi": "UPI",
    "credit_card": "Credit card",
    "debit_card": "Debit card",
    "atm": "ATM cash withdrawal",
    "netbanking": "Net banking",
    "cash": "Cash",
    "other": "Other",
}
INCOME_CATEGORIES = [
    "Salary", "Freelance", "Business", "Interest", "Refund", "Gift", "Other income",
]
ALL_CATEGORIES = EXPENSE_CATEGORIES + INCOME_CATEGORIES

_PAYEE_MAP: list[tuple[tuple[str, ...], str]] = [
    (("swiggy", "zomato", "eatsure", "dominos", "mcdonald"), "Food & dining"),
    (("blinkit", "zepto", "bigbasket", "jiomart", "dmart", "grocery"), "Groceries"),
    (("uber", "ola", "rapido", "irctc", "metro", "redbus", "makemytrip"), "Transport"),
    (("hpcl", "bpcl", "iocl", "indian oil", "petrol", "diesel"), "Fuel"),
    (("amazon", "flipkart", "myntra", "ajio", "meesho", "nykaa"), "Shopping"),
    (("jio", "airtel", "vi ", "bsnl", "electricity", "bescom", "water board", "gas"), "Bills & utilities"),
    (("rent", "nobroker", "housing.com"), "Rent"),
    (
        (
            "apollo", "1mg", "pharmeasy", "pharmacy", "hospital", "clinic",
            "medical", "medico", "dental", "diagnostic", "doctor", "labs",
        ),
        "Health",
    ),
    (("byju", "unacademy", "coursera", "udemy", "school", "college"), "Education"),
    (("netflix", "spotify", "youtube premium", "hotstar", "prime video", "apple.com/bill", "google one", "icloud"), "Subscriptions"),
    (("bookmyshow", "pvr", "inox"), "Entertainment"),
    (("indigo", "airindia", "spicejet", "goibibo", "booking.com", "airbnb", "oyo"), "Travel"),
    # Keep EMI / Insurance specific — short tokens use word boundaries in _keyword_hit.
    # Do NOT add "convert to emi" / "easy emi" (card marketing footers).
    (("emi", "loan", "bajaj finserv", "hdfc bank emi"), "EMI / loans"),
    (
        (
            "insurance", "policybazaar", "life insurance", "health insurance",
            "lic of india", "lic premium", "star health", "hdfc life", "sbi life",
        ),
        "Insurance",
    ),
    (("salary", "payroll", "neft cr", "credited by"), "Salary"),
    (("refund", "reversed", "cashback"), "Refund"),
]

# Short / ambiguous keys must not match inside other words (click→lic, premium→emi, medical footer noise).
_BOUNDARY_KEYS = frozenset({
    "emi", "lic", "loan", "gas", "rent", "atm", "vi ", "labs", "pvr",
})
_HEALTH_HINT_RE = re.compile(
    r"medical|medico|hospital|clinic|pharma|pharmacy|diagnostic|dental|"
    r"doctor|apollo|1mg|pharmeasy|\blabs?\b",
    re.I,
)
_PERSONAL_VPA_RE = re.compile(
    r"\b[a-z0-9][a-z0-9._-]{2,40}@"
    r"(?:oksbi|okaxis|okybl|okhdfcbank|ybl|paytm|ibl|fbl|axl|upi)\b",
    re.I,
)
_KNOWN_MERCHANT_HINT_RE = re.compile(
    r"swiggy|zomato|amazon|flipkart|myntra|uber|ola|irctc|netflix|spotify|"
    r"phonepe|google pay|gpay|paytm|bigbasket|blinkit|zepto",
    re.I,
)

_AMOUNT_RE = re.compile(
    r"(?:rs\.?|inr|₹)\s*("
    r"[0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]{1,2})?"
    r"|[0-9]+(?:\.[0-9]{1,2})?"
    r")",
    re.I,
)
_AMOUNT_ALT_RE = re.compile(
    r"\b([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]{1,2})?|[0-9]+\.[0-9]{2})\s*(?:rs|inr|debited|credited)",
    re.I,
)
_DEBIT_RE = re.compile(
    r"\b(debited|debit|spent|paid|purchase|withdrawn|dr\b|sent to|transferred to|"
    r"used for a (?:transaction|purchase|payment)|"
    r"upi txn|done a (?:upi )?txn|txn from|txn of|transaction of)\b",
    re.I,
)
_CREDIT_RE = re.compile(
    r"\b(credited|received|refund(?:ed)?|deposited|cr\b|added to)\b",
    re.I,
)
# Bare "credit" (as in Available Credit Limit) must NOT count as income.
_CREDIT_LIMIT_RE = re.compile(r"\b(?:available\s+)?credit\s+limit\b|\bcredit\s+balanc", re.I)
_ATM_RE = re.compile(r"\batm\b|atm\s*wdl|cash withdraw|withdrawn (?:at|from) atm|atm withdrawal", re.I)
_CC_RE = re.compile(
    r"credit\s*card|\bcc\s*(?:xx|ending|no\.?)|on your credit card|"
    r"card\s+xx\d{2,4}|card\s+ending",
    re.I,
)
_CC_SPEND_RE = re.compile(
    r"credit\s*card.{0,80}(?:used for|spent|purchase|txn|transaction|payment)|"
    r"(?:used for|spent|purchase).{0,40}credit\s*card|"
    r"has been used for a transaction",
    re.I | re.S,
)
_DC_RE = re.compile(r"debit\s*card|\bdc\s*(?:xx|ending)|pos\s+(?:purchase|txn)", re.I)
_UPI_RE = re.compile(r"\bupi\b|vpa|upi[\s-]?ref|upi-?id|@oksbi|@okaxis|@ybl|@paytm|@ibl", re.I)
_NB_RE = re.compile(r"\bneft\b|\bimps\b|\brtgs\b|net\s*banking|internet banking", re.I)
_PAYEE_RE = re.compile(
    r"(?:to|from|via u?pi(?:/.*?|id)?(?:\s+to)?)\s+"
    r"(?!inform\b|you\b|your\b|the\b|a\b|an\b)"
    r"([A-Z0-9][A-Za-z0-9 .&@_-]{2,40})",
    re.I,
)
_INFO_PAYEE_RE = re.compile(
    r"(?:info|merchant)\s*[:\-–]\s*([A-Z0-9][A-Za-z0-9 .&@/_-]{2,50})",
    re.I,
)
# South Indian Bank / NPCI style: UPI/SBIN/659519060532/JIBIN S/UPI
_UPI_SLASH_PAYEE_RE = re.compile(
    r"\bUPI/[A-Z]{2,10}/\d{6,}/([^/\n]{2,40})/UPI\b",
    re.I,
)
_PAYEE_CUT_RE = re.compile(
    r"\b(?:of\s+(?:inr|rs\.?|₹)|with\s+your|using\s+your|on\s+your|"
    r"has\s+been|credit\s*c(?:ard)?|debit\s*c(?:ard)?|available|"
    r"info\s*:|txn|transaction|for\s+rs|for\s+inr)\b.*$",
    re.I,
)
_JUNK_PAYEE_RE = re.compile(
    r"^(?:inform you that|merchant platform|apply|your|a/c|account|"
    r"upi|imps|neft|card holder|primary card holder|the primary card holder|"
    r"dear customer|customer)$",
    re.I,
)
_PAYEE_BRANDS = {
    "hdfc": "HDFC",
    "hdfc bank": "HDFC Bank",
    "sbi": "SBI",
    "icici": "ICICI",
    "icici bank": "ICICI Bank",
    "axis": "Axis",
    "axis bank": "Axis Bank",
    "amazon": "Amazon",
    "amazon pay": "Amazon Pay",
    "flipkart": "Flipkart",
    "swiggy": "Swiggy",
    "zomato": "Zomato",
    "paytm": "Paytm",
    "phonepe": "PhonePe",
    "google pay": "Google Pay",
    "gpay": "GPay",
    "netflix": "Netflix",
    "spotify": "Spotify",
    "uber": "Uber",
    "ola": "Ola",
    "irctc": "IRCTC",
    "atm": "ATM",
}
_DATE_RE = re.compile(r"\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b")
_DATE_NAMED_RE = re.compile(
    r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*,?\s+\d{2,4})"
    r"|"
    r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{2,4})\b",
    re.I,
)

def split_messages(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    chunks = [c.strip() for c in re.split(r"\n\s*\n", text) if c.strip()]
    if len(chunks) == 1 and text.count("\n") >= 3:
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        if lines and all(len(ln) > 40 for ln in lines):
            return lines
    return chunks


def _parse_amount(text: str) -> float | None:
    m = _AMOUNT_RE.search(text) or _AMOUNT_ALT_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _parse_date(text: str) -> str | None:
    m = _DATE_RE.search(text or "")
    if m:
        raw = m.group(1).replace("/", "-")
        parts = raw.split("-")
        if len(parts) == 3:
            d, mo, y = parts
            if len(y) == 2:
                y = "20" + y
            try:
                return datetime(int(y), int(mo), int(d)).strftime("%Y-%m-%d")
            except ValueError:
                try:
                    return datetime(int(y), int(d), int(mo)).strftime("%Y-%m-%d")
                except ValueError:
                    pass
    m = _DATE_NAMED_RE.search(text or "")
    if m:
        raw = (m.group(1) or m.group(2) or "").replace(",", " ")
        raw = re.sub(r"\s+", " ", raw).strip()
        for fmt in (
            "%d %b %Y", "%d %B %Y", "%d %b %y", "%d %B %y",
            "%b %d %Y", "%B %d %Y", "%b %d %y", "%B %d %y",
        ):
            try:
                return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return None


def _parse_txn_date(text: str) -> str | None:
    """Prefer a date near spend language / amount so HTML footers don't stamp old days."""
    blob = text or ""
    for m in re.finditer(
        r"(?:transaction of|txn of|debited|credited|spent|withdrawn|used for).{0,140}",
        blob,
        re.I | re.S,
    ):
        found = _parse_date(m.group(0))
        if found:
            return found
    windows: list[str] = []
    for am in list(_AMOUNT_RE.finditer(blob))[:6]:
        prefix = blob[max(0, am.start() - 48):am.start()].lower()
        if "credit limit" in prefix or "available" in prefix:
            continue
        start = max(0, am.start() - 90)
        end = min(len(blob), am.end() + 90)
        windows.append(blob[start:end])
    for am in list(_AMOUNT_ALT_RE.finditer(blob))[:2]:
        start = max(0, am.start() - 90)
        end = min(len(blob), am.end() + 90)
        windows.append(blob[start:end])
    for chunk in windows:
        found = _parse_date(chunk)
        if found:
            return found
    if len(blob) <= 400:
        return _parse_date(blob)
    return None


def format_payee(payee: str | None) -> str | None:
    """Title-case payee for display; keep known bank/brand spellings."""
    text = (payee or "").strip(" .-_")
    if not text:
        return None
    lower = re.sub(r"\s+", " ", text).strip().lower()
    if lower in _PAYEE_BRANDS:
        return _PAYEE_BRANDS[lower]
    for key, nice in sorted(_PAYEE_BRANDS.items(), key=lambda kv: -len(kv[0])):
        if lower == key or lower.startswith(key + " "):
            rest = text[len(key):].strip(" .-_")
            return nice if not rest else f"{nice} {format_payee(rest) or rest.title()}"
    parts = []
    for part in re.split(r"(\s+)", text):
        if not part or part.isspace():
            parts.append(part)
            continue
        low = part.lower()
        if low in _PAYEE_BRANDS:
            parts.append(_PAYEE_BRANDS[low])
        elif part.isupper() and len(part) <= 5 and len(part) != 1:
            parts.append(part)
        else:
            parts.append(part[:1].upper() + part[1:].lower())
    return "".join(parts).strip() or None


def normalize_payee(payee: str | None) -> str | None:
    """Strip alert boilerplate and return a clean, cased merchant name."""
    text = re.sub(r"\s+", " ", (payee or "").strip(" .-_"))
    if not text:
        return None
    text = _PAYEE_CUT_RE.sub("", text).strip(" .-_")
    text = re.sub(r"\bINR\s*[\d,]+\.?\d*\b", "", text, flags=re.I)
    text = re.sub(r"\bRs\.?\s*[\d,]+\.?\d*\b", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip(" .-_")
    if len(text) < 2 or _JUNK_PAYEE_RE.match(text):
        return None
    if re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", text):
        return None
    if len(text.split()) > 6:
        text = " ".join(text.split()[:4]).strip(" .-_")
    # Drop trailing "I" leftovers from cut "INR" ("FLIPKART I"). Keep "JIBIN S".
    parts = text.split()
    while parts and parts[-1].upper() == "I" and len(parts[-1]) == 1:
        parts.pop()
    text = " ".join(parts).strip(" .-_")
    if len(text) < 2 or _JUNK_PAYEE_RE.match(text):
        return None
    return format_payee(text)


def _guess_payee(text: str) -> str | None:
    m = _UPI_SLASH_PAYEE_RE.search(text or "")
    if m:
        payee = normalize_payee(m.group(1))
        if payee and payee.lower() not in {"upi", "sbin", "imps"}:
            return payee
    m = _INFO_PAYEE_RE.search(text or "")
    if m:
        raw = m.group(1)
        slash = _UPI_SLASH_PAYEE_RE.search(raw) or _UPI_SLASH_PAYEE_RE.search(text or "")
        if slash:
            payee = normalize_payee(slash.group(1))
            if payee and payee.lower() not in {"upi", "sbin", "imps"}:
                return payee
        payee = normalize_payee(raw)
        if payee:
            return payee
    m = _PAYEE_RE.search(text or "")
    if m:
        payee = normalize_payee(m.group(1))
        if payee:
            return payee
    lower = (text or "").lower()
    for key, nice in sorted(_PAYEE_BRANDS.items(), key=lambda kv: -len(kv[0])):
        if key in {"atm", "hdfc", "sbi", "icici", "axis", "hdfc bank", "icici bank", "axis bank"}:
            continue
        if re.search(rf"\b{re.escape(key)}\b", lower):
            return nice
    return None


def detect_payment_method(text: str) -> tuple[str, float]:
    # Credit-card spend alerts must never be tagged ATM just because of odd AI guesses later.
    # Prefer explicit "debit card" before the generic "card xx1234" credit-card pattern.
    if _DC_RE.search(text) and not re.search(r"credit\s*card", text or "", re.I):
        return "debit_card", 0.9
    if _CC_RE.search(text) or _CC_SPEND_RE.search(text):
        return "credit_card", 0.93
    if _ATM_RE.search(text):
        return "atm", 0.92
    if _UPI_RE.search(text):
        return "upi", 0.93
    if _NB_RE.search(text):
        return "netbanking", 0.86
    return "other", 0.3


def build_description(
    method: str | None,
    payee: str | None,
    category: str | None,
    notes: str | None = None,
) -> str | None:
    if notes and str(notes).strip():
        return str(notes).strip()[:200]
    label = PAYMENT_LABELS.get(method or "")
    if label == "Other":
        label = None
    who = (payee or category or "").strip() or None
    if who in {"ATM / cash", "Other", "Other income"}:
        who = None
    if label and who:
        return f"{label} · {who}"[:200]
    return label or who


def _keyword_hit(haystack: str, key: str) -> bool:
    needle = (key or "").strip().lower()
    if not needle or not haystack:
        return False
    # Trailing-space keys (e.g. "vi ") are intentional phrase pads — keep substring match.
    if needle.endswith(" ") or len(needle) <= 3 or needle in _BOUNDARY_KEYS:
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(needle.strip())}(?![a-z0-9])", haystack))
    return needle in haystack


def _keyword_category(text: str, direction: str) -> tuple[str, float]:
    lower = (text or "").lower()
    # Merchant health signals beat EMI/insurance marketing footers.
    if direction != "credit" and _HEALTH_HINT_RE.search(lower):
        return "Health", 0.9
    best: tuple[str, float, int] | None = None
    for keys, cat in _PAYEE_MAP:
        for key in keys:
            if not _keyword_hit(lower, key):
                continue
            score = len(key.strip())
            if best is None or score > best[2]:
                best = (cat, 0.8, score)
    if best is None:
        if direction != "credit" and _looks_personal_upi(text):
            return "UPI / transfers", 0.82
        if direction == "credit":
            return "Other income", 0.4
        return "Other", 0.4
    cat, conf, _ = best
    if direction == "credit" and cat not in INCOME_CATEGORIES:
        if cat == "Refund":
            return cat, 0.82
        return "Other income", 0.55
    if direction == "debit" and cat in INCOME_CATEGORIES and cat != "Refund":
        return "Other", 0.5
    if cat in {"EMI / loans", "Insurance"} and _looks_personal_upi(text):
        return "UPI / transfers", 0.86
    return cat, conf


def _looks_personal_upi(text: str, payee: str | None = None) -> bool:
    """True for person-to-person UPI (name@oksbi), not merchant brands."""
    blob = f"{text or ''} {payee or ''}"
    if _KNOWN_MERCHANT_HINT_RE.search(blob):
        return False
    if _HEALTH_HINT_RE.search(blob):
        return False
    if _PERSONAL_VPA_RE.search(blob):
        return True
    who = (payee or "").strip()
    if who and re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,40}", who):
        # "VJ BIJI", "Renish K" — person-like, not ALLCAPS merchant brands with digits.
        if not re.search(r"\d", who) and len(who.split()) <= 4:
            return True
    return False


def classify_heuristic(text: str) -> dict[str, Any]:
    debit = bool(_DEBIT_RE.search(text))
    credit = bool(_CREDIT_RE.search(text))
    # Ignore "Available Credit Limit" style wording for income detection.
    if _CREDIT_LIMIT_RE.search(text) and not re.search(
        r"\b(credited|received|refund(?:ed)?|deposited)\b", text or "", re.I
    ):
        credit = False
    if _CC_SPEND_RE.search(text):
        debit = True
    if credit and not debit:
        direction = "credit"
    elif debit and not credit:
        direction = "debit"
    elif credit and debit:
        dpos = _DEBIT_RE.search(text)
        cpos = _CREDIT_RE.search(text)
        direction = "debit" if (dpos and cpos and dpos.start() <= cpos.start()) else "credit"
    else:
        direction = "unknown"
    if _CC_SPEND_RE.search(text) or (_CC_RE.search(text) and debit):
        direction = "debit"
    amount = _parse_amount(text)
    payee = _guess_payee(text)
    category, conf = _keyword_category(text, direction)
    method, mconf = detect_payment_method(text)
    if method == "atm" and category in {"Other", "Other income", "UPI / transfers"}:
        category = "ATM / cash"
        conf = max(conf, 0.84)
        payee = payee or "ATM"
    if method == "credit_card" and direction == "debit" and category in {"Other income", "ATM / cash"}:
        category, conf = _keyword_category(text, "debit")
        conf = max(conf, 0.75)
    if direction == "unknown":
        conf = min(conf, 0.35)
    if amount is None:
        conf = min(conf, 0.4)
    if method != "other":
        conf = max(conf, min(mconf, 0.88))
    return {
        "direction": direction,
        "amount": amount,
        "payee": payee,
        "date": _parse_txn_date(text),
        "category": category,
        "payment_method": method,
        "confidence": round(conf, 3),
        "notes": None,
        "description": build_description(method, payee, category),
        "provider": "heuristic",
    }


def hard_correct(text: str, result: dict[str, Any]) -> dict[str, Any]:
    """Sanity-fix AI/heuristic output against clear bank-alert signals."""
    out = dict(result or {})
    method, mconf = detect_payment_method(text)
    if method == "credit_card":
        out["payment_method"] = "credit_card"
        if _CC_SPEND_RE.search(text) or _DEBIT_RE.search(text):
            out["direction"] = "debit"
        if out.get("category") in {"ATM / cash", "Other income", None, ""}:
            cat, conf = _keyword_category(text, "debit")
            out["category"] = cat
            out["confidence"] = max(float(out.get("confidence") or 0), conf, mconf)
        if not out.get("payee") or str(out.get("payee")).lower() in {
            "atm", "the primary card holder", "primary card holder", "card holder",
        }:
            payee = _guess_payee(text)
            if payee:
                out["payee"] = payee
    elif method == "atm" and out.get("payment_method") not in {"credit_card", "debit_card", "upi"}:
        out["payment_method"] = "atm"
    lower = (text or "").lower()
    if "amazon" in lower and out.get("payment_method") == "credit_card":
        out["category"] = "Shopping"
        out["payee"] = out.get("payee") or _guess_payee(text) or "Amazon"
        out["direction"] = "debit"
        out["confidence"] = max(float(out.get("confidence") or 0), 0.9)
    cleaned = normalize_payee(out.get("payee"))
    if cleaned:
        out["payee"] = cleaned
    elif out.get("payee"):
        # Junk payee — try body extraction, else drop.
        out["payee"] = _guess_payee(text)

    # Strong merchant hints always win over weak/wrong AI categories.
    if _HEALTH_HINT_RE.search(text or "") or _HEALTH_HINT_RE.search(out.get("payee") or ""):
        out["category"] = "Health"
        out["confidence"] = max(float(out.get("confidence") or 0), 0.93)
        if out.get("direction") in {None, "", "unknown", "credit"} and (
            _CC_SPEND_RE.search(text or "") or _DEBIT_RE.search(text or "")
        ):
            out["direction"] = "debit"
    elif _looks_personal_upi(text, out.get("payee")) and out.get("category") in {
        "Insurance", "EMI / loans", "Subscriptions", "Other", "Other income",
        "ATM / cash", "Salary", None, "",
    }:
        out["category"] = "UPI / transfers"
        out["payment_method"] = out.get("payment_method") or "upi"
        if out.get("payment_method") == "other":
            out["payment_method"] = "upi"
        out["confidence"] = max(float(out.get("confidence") or 0), 0.86)

    # Recompute from body when AI still left a fragile EMI/Insurance tag with no real keyword.
    fragile = out.get("category") in {"EMI / loans", "Insurance"}
    if fragile:
        cat, conf = _keyword_category(text, out.get("direction") or "debit")
        if cat not in {"EMI / loans", "Insurance"} and conf >= 0.8:
            out["category"] = cat
            out["confidence"] = max(float(out.get("confidence") or 0), conf)
        elif cat in {"EMI / loans", "Insurance"}:
            # Confirm with boundary-safe keys only; otherwise drop to safer default.
            out["category"] = cat
        else:
            if method == "upi" or _UPI_RE.search(text or ""):
                out["category"] = "UPI / transfers"
            elif _HEALTH_HINT_RE.search(text or ""):
                out["category"] = "Health"
            else:
                out["category"] = "Other"
            out["confidence"] = min(float(out.get("confidence") or 0.5), 0.55)

    out["description"] = build_description(
        out.get("payment_method"), out.get("payee"), out.get("category"), out.get("notes"),
    )
    return out


def apply_rules(text: str, result: dict[str, Any], rules: list[dict[str, Any]]) -> dict[str, Any]:
    lower = text.lower()
    for rule in rules:
        needle = (rule.get("match_text") or "").strip().lower()
        if needle and needle in lower:
            if rule.get("txn_type") == "income":
                result["direction"] = "credit"
            elif rule.get("txn_type") == "expense":
                result["direction"] = "debit"
            if rule.get("category"):
                result["category"] = rule["category"]
            if rule.get("payee"):
                result["payee"] = rule["payee"]
            result["confidence"] = max(float(result.get("confidence") or 0), 0.92)
            result["provider"] = "rule"
            break
    return result


def _openai_chat(base_url: str, api_key: str | None, model: str, system: str, user: str) -> tuple[str, dict]:
    from app.ai_usage import parse_usage

    url = base_url.rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }).encode()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read().decode())
    text = data["choices"][0]["message"]["content"]
    usage = parse_usage(data)
    usage["model"] = data.get("model") or model
    return text, usage


def _anthropic_chat(api_key: str, model: str, system: str, user: str) -> tuple[str, dict]:
    from app.ai_usage import parse_usage

    body = json.dumps({
        "model": model,
        "max_tokens": 400,
        "temperature": 0.1,
        "system": system,
        "messages": [{"role": "user", "content": user}],
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
    with urllib.request.urlopen(req, timeout=25) as resp:
        data = json.loads(resp.read().decode())
    text = data["content"][0]["text"]
    usage = parse_usage(data)
    usage["model"] = data.get("model") or model
    return text, usage


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).removesuffix("```").strip()
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def classify_with_ai(
    text: str,
    kind: str,
    api_key: str | None,
    model: str | None,
    base_url: str | None,
) -> dict[str, Any]:
    model = model or DEFAULT_MODELS.get(kind, "gpt-4o-mini")
    base = (base_url or DEFAULT_BASES.get(kind) or "https://api.openai.com/v1").rstrip("/")
    system = (
        "You classify bank SMS, UPI, wallet, card, and ATM alerts. "
        "Return JSON only with keys: direction (debit|credit|unknown), "
        "amount (number or null), payee (string or null), date (YYYY-MM-DD or null), "
        f"category (one of {ALL_CATEGORIES}), "
        f"payment_method (one of {list(PAYMENT_METHODS)}), "
        "confidence (0-1), notes (short description). "
        "debit = payment/expense/card spend/ATM withdrawal. credit = money received/refund. "
        "IMPORTANT: A credit-card spend ('Credit Card … used for a transaction', Info: MERCHANT) "
        "is direction=debit and payment_method=credit_card. Never call that income or atm. "
        "Ignore phrases like Available Credit Limit when deciding direction. "
        "Payee should be the merchant from Info:/at:/towards VPA, e.g. AMAZON PAY. "
        "Category from the MERCHANT, not email footers: "
        "names containing medical/hospital/clinic/pharma → Health (never EMI / loans); "
        "person UPI VPAs like name@oksbi / name@ybl → UPI / transfers (never Insurance); "
        "EMI / loans only for real loan/EMI payments; Insurance only for insurers/premiums. "
        "Ignore 'click here', Convert to EMI ads, and marketing footers."
    )
    user = f"Message:\n{text}"
    usage: dict[str, Any] = {}
    if kind == "anthropic":
        if not api_key:
            raise ValueError("Anthropic needs an API key")
        raw, usage = _anthropic_chat(api_key, model, system, user)
    else:
        raw, usage = _openai_chat(base, api_key, model, system, user)
    data = _extract_json(raw)
    direction = str(data.get("direction") or "unknown").lower()
    if direction not in {"debit", "credit", "unknown"}:
        direction = "unknown"
    cat = data.get("category") or "Other"
    if cat not in ALL_CATEGORIES:
        cat = "Other income" if direction == "credit" else "Other"
    amount = data.get("amount")
    try:
        amount = float(amount) if amount is not None and amount != "" else None
    except (TypeError, ValueError):
        amount = None
    conf = data.get("confidence")
    try:
        conf = max(0.0, min(1.0, float(conf)))
    except (TypeError, ValueError):
        conf = 0.6
    method = str(data.get("payment_method") or "other").lower().replace(" ", "_")
    if method not in PAYMENT_METHODS:
        method, _ = detect_payment_method(text)
    notes = data.get("notes")
    notes = str(notes).strip()[:200] if notes else None
    return {
        "direction": direction,
        "amount": amount,
        "payee": normalize_payee(str(data["payee"])[:80] if data.get("payee") else None) or _guess_payee(text),
        "date": data.get("date") or _parse_txn_date(text),
        "category": cat,
        "payment_method": method,
        "confidence": round(conf, 3),
        "notes": notes,
        "description": build_description(method, data.get("payee"), cat, notes),
        "provider": kind,
        "_usage": usage,
        "_raw": (raw or "")[:4000],
    }


def classify_message(
    text: str,
    rules: list[dict[str, Any]] | None = None,
    ai: dict[str, Any] | None = None,
) -> dict[str, Any]:
    import time
    from app.ai_usage import maybe_log_from_ai_result

    result = classify_heuristic(text)
    result = apply_rules(text, result, rules or [])
    if result.get("provider") == "rule":
        return hard_correct(text, result)
    if not ai:
        return hard_correct(text, result)
    started = time.monotonic()
    try:
        ai_result = classify_with_ai(
            text,
            kind=ai.get("kind") or "openai",
            api_key=ai.get("api_key"),
            model=ai.get("model"),
            base_url=ai.get("base_url"),
        )
        latency = int((time.monotonic() - started) * 1000)
        maybe_log_from_ai_result(
            ai, ai_result, latency_ms=latency, ok=True,
            request_text=text,
            response_text=ai_result.get("_raw") or json.dumps({
                "direction": ai_result.get("direction"),
                "amount": ai_result.get("amount"),
                "payee": ai_result.get("payee"),
                "category": ai_result.get("category"),
                "payment_method": ai_result.get("payment_method"),
                "confidence": ai_result.get("confidence"),
            }, ensure_ascii=False),
        )
        if float(ai_result.get("confidence") or 0) >= float(result.get("confidence") or 0):
            result = ai_result
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError, json.JSONDecodeError) as exc:
        latency = int((time.monotonic() - started) * 1000)
        maybe_log_from_ai_result(
            ai, {"_usage": {}, "provider": ai.get("kind")},
            latency_ms=latency, ok=False, error=str(exc)[:200],
            request_text=text,
        )
        result["ai_error"] = True
    return hard_correct(text, result)


def test_provider(kind: str, api_key: str | None, model: str | None, base_url: str | None) -> tuple[str, dict]:
    sample = "Dear Customer, Rs.199.00 debited via UPI to NETFLIX on 13-08-2026."
    out = classify_with_ai(sample, kind, api_key, model, base_url)
    text = f"{out.get('direction')} {out.get('amount')} {out.get('category')}"
    return text, out.get("_usage") or {}
