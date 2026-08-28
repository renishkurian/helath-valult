"""Automation Audit Log Router & Recorder for OpenClaw / AI / Automated tasks."""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app import models, schemas
from app.deps import get_current_user, require_enabled_module, vault_id

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
