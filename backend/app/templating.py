from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.finance_ai import PAYMENT_LABELS

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_RELATION_LABELS = {
    "self": "You",
    "spouse": "Spouse",
    "child": "Child",
    "parent": "Parent",
    "other": "Other",
}

_TAG_LABELS = {
    "alert": "Alert",
    "bill": "Statement",
    "bill_line": "Bill line",
    "pending": "Pending",
    "matched": "Matched",
    "corrected": "Corrected",
    "posted": "Posted",
    "ignored": "Ignored",
    "missed": "Missed",
    "manual": "Manual",
    "scheduled": "Scheduled",
    "approved": "Approved",
    "pending": "Pending",
    "debit": "Debit",
    "credit": "Credit",
    **PAYMENT_LABELS,
}


def nice_name(value) -> str:
    """Display names in title case. Leaves emails and filenames alone."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if "@" in text:
        return text
    if "." in text and " " not in text:
        return text
    text = text.replace("_", " ")
    return " ".join(part[:1].upper() + part[1:] if part else part for part in text.split())


def labelize(value) -> str:
    """Human labels for snake_case tags (credit_card → Credit card)."""
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    if text in _TAG_LABELS:
        return _TAG_LABELS[text]
    return nice_name(text.replace("-", "_"))


def enum_value(value) -> str:
    if value is None:
        return ""
    if hasattr(value, "value"):
        return str(value.value)
    text = str(value)
    if text.startswith("Relation."):
        text = text.split(".", 1)[1]
    return text.rstrip("_")


def relation_label(value) -> str:
    key = enum_value(value)
    if not key:
        return ""
    return _RELATION_LABELS.get(key, key.replace("_", " ").title())


def phone_digits(value) -> str:
    """Digits only for tel: / WhatsApp wa.me links."""
    if value is None:
        return ""
    return "".join(ch for ch in str(value) if ch.isdigit())


def setup_templates() -> Jinja2Templates:
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.filters["nice"] = nice_name
    templates.env.filters["labelize"] = labelize
    templates.env.filters["relabel"] = relation_label
    templates.env.filters["enum_value"] = enum_value
    templates.env.filters["phone_digits"] = phone_digits
    return templates
