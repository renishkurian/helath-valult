"""Family Vault item ownership and share ACL.

Rules:
- Each password / health document / locker item has an owner_user_id (creator).
- Owner always has full access.
- Others only see an item if a FamilyShare grants them view or edit.
- Family admin (owner role) does NOT automatically see member-created items.
"""
from __future__ import annotations

from typing import Iterable, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models
from app.deps import vault_id


def require_family_admin(user: models.User) -> models.User:
    """Family manager (vault owner), not a member account."""
    if (user.role or "") == models.UserRole.owner.value:
        return user
    if (user.role or "") == models.UserRole.superadmin.value and (user.vault_owner_id or user.id) == user.id:
        return user
    raise HTTPException(status_code=403, detail="Only the family manager can do this")


def is_family_admin(user: models.User) -> bool:
    role = user.role or ""
    if role == models.UserRole.owner.value:
        return True
    if role == models.UserRole.superadmin.value and (user.vault_owner_id or user.id) == user.id:
        return True
    return False


def is_family_member(user: models.User) -> bool:
    return (user.role or "") == models.UserRole.member.value


def is_legacy_viewer(user: models.User) -> bool:
    return (user.role or "") == models.UserRole.viewer.value


def can_write_own(user: models.User) -> bool:
    """Owner and members can create/edit their own entries. Legacy viewers cannot."""
    if is_legacy_viewer(user):
        return False
    role = user.role or models.UserRole.owner.value
    return role in (
        models.UserRole.owner.value,
        models.UserRole.member.value,
        models.UserRole.superadmin.value,
    )


def require_family_writer(user: models.User) -> models.User:
    if not can_write_own(user):
        raise HTTPException(status_code=403, detail="This account is view-only")
    return user


def item_owner_id(owner_user_id: Optional[str], vault_scope_id: str) -> str:
    return owner_user_id or vault_scope_id


def _share_row(
    db: Session,
    *,
    resource_type: str,
    resource_id: str,
    to_user_id: str,
) -> Optional[models.FamilyShare]:
    return (
        db.query(models.FamilyShare)
        .filter(
            models.FamilyShare.resource_type == resource_type,
            models.FamilyShare.resource_id == resource_id,
            models.FamilyShare.to_user_id == to_user_id,
        )
        .first()
    )


def permission_for(
    db: Session,
    user: models.User,
    *,
    resource_type: str,
    resource_id: str,
    owner_user_id: Optional[str],
    vault_scope_id: str,
) -> Optional[str]:
    """Return 'edit', 'view', or None."""
    oid = item_owner_id(owner_user_id, vault_scope_id)
    if user.id == oid:
        return models.SharePermission.edit.value
    share = _share_row(db, resource_type=resource_type, resource_id=resource_id, to_user_id=user.id)
    if not share:
        return None
    if share.permission == models.SharePermission.edit.value:
        return models.SharePermission.edit.value
    return models.SharePermission.view.value


def can_view(
    db: Session,
    user: models.User,
    *,
    resource_type: str,
    resource_id: str,
    owner_user_id: Optional[str],
    vault_scope_id: str,
) -> bool:
    return permission_for(
        db, user,
        resource_type=resource_type,
        resource_id=resource_id,
        owner_user_id=owner_user_id,
        vault_scope_id=vault_scope_id,
    ) is not None


def can_edit(
    db: Session,
    user: models.User,
    *,
    resource_type: str,
    resource_id: str,
    owner_user_id: Optional[str],
    vault_scope_id: str,
) -> bool:
    return permission_for(
        db, user,
        resource_type=resource_type,
        resource_id=resource_id,
        owner_user_id=owner_user_id,
        vault_scope_id=vault_scope_id,
    ) == models.SharePermission.edit.value


def visible_resource_ids(
    db: Session,
    user: models.User,
    *,
    resource_type: str,
    vault_scope_id: str,
) -> tuple[set[str], set[str]]:
    """Return (owned_ids_placeholder unused, shared_ids) — callers filter owned separately.

    Shared ids: resources shared *to* this user.
    """
    rows = (
        db.query(models.FamilyShare.resource_id)
        .filter(
            models.FamilyShare.vault_id == vault_scope_id,
            models.FamilyShare.resource_type == resource_type,
            models.FamilyShare.to_user_id == user.id,
        )
        .all()
    )
    return set(), {r[0] for r in rows}


