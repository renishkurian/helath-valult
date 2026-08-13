from typing import Optional
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.deps import get_current_user, vault_id

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[schemas.AuditLogOut])
def list_audit_log(
    document_id: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Who viewed/downloaded what, and any share-link activity on your documents."""
    q = db.query(models.AuditLog).join(
        models.Document, models.AuditLog.document_id == models.Document.id
    ).join(models.Person).filter(models.Person.user_id == vault_id(current_user))
    if document_id:
        q = q.filter(models.AuditLog.document_id == document_id)
    return q.order_by(models.AuditLog.created_at.desc()).limit(min(limit, 500)).all()
