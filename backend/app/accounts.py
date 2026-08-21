"""Create vault users and bootstrap the superadmin from env."""
from __future__ import annotations

import secrets

from sqlalchemy.orm import Session

from app import models, security
from app.config import settings
from app.database import SessionLocal


class AccountExists(Exception):
    pass


def create_vault_user(
    db: Session,
    *,
    email: str,
    password: str,
    full_name: str,
    role: str = models.UserRole.owner.value,
) -> models.User:
    email_norm = (email or "").strip().lower()
    name = (full_name or "").strip()
    if not email_norm or not name:
        raise ValueError("Email and name are required")
    if len(password or "") < 8:
        raise ValueError("Password must be at least 8 characters")
    if role not in (
        models.UserRole.owner.value,
        models.UserRole.superadmin.value,
        models.UserRole.viewer.value,
    ):
        raise ValueError("Unknown role")
    if db.query(models.User).filter(models.User.email == email_norm).first():
        raise AccountExists(email_norm)

    from app.quota import DEFAULT_QUOTA_BYTES

    user = models.User(
        email=email_norm,
        hashed_password=security.hash_password(password),
        full_name=name,
        role=role,
        storage_quota_bytes=DEFAULT_QUOTA_BYTES,
    )
    db.add(user)
    db.flush()
    user.vault_owner_id = user.id

    initials = "".join([p[0].upper() for p in name.split()[:2]]) or "ME"
    db.add(models.Person(
        user_id=user.id,
        name=name,
        relation=models.Relation.self_,
        avatar_initials=initials,
        ice_token=secrets.token_urlsafe(18),
    ))
    db.commit()
    db.refresh(user)
    return user


def ensure_superadmin() -> None:
    """Create or promote SUPERADMIN_EMAIL. No-op when the env var is empty."""
    email = settings.SUPERADMIN_EMAIL
    if not email:
        return
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user:
            user = db.query(models.User).filter(models.User.email.ilike(email)).first()
        if user:
            if user.role != models.UserRole.superadmin.value:
                user.role = models.UserRole.superadmin.value
                db.commit()
            return
        if not settings.SUPERADMIN_PASSWORD or len(settings.SUPERADMIN_PASSWORD) < 8:
            return
        create_vault_user(
            db,
            email=email,
            password=settings.SUPERADMIN_PASSWORD,
            full_name=settings.SUPERADMIN_NAME,
            role=models.UserRole.superadmin.value,
        )
    finally:
        db.close()
