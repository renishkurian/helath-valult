"""Canonical module keys and per-user enable/disable (Super Admin).

``User.enabled_modules`` stores a JSON list of allowed keys.
``null`` / empty / invalid → all default modules are allowed.
Viewers inherit the vault owner's list. Super Admin always sees every module
plus the control plane.
"""
from __future__ import annotations

import json
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app import models

# Keys used in web sidebar, module picker, Android hub, and API guards.
DEFAULT_MODULE_KEYS: tuple[str, ...] = (
    "health",
    "passwords",
    "finance",
    "expense",
    "ai",
    "locker",
    "tracker",
    "urls",
    "diary",
)

MODULE_LABELS: dict[str, str] = {
    "health": "Health Vault",
    "passwords": "Password Vault",
    "finance": "Money Manager",
    "expense": "Expense Analyser",
    "ai": "AI",
    "locker": "Document Vault",
    "tracker": "Shopping List",
    "urls": "URL Vault",
    "diary": "Digital Diary",
}

# Admin HTML path prefix → module key (longest prefixes first).
ADMIN_PREFIX_MODULES: tuple[tuple[str, str], ...] = (
    ("/admin/expense-analyser", "expense"),
    ("/admin/passwords", "passwords"),
    ("/admin/finance", "finance"),
    ("/admin/locker", "locker"),
    ("/admin/tracker", "tracker"),
    ("/admin/urls", "urls"),
    ("/admin/diary", "diary"),
    ("/admin/ai", "ai"),
    ("/admin/sa", "superadmin"),
)

# API path prefix → module key.
API_PREFIX_MODULES: tuple[tuple[str, str], ...] = (
    ("/expense-analyser", "expense"),
    ("/finance", "finance"),
    ("/locker", "locker"),
    ("/tracker", "tracker"),
    ("/urls", "urls"),
    ("/diary", "diary"),
    ("/vault", "passwords"),
    ("/ai", "ai"),
    # Health module surfaces (people, documents, …) share "health"
    ("/people", "health"),
    ("/cards", "health"),
    ("/documents", "health"),
    ("/reminders", "health"),
    ("/search", "health"),
    ("/share", "health"),
    ("/labs", "health"),
    ("/health", "health"),
    ("/storage", "health"),
    ("/audit", "health"),
    ("/backup", "health"),
)


def parse_enabled_modules(raw: Optional[str]) -> Optional[list[str]]:
    """Return a sanitized list, or None meaning 'all defaults'."""
    if raw is None or not str(raw).strip():
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, list):
        return None
    allowed = {k for k in DEFAULT_MODULE_KEYS}
    out = [str(x) for x in data if str(x) in allowed]
    return out if out else None


def serialize_enabled_modules(keys: Optional[Iterable[str]]) -> Optional[str]:
    if keys is None:
        return None
    allowed = {k for k in DEFAULT_MODULE_KEYS}
    cleaned = [k for k in keys if k in allowed]
    if not cleaned or set(cleaned) == set(DEFAULT_MODULE_KEYS):
        return None
    return json.dumps(cleaned)


def _owner_row(db: Session, user: models.User) -> models.User:
    oid = user.vault_owner_id or user.id
    if oid == user.id:
        return user
    owner = db.query(models.User).filter(models.User.id == oid).first()
    return owner or user


def enabled_keys(db: Session, user: models.User) -> list[str]:
    """Module keys this login may open (always includes superadmin for SA)."""
    role = user.role or models.UserRole.owner.value
    if role == models.UserRole.superadmin.value:
        return list(DEFAULT_MODULE_KEYS) + ["superadmin"]

    source = _owner_row(db, user)
    parsed = parse_enabled_modules(getattr(source, "enabled_modules", None))
    keys = list(parsed) if parsed is not None else list(DEFAULT_MODULE_KEYS)
    return keys


def is_enabled(db: Session, user: models.User, module_key: str) -> bool:
    if module_key == "superadmin":
        return (user.role or "") == models.UserRole.superadmin.value
    return module_key in enabled_keys(db, user)


def admin_module_for_path(path: str) -> Optional[str]:
    """Return module key for an /admin path, or None if ungated (login, modules, …)."""
    if not path.startswith("/admin"):
        return None
    # Shared shell / auth — always allowed when logged in
    if path in ("/admin", "/admin/", "/admin/modules", "/admin/login", "/admin/logout", "/admin/signup"):
        # Dashboard home is health
        if path in ("/admin", "/admin/"):
            return "health"
        return None
    if path.startswith("/admin/login") or path.startswith("/admin/logout") or path.startswith("/admin/signup"):
        return None
    # Other health admin pages (family, care, …) without a dedicated prefix
    health_only = (
        "/admin/family", "/admin/reminders", "/admin/care", "/admin/shares",
        "/admin/activity", "/admin/storage", "/admin/security", "/admin/people",
        "/admin/documents", "/admin/cards", "/admin/upload", "/admin/search",
        "/admin/health-settings", "/admin/trash",
    )
    for prefix, key in ADMIN_PREFIX_MODULES:
        if path == prefix or path.startswith(prefix + "/"):
            return key
    for hp in health_only:
        if path == hp or path.startswith(hp + "/"):
            return "health"
    if path.startswith("/admin/") and not path.startswith("/admin/sa"):
        # Unknown admin path under health by default
        return "health"
    return None


def api_module_for_path(path: str) -> Optional[str]:
    for prefix, key in API_PREFIX_MODULES:
        if path == prefix or path.startswith(prefix + "/"):
            return key
    return None
