"""Persistent AI usage logs — client, model, request/response tokens, time."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app import models
from app.deps import vault_id

CLIENT_LABELS = {
    "ask_ai": "Ask AI",
    "finance_sms": "Money Manager SMS",
    "expense_analyser": "Expense Analyser",
    "connection_test": "Connection test",
    "provider_test": "Provider test",
}


def _uid(user: models.User) -> str:
    return vault_id(user)


def _int(val) -> int | None:
    if val is None or val == "":
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def parse_usage(data: dict | None) -> dict:
    """Normalize OpenAI / Anthropic / OpenRouter usage blocks."""
    usage = (data or {}).get("usage") or {}
    prompt = _int(usage.get("prompt_tokens") if usage.get("prompt_tokens") is not None else usage.get("input_tokens"))
    completion = _int(
        usage.get("completion_tokens") if usage.get("completion_tokens") is not None else usage.get("output_tokens")
    )
    total = _int(usage.get("total_tokens"))
    if total is None and prompt is not None and completion is not None:
        total = prompt + completion
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
    }


def record(
    db: Session,
    user: models.User,
    *,
    client: str,
    provider_name: str | None = None,
    provider_kind: str | None = None,
    model: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    latency_ms: int | None = None,
    ok: bool = True,
    error: str | None = None,
) -> models.AiUsageLog | None:
    """Attach a usage row to the caller's session (flush via SAVEPOINT).

    Same session avoids SQLite lock conflicts; nested transaction keeps a log
    failure from wiping the caller's pending work.
    """
    if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
        total_tokens = prompt_tokens + completion_tokens
    row = models.AiUsageLog(
        user_id=_uid(user),
        client=(client or "unknown")[:40],
        provider_name=(provider_name or None),
        provider_kind=(provider_kind or None),
        model=(model or None),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
        ok=bool(ok),
        error=(error or None)[:500] if error else None,
        created_at=datetime.utcnow(),
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
        return row
    except Exception:
        return None


def attach_log_context(bundle: dict | None, db: Session, user: models.User, client: str) -> dict | None:
    """Copy a provider bundle and mark it so classify_message can write usage rows."""
    if not bundle:
        return None
    out = dict(bundle)
    out["_db"] = db
    out["_user"] = user
    out["_client"] = client
    return out


def maybe_log_from_ai_result(ai: dict | None, result: dict, *, latency_ms: int | None = None, ok: bool = True, error: str | None = None) -> None:
    if not ai:
        return
    db = ai.get("_db")
    user = ai.get("_user")
    client = ai.get("_client")
    if not db or not user or not client:
        return
    usage = result.get("_usage") or {}
    record(
        db, user,
        client=client,
        provider_name=ai.get("name"),
        provider_kind=ai.get("kind") or result.get("provider"),
        model=ai.get("model") or usage.get("model"),
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
        total_tokens=usage.get("total_tokens"),
        latency_ms=latency_ms,
        ok=ok,
        error=error,
    )


def list_logs(
    db: Session,
    user: models.User,
    *,
    limit: int = 100,
    offset: int = 0,
    client: str | None = None,
) -> list[models.AiUsageLog]:
    q = db.query(models.AiUsageLog).filter(models.AiUsageLog.user_id == _uid(user))
    if client:
        q = q.filter(models.AiUsageLog.client == client)
    return (
        q.order_by(models.AiUsageLog.created_at.desc())
        .offset(max(0, offset))
        .limit(max(1, min(500, limit)))
        .all()
    )


def count_logs(db: Session, user: models.User, *, client: str | None = None) -> int:
    q = db.query(models.AiUsageLog).filter(models.AiUsageLog.user_id == _uid(user))
    if client:
        q = q.filter(models.AiUsageLog.client == client)
    return int(q.count() or 0)


def summary(db: Session, user: models.User, *, days: int = 30) -> dict:
    since = datetime.utcnow() - timedelta(days=max(1, days))
    rows = (
        db.query(models.AiUsageLog)
        .filter(models.AiUsageLog.user_id == _uid(user), models.AiUsageLog.created_at >= since)
        .all()
    )
    by_client: dict[str, int] = {}
    prompt = completion = total = 0
    ok_n = fail_n = 0
    for r in rows:
        by_client[r.client] = by_client.get(r.client, 0) + 1
        prompt += r.prompt_tokens or 0
        completion += r.completion_tokens or 0
        total += r.total_tokens or 0
        if r.ok:
            ok_n += 1
        else:
            fail_n += 1
    return {
        "days": days,
        "calls": len(rows),
        "ok": ok_n,
        "failed": fail_n,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "by_client": by_client,
    }


def log_out(row: models.AiUsageLog) -> dict:
    return {
        "id": row.id,
        "client": row.client,
        "client_label": CLIENT_LABELS.get(row.client, row.client),
        "provider_name": row.provider_name,
        "provider_kind": row.provider_kind,
        "model": row.model,
        "prompt_tokens": row.prompt_tokens,
        "completion_tokens": row.completion_tokens,
        "total_tokens": row.total_tokens,
        "latency_ms": row.latency_ms,
        "ok": bool(row.ok),
        "error": row.error,
        "created_at": row.created_at,
    }
