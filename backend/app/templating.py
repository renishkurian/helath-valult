from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_RELATION_LABELS = {
    "self": "You",
    "spouse": "Spouse",
    "child": "Child",
    "parent": "Parent",
    "other": "Other",
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
    return " ".join(part[:1].upper() + part[1:] if part else part for part in text.split())


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


def setup_templates() -> Jinja2Templates:
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    templates.env.filters["nice"] = nice_name
    templates.env.filters["relabel"] = relation_label
    templates.env.filters["enum_value"] = enum_value
    return templates
