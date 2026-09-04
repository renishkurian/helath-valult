"""Family Vault module: members, relationships, and item shares."""
from __future__ import annotations

import secrets
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app import models, schemas, security
from app.database import get_db
from app.deps import get_current_user, require_enabled_module, vault_id
from app import family_access as faccess

router = APIRouter(
    prefix="/family",
    tags=["family"],
    dependencies=[Depends(require_enabled_module("family"))],
)


class FamilyMemberOut(BaseModel):
    user_id: Optional[str] = None
    email: Optional[str] = None
    full_name: str
    role: str
    person_id: str
    relation: str
    blood_group: Optional[str] = None
    linked: bool = False


class InviteMemberIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    relation: str = "other"
    person_id: Optional[str] = None  # link existing profile, or create new


class ShareIn(BaseModel):
    to_user_id: str
    permission: str = "view"  # view | edit


class TransferIn(BaseModel):
    to_user_id: str
    keep_access: bool = True
    keep_permission: str = "view"  # view | edit when keep_access


class ShareOut(BaseModel):
    id: str
    resource_type: str
    resource_id: str
    from_user_id: str
    to_user_id: str
    to_full_name: str
    to_email: str
    permission: str


class ShareTargetOut(BaseModel):
    user_id: str
    full_name: str
    email: str
    role: str


def _person_out(person: models.Person, linked: Optional[models.User] = None) -> FamilyMemberOut:
    return FamilyMemberOut(
        user_id=linked.id if linked else person.linked_user_id,
        email=linked.email if linked else None,
        full_name=linked.full_name if linked else person.name,
        role=(linked.role if linked else "profile"),
        person_id=person.id,
        relation=person.relation.value if hasattr(person.relation, "value") else str(person.relation),
        blood_group=person.blood_group,
        linked=bool(person.linked_user_id),
    )