def shares_for_resource(
    db: Session,
    *,
    resource_type: str,
    resource_id: str,
) -> list[models.FamilyShare]:
    return (
        db.query(models.FamilyShare)
        .filter(
            models.FamilyShare.resource_type == resource_type,
            models.FamilyShare.resource_id == resource_id,
        )
        .order_by(models.FamilyShare.created_at.asc())
        .all()
    )


def family_member_users(db: Session, admin: models.User) -> list[models.User]:
    vid = vault_id(admin)
    return (
        db.query(models.User)
        .filter(models.User.vault_owner_id == vid, models.User.id != vid)
        .order_by(models.User.created_at.asc())
        .all()
    )


def share_target_users(db: Session, user: models.User, *, repair: bool = True) -> list[models.User]:
    """Other household logins this user can share or transfer items to.

    Includes vault owner + members (excluding self). Also picks up Users linked
    via Person.linked_user_id in case vault_owner_id was never set.
    """
    vid = vault_id(user)
    rows = (
        db.query(models.User)
        .filter(
            models.User.id != user.id,
            (
                (models.User.vault_owner_id == vid)
                | (models.User.id == vid)
            ),
        )
        .order_by(models.User.full_name.asc())
        .all()
    )
    by_id = {u.id: u for u in rows if vault_id(u) == vid}

    linked_ids = [
        p.linked_user_id
        for p in (
            db.query(models.Person)
            .filter(
                models.Person.user_id == vid,
                models.Person.linked_user_id.isnot(None),
            )
            .all()
        )
        if p.linked_user_id and p.linked_user_id != user.id
    ]
    missing = [uid for uid in linked_ids if uid not in by_id]
    dirty = False
    if missing:
        for u in db.query(models.User).filter(models.User.id.in_(missing)).all():
            if repair and (u.role or "") == models.UserRole.member.value and (u.vault_owner_id or u.id) != vid:
                u.vault_owner_id = vid
                dirty = True
            by_id[u.id] = u
    if dirty:
        db.commit()

    return sorted(by_id.values(), key=lambda u: (u.full_name or u.email or "").lower())


def same_family(db: Session, a: models.User, b_user_id: str) -> Optional[models.User]:
    other = db.query(models.User).filter(models.User.id == b_user_id).first()
    if not other:
        return None
    vid = vault_id(a)
    if vault_id(other) == vid:
        return other
    # Person-linked household member whose vault_owner_id was never set.
    linked = (
        db.query(models.Person)
        .filter(
            models.Person.user_id == vid,
            models.Person.linked_user_id == other.id,
        )
        .first()
    )
    if not linked:
        return None
    if (other.role or "") == models.UserRole.member.value and (other.vault_owner_id or "") != vid:
        other.vault_owner_id = vid
    return other


