"""Per-vault encrypted storage quota.

Admins set a total byte limit per vault owner (any number of files, sum ≤ quota).
Default is 100 MiB. Viewers share the owner's vault and quota.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models
from app.config import settings
from app.deps import vault_id

DEFAULT_QUOTA_BYTES = 100 * 1024 * 1024  # 100 MiB
MIN_QUOTA_BYTES = 1 * 1024 * 1024  # 1 MiB floor for admin edits
MAX_QUOTA_BYTES = 1024 * 1024 * 1024 * 1024  # 1 TiB ceiling


def mb_to_bytes(mb: float | int | str) -> int:
    try:
        n = float(mb)
    except (TypeError, ValueError):
        return DEFAULT_QUOTA_BYTES
    if n <= 0:
        return DEFAULT_QUOTA_BYTES
    return int(n * 1024 * 1024)


def bytes_to_mb(n: int | None) -> float:
    return round((n or 0) / (1024 * 1024), 1)


def format_bytes(n: int | None) -> str:
    try:
        size = float(n or 0)
    except (TypeError, ValueError):
        return "0 B"
    if size <= 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} B"
            if size >= 100 or unit == "KB":
                return f"{size:.0f} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{int(n or 0)} B"


def vault_owner(db: Session, user: models.User) -> models.User:
    """Quota lives on the vault owner row (viewers share it)."""
    vid = vault_id(user)
    if vid == user.id:
        return user
    owner = db.query(models.User).filter(models.User.id == vid).first()
    return owner or user


def effective_quota_bytes(user: models.User) -> int:
    raw = getattr(user, "storage_quota_bytes", None)
    try:
        n = int(raw) if raw is not None else DEFAULT_QUOTA_BYTES
    except (TypeError, ValueError):
        n = DEFAULT_QUOTA_BYTES
    if n <= 0:
        return DEFAULT_QUOTA_BYTES
    return n


def vault_bytes_used(user: models.User) -> tuple[int, int]:
    """Return (bytes_used, file_count) for the vault storage directory."""
    root = settings.STORAGE_DIR / vault_id(user)
    total = 0
    count = 0
    if root.exists():
        for p in root.rglob("*"):
            if p.is_file():
                try:
                    total += p.stat().st_size
                    count += 1
                except OSError:
                    continue
    return total, count


def quota_snapshot(db: Session, user: models.User) -> dict:
    owner = vault_owner(db, user)
    used, files = vault_bytes_used(owner)
    limit = effective_quota_bytes(owner)
    remaining = max(0, limit - used)
    return {
        "bytes_used": used,
        "file_count": files,
        "quota_bytes": limit,
        "remaining_bytes": remaining,
        "quota_mb": bytes_to_mb(limit),
        "used_mb": bytes_to_mb(used),
        "pct": min(100, int(round((used / limit) * 100))) if limit else 100,
        "over_quota": used > limit,
    }


def assert_can_store(db: Session, user: models.User, add_bytes: int) -> None:
    """Raise 413 if storing add_bytes would exceed the vault quota."""
    try:
        need = int(add_bytes or 0)
    except (TypeError, ValueError):
        need = 0
    if need <= 0:
        return
    snap = quota_snapshot(db, user)
    if snap["bytes_used"] + need <= snap["quota_bytes"]:
        return
    raise HTTPException(
        status_code=413,
        detail=(
            f"Storage quota exceeded. "
            f"Used {format_bytes(snap['bytes_used'])} of {format_bytes(snap['quota_bytes'])}; "
            f"this upload needs {format_bytes(need)}. "
            f"Ask a super admin to raise your limit, or delete unused files."
        ),
    )


def set_quota_bytes(db: Session, owner: models.User, quota_bytes: int) -> int:
    n = int(quota_bytes)
    n = max(MIN_QUOTA_BYTES, min(MAX_QUOTA_BYTES, n))
    owner.storage_quota_bytes = n
    db.commit()
    db.refresh(owner)
    return n
