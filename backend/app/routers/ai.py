"""Shared AI providers API — vault-wide LLM keys for every module."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import ai_chat, ai_providers as ap
from app import models, schemas
from app.database import get_db
from app.deps import require_enabled_module, get_current_user, require_owner

router = APIRouter(prefix="/ai", tags=["ai"], dependencies=[Depends(require_enabled_module("ai"))])


def _out(row: models.AiProvider) -> schemas.AiProviderOut:
    return schemas.AiProviderOut(**ap.provider_out(row))


@router.get("/status", response_model=schemas.AiStatusOut)
def status(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    return schemas.AiStatusOut(**ap.status_summary(db, current_user))


@router.get("/providers", response_model=list[schemas.AiProviderOut])
def list_providers(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    return [_out(r) for r in ap.list_providers(db, current_user)]


@router.post("/providers", response_model=schemas.AiProviderOut)
def create_provider(
    body: schemas.AiProviderIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = ap.create_provider(
        db, current_user,
        name=body.name, kind=body.kind, api_key=body.api_key,
        base_url=body.base_url, model=body.model, is_default=body.is_default,
    )
    return _out(row)


@router.post("/providers/{provider_id}/default", response_model=schemas.AiProviderOut)
def set_default_provider(
    provider_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = ap.set_default_provider(db, current_user, provider_id)
    if not row:
        raise HTTPException(404, "Provider not found")
    return _out(row)


@router.put("/providers/{provider_id}", response_model=schemas.AiProviderOut)
@router.patch("/providers/{provider_id}", response_model=schemas.AiProviderOut)
def update_provider(
    provider_id: str,
    body: schemas.AiProviderIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    row = ap.update_provider(
        db, current_user, provider_id,
        name=body.name, kind=body.kind, api_key=body.api_key,
        keep_existing_key=(body.api_key is None),
        base_url=body.base_url, model=body.model, is_default=body.is_default,
    )
    if not row:
        raise HTTPException(404, "Provider not found")
    return _out(row)


@router.delete("/providers/{provider_id}")
def delete_provider(
    provider_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    if not ap.delete_provider(db, current_user, provider_id):
        raise HTTPException(404, "Provider not found")
    return {"ok": True}


@router.post("/providers/{provider_id}/test")
def test_provider(
    provider_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    try:
        sample = ap.test_provider_row(db, current_user, provider_id)
        return {"ok": True, "sample": sample}
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, f"Provider test failed: {exc}") from exc


@router.post("/test", response_model=schemas.AiConnectionTestOut)
def test_default_connection(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Ping the vault default provider with a chat completion (Ask AI path)."""
    require_owner(current_user)
    try:
        return schemas.AiConnectionTestOut(**ap.test_default_connection(db, current_user))
    except LookupError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, f"Connection failed: {exc}") from exc
    except Exception as exc:
        raise HTTPException(400, f"Connection failed: {exc}") from exc


@router.get("/chat/threads", response_model=list[schemas.AiChatThreadOut])
def list_chat_threads(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    return [schemas.AiChatThreadOut(**t) for t in ai_chat.list_threads(db, current_user)]


@router.get("/chat/threads/{thread_id}", response_model=schemas.AiChatThreadDetailOut)
def get_chat_thread(
    thread_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    detail = ai_chat.thread_detail(db, current_user, thread_id)
    if not detail:
        raise HTTPException(404, "Chat not found")
    return schemas.AiChatThreadDetailOut(**detail)


@router.delete("/chat/threads/{thread_id}")
def delete_chat_thread(
    thread_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    if not ai_chat.delete_thread(db, current_user, thread_id):
        raise HTTPException(404, "Chat not found")
    return {"ok": True}


@router.get("/brain", response_model=list[schemas.AiBrainMemoryOut])
def list_brain(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app import ai_brain
    require_owner(current_user)
    return [schemas.AiBrainMemoryOut(**m) for m in ai_brain.list_memories(db, current_user)]


@router.post("/brain", response_model=schemas.AiBrainMemoryOut)
def teach_brain(
    body: schemas.AiBrainMemoryIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app import ai_brain
    require_owner(current_user)
    row = ai_brain.upsert_memory(
        db, current_user, content=body.content, kind=body.kind, source="manual",
    )
    if not row:
        raise HTTPException(400, "Could not save that (too short, or looks like a secret)")
    db.commit()
    return schemas.AiBrainMemoryOut(**row)


@router.delete("/brain/{memory_id}")
def forget_brain(
    memory_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app import ai_brain
    require_owner(current_user)
    if not ai_brain.forget_memory(db, current_user, memory_id):
        raise HTTPException(404, "Memory not found")
    db.commit()
    return {"ok": True}


@router.post("/chat", response_model=schemas.AiChatReplyOut)
def chat(
    body: schemas.AiChatIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    try:
        result = ai_chat.ask(db, current_user, body.message, body.thread_id)
    except LookupError as exc:
        raise HTTPException(400, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return schemas.AiChatReplyOut(**result)


@router.post("/chat/apply-shop-list", response_model=schemas.AiShopListActionOut)
def apply_shop_list(
    body: schemas.AiShopListActionIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    try:
        result = ai_chat.apply_shop_list_action(db, current_user, body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return schemas.AiShopListActionOut(**result)


@router.post("/chat/apply-diary-entry", response_model=schemas.AiDiaryEntryActionOut)
def apply_diary_entry(
    body: schemas.AiDiaryEntryActionIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    try:
        result = ai_chat.apply_diary_entry_action(db, current_user, body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return schemas.AiDiaryEntryActionOut(**result)


@router.post("/chat/apply-finance-txn", response_model=schemas.AiFinanceTxnActionOut)
def apply_finance_txn(
    body: schemas.AiFinanceTxnActionIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    try:
        result = ai_chat.apply_finance_txn_action(db, current_user, body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return schemas.AiFinanceTxnActionOut(**result)


@router.post("/chat/apply-diary-folder", response_model=schemas.AiDiaryFolderActionOut)
def apply_diary_folder(
    body: schemas.AiDiaryFolderActionIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    try:
        result = ai_chat.apply_diary_folder_action(db, current_user, body.model_dump())
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return schemas.AiDiaryFolderActionOut(**result)


@router.get("/usage", response_model=list[schemas.AiUsageLogOut])
def list_usage(
    client: str | None = None,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app import ai_usage
    require_owner(current_user)
    client_key = (client or "").strip() or None
    if client_key and client_key not in ai_usage.CLIENT_LABELS:
        client_key = None
    rows = ai_usage.list_logs(db, current_user, limit=limit, offset=offset, client=client_key)
    return [schemas.AiUsageLogOut(**ai_usage.log_out(r)) for r in rows]


@router.get("/usage/summary", response_model=schemas.AiUsageSummaryOut)
def usage_summary(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app import ai_usage
    require_owner(current_user)
    return schemas.AiUsageSummaryOut(**ai_usage.summary(db, current_user, days=days))