def upsert_share(
    db: Session,
    *,
    from_user: models.User,
    to_user_id: str,
    resource_type: str,
    resource_id: str,
    permission: str,
) -> models.FamilyShare:
    if permission not in (models.SharePermission.view.value, models.SharePermission.edit.value):
        raise HTTPException(status_code=400, detail="permission must be view or edit")
    target = same_family(db, from_user, to_user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Family member not found")
    if target.id == from_user.id:
        raise HTTPException(status_code=400, detail="Cannot share with yourself")
    vid = vault_id(from_user)
    row = _share_row(db, resource_type=resource_type, resource_id=resource_id, to_user_id=to_user_id)
    if row:
        row.permission = permission
        row.from_user_id = from_user.id
    else:
        row = models.FamilyShare(
            vault_id=vid,
            resource_type=resource_type,
            resource_id=resource_id,
            from_user_id=from_user.id,
            to_user_id=to_user_id,
            permission=permission,
        )
        db.add(row)
    return row


def revoke_share(
    db: Session,
    *,
    actor: models.User,
    resource_type: str,
    resource_id: str,
    to_user_id: str,
) -> None:
    row = _share_row(db, resource_type=resource_type, resource_id=resource_id, to_user_id=to_user_id)
    if not row:
        raise HTTPException(status_code=404, detail="Share not found")
    # Owner of the item or the granter can revoke; recipient can also drop.
    if row.from_user_id != actor.id and row.to_user_id != actor.id:
        # allow item owner via caller checks; here allow vault admin who owns item checked upstream
        if not is_family_admin(actor):
            raise HTTPException(status_code=403, detail="Cannot revoke this share")
    db.delete(row)


def transfer_ownership(
    db: Session,
    *,
    actor: models.User,
    resource_type: str,
    resource_id: str,
    to_user_id: str,
    keep_access: bool = True,
    keep_permission: str = "view",
) -> models.User:
    """Move item ownership to another family login. Returns the new owner user.

    Only the current owner may transfer. Vault scope (user_id) stays the same.
    Existing shares to other members are reassigned to the new owner as granter.
    """
    if resource_type not in (
        models.ShareResourceType.password.value,
        models.ShareResourceType.health_document.value,
        models.ShareResourceType.locker.value,
    ):
        raise HTTPException(status_code=400, detail="Invalid resource type")

    target = same_family(db, actor, to_user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Family member not found")
    if target.id == actor.id:
        raise HTTPException(status_code=400, detail="Already owned by you")

    vid = vault_id(actor)
    item = None
    if resource_type == models.ShareResourceType.password.value:
        item = (
            db.query(models.VaultItem)
            .filter(models.VaultItem.id == resource_id, models.VaultItem.user_id == vid)
            .first()
        )
    elif resource_type == models.ShareResourceType.locker.value:
        item = (
            db.query(models.LockerItem)
            .filter(models.LockerItem.id == resource_id, models.LockerItem.user_id == vid)
            .first()
        )
    else:
        item = (
            db.query(models.Document)
            .join(models.Person, models.Person.id == models.Document.person_id)
            .filter(models.Document.id == resource_id, models.Person.user_id == vid)
            .first()
        )
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    current_owner = item_owner_id(getattr(item, "owner_user_id", None), vid)
    if actor.id != current_owner:
        raise HTTPException(status_code=403, detail="Only the owner can transfer this item")

    item.owner_user_id = target.id

    shares = (
        db.query(models.FamilyShare)
        .filter(
            models.FamilyShare.resource_type == resource_type,
            models.FamilyShare.resource_id == resource_id,
        )
        .all()
    )
    for share in shares:
        if share.to_user_id == target.id:
            db.delete(share)
        else:
            share.from_user_id = target.id

    if keep_access:
        perm = keep_permission if keep_permission in (
            models.SharePermission.view.value,
            models.SharePermission.edit.value,
        ) else models.SharePermission.view.value
        upsert_share(
            db,
            from_user=target,
            to_user_id=actor.id,
            resource_type=resource_type,
            resource_id=resource_id,
            permission=perm,
        )

    return target


def convert_viewers_to_members(db: Session) -> int:
    """One-shot / startup migration: viewers become members with linked Person profiles."""
    import secrets

    viewers = db.query(models.User).filter(models.User.role == models.UserRole.viewer.value).all()
    converted = 0
    for viewer in viewers:
        viewer.role = models.UserRole.member.value
        converted += 1
        linked = (
            db.query(models.Person)
            .filter(models.Person.linked_user_id == viewer.id)
            .first()
        )
        if linked:
            continue
        access = (
            db.query(models.ViewerAccess)
            .filter(models.ViewerAccess.viewer_user_id == viewer.id)
            .all()
        )
        if len(access) == 1:
            person = db.query(models.Person).filter(models.Person.id == access[0].person_id).first()
            if person and not person.linked_user_id:
                person.linked_user_id = viewer.id
                continue
        vid = viewer.vault_owner_id or viewer.id
        initials = "".join([p[0].upper() for p in (viewer.full_name or "FM").split()[:2]]) or "FM"
        db.add(models.Person(
            user_id=vid,
            linked_user_id=viewer.id,
            name=viewer.full_name or viewer.email,
            relation=models.Relation.other,
            avatar_initials=initials,
            ice_token=secrets.token_urlsafe(18),
        ))
    if converted:
        db.commit()
    return converted


def share_summaries(
    db: Session,
    *,
    resource_type: str,
    resource_ids: Iterable[str],
) -> dict[str, list[dict]]:
    ids = list(resource_ids)
    if not ids:
        return {}
    rows = (
        db.query(models.FamilyShare, models.User)
        .join(models.User, models.User.id == models.FamilyShare.to_user_id)
        .filter(
            models.FamilyShare.resource_type == resource_type,
            models.FamilyShare.resource_id.in_(ids),
        )
        .all()
    )
    out: dict[str, list[dict]] = {i: [] for i in ids}
    for share, user in rows:
        out.setdefault(share.resource_id, []).append({
            "user_id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "permission": share.permission,
            "share_id": share.id,
        })
    return out
