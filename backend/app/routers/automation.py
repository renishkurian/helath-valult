"""Automation Audit Log Router & Recorder for OpenClaw / AI / Automated tasks."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app import models, schemas, security
from app.deps import get_current_user, require_enabled_module, vault_id, require_owner

router = APIRouter(
    prefix="/automation",
    tags=["automation"],
    dependencies=[Depends(require_enabled_module("automation"))],
)


def record_automation_audit(
    action: str,
    resource_type: str,
    resource_id: Optional[str] = None,
    details: Optional[str] = None,
    user_id: Optional[str] = None,
    actor: str = "openclaw",
    status: str = "success",
    ip: Optional[str] = None,
    db: Optional[Session] = None,
) -> models.AutomationAuditLog:
    """Helper function to record an automation audit event from anywhere in code or CLI."""
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True

    try:
        log_entry = models.AutomationAuditLog(
            user_id=user_id,
            actor=actor,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            status=status,
            ip=ip,
        )
        db.add(log_entry)
        db.commit()
        db.refresh(log_entry)
        return log_entry
    finally:
        if should_close:
            db.close()


@router.get("/logs", response_model=list[schemas.AutomationAuditLogOut])
def list_automation_logs(
    actor: Optional[str] = None,
    resource_type: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Retrieve audit logs of all OpenClaw/automation activity."""
    v_id = vault_id(current_user)
    q = db.query(models.AutomationAuditLog).filter(
        (models.AutomationAuditLog.user_id == v_id) | (models.AutomationAuditLog.user_id.is_(None))
    )
    if actor:
        q = q.filter(models.AutomationAuditLog.actor == actor)
    if resource_type:
        q = q.filter(models.AutomationAuditLog.resource_type == resource_type)
    if action:
        q = q.filter(models.AutomationAuditLog.action == action)

    return q.order_by(models.AutomationAuditLog.created_at.desc()).limit(limit).all()


@router.post("/logs", response_model=schemas.AutomationAuditLogOut, status_code=201)
def create_automation_log(
    payload: schemas.AutomationAuditLogCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Explicitly append an automation audit record from external tools/PicoClaw."""
    v_id = vault_id(current_user)
    return record_automation_audit(
        action=payload.action,
        resource_type=payload.resource_type,
        resource_id=payload.resource_id,
        details=payload.details,
        user_id=v_id,
        actor=payload.actor,
        status=payload.status,
        ip=payload.ip,
        db=db,
    )


# ---------- User API Tokens Management ----------

@router.get("/tokens", response_model=list[schemas.UserApiTokenOut])
def list_user_api_tokens(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """List all active API tokens for current user."""
    return (
        db.query(models.UserApiToken)
        .filter(
            models.UserApiToken.user_id == current_user.id,
            models.UserApiToken.revoked_at.is_(None),
        )
        .order_by(models.UserApiToken.created_at.desc())
        .all()
    )


@router.post("/tokens", response_model=schemas.UserApiTokenCreatedOut, status_code=201)
def create_user_api_token(
    payload: schemas.UserApiTokenCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Create a new Personal API token for OpenClaw/PicoClaw/Automations."""
    token, token_hash, prefix = security.generate_api_token()
    token_obj = models.UserApiToken(
        user_id=current_user.id,
        name=payload.name.strip() or "OpenClaw Token",
        token_hash=token_hash,
        prefix=prefix,
        created_at=datetime.utcnow(),
    )
    db.add(token_obj)
    db.commit()
    db.refresh(token_obj)

    record_automation_audit(
        action="api_token_create",
        resource_type="security",
        resource_id=token_obj.id,
        details=f"Created API token '{token_obj.name}' ({token_obj.prefix})",
        user_id=vault_id(current_user),
        actor="web",
        db=db,
    )

    return schemas.UserApiTokenCreatedOut(
        id=token_obj.id,
        name=token_obj.name,
        prefix=token_obj.prefix,
        token=token,
        created_at=token_obj.created_at,
    )


@router.delete("/tokens/{token_id}")
def revoke_user_api_token(
    token_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Revoke an API token."""
    tok = (
        db.query(models.UserApiToken)
        .filter(
            models.UserApiToken.id == token_id,
            models.UserApiToken.user_id == current_user.id,
        )
        .first()
    )
    if not tok:
        raise HTTPException(status_code=404, detail="API Token not found")

    tok.revoked_at = datetime.utcnow()
    db.commit()

    record_automation_audit(
        action="api_token_revoke",
        resource_type="security",
        resource_id=tok.id,
        details=f"Revoked API token '{tok.name}' ({tok.prefix})",
        user_id=vault_id(current_user),
        actor="web",
        db=db,
    )

    return {"status": "ok", "message": "API token revoked"}

