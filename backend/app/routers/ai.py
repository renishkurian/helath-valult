"""Shared AI providers API — vault-wide LLM keys for every module."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import ai_providers as ap
from app import models, schemas
from app.database import get_db
from app.deps import get_current_user, require_owner

router = APIRouter(prefix="/ai", tags=["ai"])


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
