"""Secret Share — expiring text links (Vault Send with send_type=secret)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.deps import get_current_user, require_enabled_module, require_writer, vault_id
from app.routers import vault as vault_mod

router = APIRouter(
    prefix="/secrets",
    tags=["secrets"],
    dependencies=[Depends(require_enabled_module("secrets"))],
)


@router.get("/sends", response_model=list[schemas.VaultSendOut])
def list_secret_sends(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_writer(current_user)
    rows = (
        db.query(models.VaultSend)
        .filter(
            models.VaultSend.user_id == vault_id(current_user),
            models.VaultSend.send_type == "secret",
        )
        .order_by(models.VaultSend.created_at.desc())
        .all()
    )
    return [vault_mod._send_out(r) for r in rows]


@router.post("/sends", response_model=schemas.VaultSendOut, status_code=201)
def create_secret_send(
    body: schemas.VaultSendCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Create a text secret share; forces send_type=secret."""
    payload = body.model_copy(update={"send_type": "secret"})
    return vault_mod.create_send(payload, db=db, current_user=current_user)


@router.get("/sends/{send_id}", response_model=schemas.VaultSendOut)
def get_secret_send(
    send_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_writer(current_user)
    row = (
        db.query(models.VaultSend)
        .filter(
            models.VaultSend.id == send_id,
            models.VaultSend.user_id == vault_id(current_user),
            models.VaultSend.send_type == "secret",
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Send not found")
    return vault_mod._send_out(row)


@router.delete("/sends/{send_id}", status_code=204)
def revoke_secret_send(
    send_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_writer(current_user)
    row = (
        db.query(models.VaultSend)
        .filter(
            models.VaultSend.id == send_id,
            models.VaultSend.user_id == vault_id(current_user),
            models.VaultSend.send_type == "secret",
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Send not found")
    row.revoked = True
    db.commit()
    return Response(status_code=204)


@router.get("/send-requests", response_model=list[schemas.VaultSendRequestOut])
def list_secret_send_requests(
    status: Optional[str] = "all",
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_writer(current_user)
    q = (
        db.query(models.VaultSendRequest)
        .join(models.VaultSend, models.VaultSend.id == models.VaultSendRequest.send_id)
        .filter(
            models.VaultSendRequest.user_id == vault_id(current_user),
            models.VaultSend.send_type == "secret",
        )
    )
    if status and status != "all":
        q = q.filter(models.VaultSendRequest.status == status)
    rows = q.order_by(models.VaultSendRequest.created_at.desc()).limit(100).all()
    send_ids = {r.send_id for r in rows}
    sends = {
        s.id: s
        for s in db.query(models.VaultSend).filter(models.VaultSend.id.in_(send_ids)).all()
    } if send_ids else {}
    return [vault_mod._request_out(r, sends.get(r.send_id)) for r in rows]
