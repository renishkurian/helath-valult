"""Shared vault AI providers — one encrypted key store for every module."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app import crypto, models
from app.deps import vault_id
from app.finance_ai import DEFAULT_BASES, DEFAULT_MODELS, test_provider

PROVIDER_KINDS = ("openai", "anthropic", "openrouter", "kimi", "groq", "ollama", "custom")


def _uid(user: models.User) -> str:
    return vault_id(user)


def list_providers(db: Session, user: models.User) -> list[models.AiProvider]:
    return (
        db.query(models.AiProvider)
        .filter(models.AiProvider.user_id == _uid(user))
        .order_by(models.AiProvider.created_at.desc())
        .all()
    )


def get_provider(db: Session, user: models.User, provider_id: str) -> models.AiProvider | None:
    return (
        db.query(models.AiProvider)
        .filter(models.AiProvider.id == provider_id, models.AiProvider.user_id == _uid(user))
        .first()
    )


def create_provider(
    db: Session,
    user: models.User,
    *,
    name: str,
    kind: str,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    is_default: bool = False,
) -> models.AiProvider:
    uid = _uid(user)
    kind = (kind or "openai").strip().lower()
    if kind not in PROVIDER_KINDS:
        kind = "custom"
    if is_default:
        db.query(models.AiProvider).filter(models.AiProvider.user_id == uid).update({"is_default": False})
    row = models.AiProvider(
        user_id=uid,
        name=(name or "").strip() or kind,
        kind=kind,
        api_key_enc=crypto.encrypt_text(api_key) if api_key else None,
        base_url=base_url or DEFAULT_BASES.get(kind),
        model=model or DEFAULT_MODELS.get(kind),
        is_default=bool(is_default),
        enabled=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def delete_provider(db: Session, user: models.User, provider_id: str) -> bool:
    row = get_provider(db, user, provider_id)
    if not row:
        return False
    db.delete(row)
    db.commit()
    return True


def provider_out(row: models.AiProvider) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "kind": row.kind,
        "base_url": row.base_url,
        "model": row.model,
        "is_default": bool(row.is_default),
        "enabled": bool(row.enabled),
        "has_key": bool(row.api_key_enc),
    }


def get_default_bundle(db: Session, user: models.User) -> dict | None:
    """Decrypt the default (or first enabled) provider for classify/chat callers."""
    uid = _uid(user)
    row = (
        db.query(models.AiProvider)
        .filter(
            models.AiProvider.user_id == uid,
            models.AiProvider.enabled.is_(True),
            models.AiProvider.is_default.is_(True),
        )
        .first()
    )
    if not row:
        row = (
            db.query(models.AiProvider)
            .filter(models.AiProvider.user_id == uid, models.AiProvider.enabled.is_(True))
            .first()
        )
    if not row:
        return None
    return {
        "kind": row.kind,
        "api_key": crypto.decrypt_text(row.api_key_enc) if row.api_key_enc else None,
        "model": row.model,
        "base_url": row.base_url,
        "name": row.name,
    }


def test_provider_row(db: Session, user: models.User, provider_id: str) -> str:
    row = get_provider(db, user, provider_id)
    if not row:
        raise LookupError("Provider not found")
    return test_provider(
        row.kind,
        crypto.decrypt_text(row.api_key_enc) if row.api_key_enc else None,
        row.model,
        row.base_url,
    )


def status_summary(db: Session, user: models.User) -> dict:
    rows = list_providers(db, user)
    default = next((r for r in rows if r.is_default and r.enabled), None) or next(
        (r for r in rows if r.enabled), None
    )
    return {
        "count": len(rows),
        "has_default": bool(default),
        "default_name": default.name if default else None,
        "default_kind": default.kind if default else None,
    }
