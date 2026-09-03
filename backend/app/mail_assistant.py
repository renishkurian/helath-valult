"""AI-assisted Gmail browser for Expense Analyser.

Reuses the same read-only Gmail connection already wired up for bank-alert
sync (see app/expense_analyser.py + app/gmail.py) — no extra OAuth scope,
no send capability. AI tasks (natural-language search, reply drafting) run
through the vault's existing AI provider (app/ai_providers.py) and are
logged via app/ai_usage.py like every other AI feature in the app.
"""
from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from app import ai_usage, expense_analyser as ea, gmail, models
from app.ai_chat import complete_chat
from app.ai_providers import get_default_bundle

DEFAULT_LIST_QUERY = "in:inbox"
_REPLY_CLIENT = "expense_analyser_mail_reply"
_SEARCH_CLIENT = "expense_analyser_mail_search"


def _token(db: Session, user: models.User) -> str:
    row = ea.get_or_create(db, user)
    if not row.refresh_token_enc:
        raise RuntimeError("Connect Gmail first (Expense Analyser → Gmail & sync).")
    return ea._access_token(db, row)


def _bundle(db: Session, user: models.User) -> dict:
    bundle = get_default_bundle(db, user)
    if not bundle:
        raise RuntimeError("No AI provider configured. Add one under AI → Providers.")
    return bundle


def _summarize(mail: dict[str, Any]) -> dict[str, Any]:
    received = mail.get("received_at")
    return {
        "id": mail.get("id"),
        "thread_id": mail.get("thread_id"),
        "subject": (mail.get("subject") or "(no subject)").strip(),
        "from_addr": (mail.get("from_addr") or "").strip(),
        "received_at": received.isoformat() if received else None,
        "snippet": (mail.get("snippet") or "").strip(),
    }


def list_mail(
    db: Session,
    user: models.User,
    *,
    query: str | None = None,
    limit: int = 25,
    page_token: str | None = None,
) -> dict[str, Any]:
    """List inbox mail (any mail, not just bank alerts) via the shared Gmail token."""
    token = _token(db, user)
    q = (query or DEFAULT_LIST_QUERY).strip() or DEFAULT_LIST_QUERY
    ids, next_token = gmail.list_message_ids(
        token, q, max_results=max(1, min(50, limit)), page_token=page_token,
    )
    items: list[dict[str, Any]] = []
    for mid in ids:
        try:
            payload = gmail.get_message(token, mid)
        except Exception:  # noqa: BLE001 — skip a single bad message, keep the list going
            continue
        items.append(_summarize(gmail.extract_message(payload)))
    return {"items": items, "next_page_token": next_token, "query": q}


def get_mail_detail(db: Session, user: models.User, message_id: str) -> dict[str, Any]:
    token = _token(db, user)
    payload = gmail.get_message(token, message_id)
    mail = gmail.extract_message(payload)
    mail = gmail.hydrate_message_text(token, mail)
    out = _summarize(mail)
    out["text"] = (mail.get("text") or "").strip()[:6000]
    return out


_QUERY_SYSTEM = (
    "Translate the user's request into a single Gmail search query using Gmail search "
    "operators only (from:, to:, subject:, newer_than:, older_than:, after:, before:, "
    "is:unread, is:read, has:attachment, label:, in:inbox, etc). "
    "Reply with ONLY the raw query string on one line — no quotes, no markdown, no explanation."
)


def natural_query_to_gmail(db: Session, user: models.User, question: str) -> str:
    """Turn a plain-language ask ('unread mail from the bank last week') into a Gmail query."""
    question = (question or "").strip()
    if not question:
        return DEFAULT_LIST_QUERY
    bundle = _bundle(db, user)
    started = time.monotonic()
    try:
        result = complete_chat(
            kind=bundle["kind"], api_key=bundle.get("api_key"), model=bundle.get("model"),
            base_url=bundle.get("base_url"), system=_QUERY_SYSTEM,
            messages=[{"role": "user", "content": question}],
        )
        query = (result.get("content") or "").strip().strip('"').splitlines()[0].strip()
        ai_usage.record(
            db, user, client=_SEARCH_CLIENT,
            provider_name=bundle.get("name"), provider_kind=bundle.get("kind"),
            model=result.get("model") or bundle.get("model"),
            prompt_tokens=result.get("prompt_tokens"),
            completion_tokens=result.get("completion_tokens"),
            total_tokens=result.get("total_tokens"),
            latency_ms=int((time.monotonic() - started) * 1000),
            ok=True, request_text=question, response_text=query,
        )
        return query or question
    except Exception as exc:  # noqa: BLE001
        ai_usage.record(
            db, user, client=_SEARCH_CLIENT,
            provider_name=bundle.get("name"), provider_kind=bundle.get("kind"),
            model=bundle.get("model"),
            latency_ms=int((time.monotonic() - started) * 1000),
            ok=False, error=str(exc)[:200], request_text=question,
        )
        # Fall back to a plain full-text search rather than failing the whole request.
        return question


def search_mail(db: Session, user: models.User, question: str, *, limit: int = 25) -> dict[str, Any]:
    gmail_query = natural_query_to_gmail(db, user, question)
    out = list_mail(db, user, query=gmail_query, limit=limit)
    out["asked"] = question
    return out


_REPLY_SYSTEM = (
    "You draft concise, polite email replies on the user's behalf. "
    "Write only the reply body — no subject line, no square-bracket placeholders, "
    "keep the tone professional but warm, and keep it short unless the email needs detail."
)


def draft_reply(db: Session, user: models.User, message_id: str, *, instructions: str = "") -> dict[str, Any]:
    """Generate a reply draft with AI. Nothing is sent — Gmail access here is read-only."""
    mail = get_mail_detail(db, user, message_id)
    bundle = _bundle(db, user)
    prompt = (
        f"Original email\nFrom: {mail['from_addr']}\nSubject: {mail['subject']}\n\n"
        f"{mail['text'] or '(no body text found)'}\n\n"
        f"Instructions for the reply: {instructions.strip() or '(none — write a sensible reply)'}"
    )
    started = time.monotonic()
    try:
        result = complete_chat(
            kind=bundle["kind"], api_key=bundle.get("api_key"), model=bundle.get("model"),
            base_url=bundle.get("base_url"), system=_REPLY_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        reply = (result.get("content") or "").strip()
        ai_usage.record(
            db, user, client=_REPLY_CLIENT,
            provider_name=bundle.get("name"), provider_kind=bundle.get("kind"),
            model=result.get("model") or bundle.get("model"),
            prompt_tokens=result.get("prompt_tokens"),
            completion_tokens=result.get("completion_tokens"),
            total_tokens=result.get("total_tokens"),
            latency_ms=int((time.monotonic() - started) * 1000),
            ok=True, request_text=prompt, response_text=reply,
        )
    except Exception as exc:  # noqa: BLE001
        ai_usage.record(
            db, user, client=_REPLY_CLIENT,
            provider_name=bundle.get("name"), provider_kind=bundle.get("kind"),
            model=bundle.get("model"),
            latency_ms=int((time.monotonic() - started) * 1000),
            ok=False, error=str(exc)[:200], request_text=prompt,
        )
        raise RuntimeError(f"AI provider error: {exc}") from exc
    return {
        "message_id": message_id,
        "subject": mail["subject"],
        "from_addr": mail["from_addr"],
        "reply": reply,
    }
