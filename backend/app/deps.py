from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, security
from app.login_guard import touch_last_seen

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def vault_id(user: models.User) -> str:
    """The account whose people/docs this login may see. Viewers share the owner's vault."""
    return user.vault_owner_id or user.id


def is_viewer(user: models.User) -> bool:
    return (user.role or models.UserRole.owner.value) == models.UserRole.viewer.value


def is_superadmin(user: models.User) -> bool:
    return (user.role or "") == models.UserRole.superadmin.value


def require_owner(user: models.User) -> models.User:
    if is_viewer(user):
        raise HTTPException(status_code=403, detail="This account is view-only")
    return user


def require_enabled_module(module_key: str):
    """FastAPI dependency factory: 403 when Super Admin disabled this module for the vault."""

    def _dep(
        request: Request,
        current_user: models.User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> models.User:
        from app import modules as mod
        from app import vault_lock as vlock

        if not mod.is_enabled(db, current_user, module_key):
            raise HTTPException(status_code=403, detail="This module is disabled for your account")
        locked_mod = vlock.module_for_api_path(request.url.path)
        if locked_mod:
            vlock.require_api_unlock(request, current_user, locked_mod, db)
        return current_user

    return _dep


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = security.decode_token(token)
        if payload.get("type") != "access":
            raise credentials_error
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_error
    except ValueError:
        raise credentials_error

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise credentials_error
    from app.totp import is_blocked
    if is_blocked(user):
        raise HTTPException(status_code=403, detail="This account is blocked")
    touch_last_seen(user)
    return user


def require_vault_unlock_if_needed(
    request: Request,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.User:
    """For routers that do not use require_enabled_module (e.g. /documents)."""
    from app import vault_lock as vlock

    locked_mod = vlock.module_for_api_path(request.url.path)
    if locked_mod:
        vlock.require_api_unlock(request, current_user, locked_mod, db)
    return current_user


def visible_person_ids(db: Session, user: models.User):
    """None = no restriction. A set means the viewer may only see those people."""
    if not is_viewer(user):
        return None
    rows = (
        db.query(models.ViewerAccess.person_id)
        .filter(models.ViewerAccess.viewer_user_id == user.id)
        .all()
    )
    if not rows:
        return None
    return {r[0] for r in rows}


def apply_person_visibility(query, db: Session, user: models.User, person_column=None):
    ids = visible_person_ids(db, user)
    if ids is None:
        return query
    col = person_column if person_column is not None else models.Person.id
    return query.filter(col.in_(ids))


def get_owned_person(
    person_id: str,
    db: Session,
    current_user: models.User,
) -> models.Person:
    """Fetch a Person and verify it belongs to the current account (self or family member)."""
    person = db.query(models.Person).filter(
        models.Person.id == person_id,
        models.Person.user_id == vault_id(current_user),
    ).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    allowed = visible_person_ids(db, current_user)
    if allowed is not None and person.id not in allowed:
        raise HTTPException(status_code=404, detail="Person not found")
    return person