@router.get("/members", response_model=List[FamilyMemberOut])
def list_members(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Everyone in the household: profiles + linked logins."""
    if not faccess.is_accepted_family_member(current_user):
        return []
    vid = vault_id(current_user)
    people = (
        db.query(models.Person)
        .filter(models.Person.user_id == vid)
        .order_by(models.Person.created_at.asc())
        .all()
    )
    linked_ids = [p.linked_user_id for p in people if p.linked_user_id]
    users = {}
    if linked_ids:
        for u in db.query(models.User).filter(models.User.id.in_(linked_ids)).all():
            users[u.id] = u
    out = [_person_out(p, users.get(p.linked_user_id) if p.linked_user_id else None) for p in people]
    return out


@router.get("/share-targets", response_model=List[ShareTargetOut])
def share_targets(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Other logins in this family you can share an entry with."""
    rows = faccess.share_target_users(db, current_user)
    return [
        ShareTargetOut(user_id=u.id, full_name=u.full_name, email=u.email, role=u.role)
        for u in rows
    ]


@router.get("/request")
def get_family_request(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Get current user's family request / invitation status."""
    vid = vault_id(current_user)
    manager = db.query(models.User).filter(models.User.id == vid).first()
    return {
        "status": getattr(current_user, "family_status", "accepted"),
        "manager_id": manager.id if manager else None,
        "manager_name": manager.full_name if manager else "",
        "manager_email": manager.email if manager else "",
    }


@router.post("/request/accept")
def accept_family_request(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Accept pending family invitation. Only now does the account actually
    join the inviting vault - vault_owner_id is untouched until this point."""
    if current_user.pending_vault_owner_id:
        current_user.vault_owner_id = current_user.pending_vault_owner_id
        current_user.pending_vault_owner_id = None
        current_user.role = models.UserRole.member.value
    current_user.family_status = "accepted"
    db.commit()
    db.refresh(current_user)
    return {"ok": True, "family_status": "accepted"}


@router.post("/request/reject")
def reject_family_request(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Reject pending family invitation. vault_owner_id was never touched on
    invite, so there's nothing to roll back there - just clear the pending
    link and any profile that was tentatively linked to this account."""
    current_user.pending_vault_owner_id = None
    current_user.family_status = "rejected"
    db.query(models.Person).filter(models.Person.linked_user_id == current_user.id).update(
        {models.Person.linked_user_id: None}, synchronize_session=False
    )
    db.commit()
    db.refresh(current_user)
    return {"ok": True, "family_status": "rejected"}


@router.post("/invite", response_model=FamilyMemberOut, status_code=201)
def invite_member(
    body: InviteMemberIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Family manager invites a member login and links (or creates) a Person profile."""
    faccess.require_family_admin(current_user)
    existing = db.query(models.User).filter(models.User.email == str(body.email).lower()).first()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    try:
        relation = models.Relation(body.relation)
    except ValueError:
        relation = models.Relation.other
    if relation == models.Relation.self_:
        raise HTTPException(status_code=400, detail="Cannot invite another 'self' profile")

    member = models.User(
        email=str(body.email).strip().lower(),
        hashed_password=security.hash_password(body.password),
        full_name=body.full_name.strip(),
        role=models.UserRole.member.value,
        family_status="pending",
        vault_owner_id=vault_id(current_user),
    )
    db.add(member)
    db.flush()

    person = None
    if body.person_id:
        person = (
            db.query(models.Person)
            .filter(
                models.Person.id == body.person_id,
                models.Person.user_id == vault_id(current_user),
            )
            .first()
        )
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")
        if person.linked_user_id and person.linked_user_id != member.id:
            raise HTTPException(status_code=409, detail="This profile already has a login")
        person.linked_user_id = member.id
        person.name = body.full_name.strip() or person.name
        person.relation = relation
    else:
        initials = "".join([p[0].upper() for p in body.full_name.split()[:2]]) or "FM"
        person = models.Person(
            user_id=vault_id(current_user),
            linked_user_id=member.id,
            name=body.full_name.strip(),
            relation=relation,
            avatar_initials=initials,
            ice_token=secrets.token_urlsafe(18),
        )
        db.add(person)
    db.commit()
    db.refresh(person)
    return _person_out(person, member)


@router.post("/convert-viewers", response_model=dict)
def convert_viewers(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    faccess.require_family_admin(current_user)
    n = faccess.convert_viewers_to_members(db)
    return {"converted": n}


@router.post("/shares/{resource_type}/{resource_id}", response_model=ShareOut)
def create_or_update_share(
    resource_type: str,
    resource_id: str,
    body: ShareIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Share a password / health document / locker item with a family member (view or edit)."""
    faccess.require_family_writer(current_user)
    if resource_type not in (
        models.ShareResourceType.password.value,
        models.ShareResourceType.health_document.value,
        models.ShareResourceType.locker.value,
    ):
        raise HTTPException(status_code=400, detail="Invalid resource type")

    owner_user_id, vault_scope = _resolve_resource_owner(db, current_user, resource_type, resource_id)
    if not faccess.can_edit(
        db, current_user,
        resource_type=resource_type,
        resource_id=resource_id,
        owner_user_id=owner_user_id,
        vault_scope_id=vault_scope,
    ):
        raise HTTPException(status_code=403, detail="Only the owner (or edit-share) can share this item")

    row = faccess.upsert_share(
        db,
        from_user=current_user,
        to_user_id=body.to_user_id,
        resource_type=resource_type,
        resource_id=resource_id,
        permission=body.permission,
    )
    db.commit()
    db.refresh(row)
    target = db.query(models.User).filter(models.User.id == row.to_user_id).first()
    return ShareOut(
        id=row.id,
        resource_type=row.resource_type,
        resource_id=row.resource_id,
        from_user_id=row.from_user_id,
        to_user_id=row.to_user_id,
        to_full_name=target.full_name if target else "",
        to_email=target.email if target else "",
        permission=row.permission,
    )


@router.get("/shares/{resource_type}/{resource_id}", response_model=List[ShareOut])
def list_shares(
    resource_type: str,
    resource_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    owner_user_id, vault_scope = _resolve_resource_owner(db, current_user, resource_type, resource_id)
    if not faccess.can_view(
        db, current_user,
        resource_type=resource_type,
        resource_id=resource_id,
        owner_user_id=owner_user_id,
        vault_scope_id=vault_scope,
    ):
        raise HTTPException(status_code=404, detail="Item not found")
    # Only owner sees full share list (who it's shared with)
    oid = faccess.item_owner_id(owner_user_id, vault_scope)
    if current_user.id != oid:
        raise HTTPException(status_code=403, detail="Only the owner can list shares for this item")
    rows = faccess.shares_for_resource(db, resource_type=resource_type, resource_id=resource_id)
    out = []
    for row in rows:
        target = db.query(models.User).filter(models.User.id == row.to_user_id).first()
        out.append(ShareOut(
            id=row.id,
            resource_type=row.resource_type,
            resource_id=row.resource_id,
            from_user_id=row.from_user_id,
            to_user_id=row.to_user_id,
            to_full_name=target.full_name if target else "",
            to_email=target.email if target else "",
            permission=row.permission,
        ))
    return out


@router.delete("/shares/{resource_type}/{resource_id}/{to_user_id}", status_code=204)
def delete_share(
    resource_type: str,
    resource_id: str,
    to_user_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    owner_user_id, vault_scope = _resolve_resource_owner(db, current_user, resource_type, resource_id)
    oid = faccess.item_owner_id(owner_user_id, vault_scope)
    if current_user.id != oid and current_user.id != to_user_id:
        raise HTTPException(status_code=403, detail="Cannot revoke this share")
    faccess.revoke_share(
        db, actor=current_user,
        resource_type=resource_type,
        resource_id=resource_id,
        to_user_id=to_user_id,
    )
    db.commit()


@router.post("/transfer/{resource_type}/{resource_id}")
def transfer_resource(
    resource_type: str,
    resource_id: str,
    body: TransferIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Transfer ownership of a password / locker / health document to another family login."""
    faccess.require_family_writer(current_user)
    new_owner = faccess.transfer_ownership(
        db,
        actor=current_user,
        resource_type=resource_type,
        resource_id=resource_id,
        to_user_id=body.to_user_id,
        keep_access=body.keep_access,
        keep_permission=body.keep_permission,
    )
    db.commit()
    return {
        "ok": True,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "owner_user_id": new_owner.id,
        "owner_full_name": new_owner.full_name,
        "kept_access": body.keep_access,
    }


def _resolve_resource_owner(
    db: Session,
    user: models.User,
    resource_type: str,
    resource_id: str,
) -> tuple[Optional[str], str]:
    vid = vault_id(user)
    if resource_type == models.ShareResourceType.password.value:
        item = (
            db.query(models.VaultItem)
            .filter(models.VaultItem.id == resource_id, models.VaultItem.user_id == vid)
            .first()
        )
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        return item.owner_user_id, item.user_id
    if resource_type == models.ShareResourceType.locker.value:
        item = (
            db.query(models.LockerItem)
            .filter(models.LockerItem.id == resource_id, models.LockerItem.user_id == vid)
            .first()
        )
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        return item.owner_user_id, item.user_id
    if resource_type == models.ShareResourceType.health_document.value:
        doc = (
            db.query(models.Document)
            .join(models.Person, models.Person.id == models.Document.person_id)
            .filter(models.Document.id == resource_id, models.Person.user_id == vid)
            .first()
        )
        if not doc:
            raise HTTPException(status_code=404, detail="Item not found")
        return doc.owner_user_id, vid
    raise HTTPException(status_code=400, detail="Invalid resource type")
