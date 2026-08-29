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


def set_default_provider(db: Session, user: models.User, provider_id: str) -> models.AiProvider | None:
    uid = _uid(user)
    row = get_provider(db, user, provider_id)
    if not row:
        return None
    db.query(models.AiProvider).filter(models.AiProvider.user_id == uid).update({"is_default": False})
    row.is_default = True
    row.enabled = True
    db.commit()
    db.refresh(row)
    return row


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
    import time
    from app import ai_usage

    row = get_provider(db, user, provider_id)
    if not row:
        raise LookupError("Provider not found")
    started = time.monotonic()
    try:
        sample, usage = test_provider(
            row.kind,
            crypto.decrypt_text(row.api_key_enc) if row.api_key_enc else None,
            row.model,
            row.base_url,
        )
        latency = int((time.monotonic() - started) * 1000)
        ai_usage.record(
            db, user,
            client="provider_test",
            provider_name=row.name,
            provider_kind=row.kind,
            model=usage.get("model") or row.model,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            latency_ms=latency,
            ok=True,
            request_text="Dear Customer, Rs.199.00 debited via UPI to NETFLIX on 13-08-2026.",
            response_text=sample,
        )
        return sample
    except Exception as exc:
        latency = int((time.monotonic() - started) * 1000)
        ai_usage.record(
            db, user,
            client="provider_test",
            provider_name=row.name,
            provider_kind=row.kind,
            model=row.model,
            latency_ms=latency,
            ok=False,
            error=str(exc)[:200],
            request_text="Dear Customer, Rs.199.00 debited via UPI to NETFLIX on 13-08-2026.",
        )
        raise


def test_default_connection(db: Session, user: models.User) -> dict:
    """Ping the default provider with a tiny chat completion (Ask AI path)."""
    import time
    from app import ai_usage
    from app.ai_chat import complete_chat

    bundle = get_default_bundle(db, user)
    if not bundle:
        raise LookupError("Add an AI provider first")
    started = time.monotonic()
    try:
        result = complete_chat(
            kind=bundle["kind"],
            api_key=bundle.get("api_key"),
            model=bundle.get("model"),
            base_url=bundle.get("base_url"),
            system="You are a connection probe. Reply with exactly one word: pong",
            messages=[{"role": "user", "content": "ping"}],
        )
        latency = int((time.monotonic() - started) * 1000)
        reply = (result.get("content") or "").strip()
        if not reply:
            raise ValueError("Provider returned an empty reply")
        ai_usage.record(
            db, user,
            client="connection_test",
            provider_name=bundle.get("name"),
            provider_kind=bundle.get("kind"),
            model=result.get("model") or bundle.get("model"),
            prompt_tokens=result.get("prompt_tokens"),
            completion_tokens=result.get("completion_tokens"),
            total_tokens=result.get("total_tokens"),
            latency_ms=latency,
            ok=True,
            request_text="ping",
            response_text=reply,
        )
        return {
            "ok": True,
            "name": bundle.get("name"),
            "kind": bundle.get("kind"),
            "model": result.get("model") or bundle.get("model"),
            "sample": reply[:160],
            "prompt_tokens": result.get("prompt_tokens"),
            "completion_tokens": result.get("completion_tokens"),
            "total_tokens": result.get("total_tokens"),
        }
    except Exception as exc:
        latency = int((time.monotonic() - started) * 1000)
        ai_usage.record(
            db, user,
            client="connection_test",
            provider_name=bundle.get("name"),
            provider_kind=bundle.get("kind"),
            model=bundle.get("model"),
            latency_ms=latency,
            ok=False,
            error=str(exc)[:200],
            request_text="ping",
        )
        raise


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
        "default_id": default.id if default else None,
        "default_model": default.model if default else None,
    }
