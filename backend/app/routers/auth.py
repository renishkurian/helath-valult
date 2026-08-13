from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, security
from app.deps import get_current_user, require_owner, vault_id

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=schemas.LoginResponse, status_code=201)
def register(body: schemas.RegisterRequest, db: Session = Depends(get_db)):
    existing = db.query(models.User).filter(models.User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")

    user = models.User(
        email=body.email,
        hashed_password=security.hash_password(body.password),
        full_name=body.full_name,
        role=models.UserRole.owner.value,
    )
    db.add(user)
    db.flush()  # get user.id before creating the dependent 'self' person
    user.vault_owner_id = user.id

    initials = "".join([p[0].upper() for p in body.full_name.split()[:2]]) or "ME"
    self_person = models.Person(
        user_id=user.id,
        name=body.full_name,
        relation=models.Relation.self_,
        avatar_initials=initials,
    )
    db.add(self_person)
    db.commit()

    return schemas.LoginResponse(
        access_token=security.create_access_token(user.id),
        refresh_token=security.create_refresh_token(user.id),
    )


@router.post("/login", response_model=schemas.LoginResponse)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form.username).first()
    if not user or not security.verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    return schemas.LoginResponse(
        access_token=security.create_access_token(user.id),
        refresh_token=security.create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=schemas.LoginResponse)
def refresh(refresh_token: str, db: Session = Depends(get_db)):
    try:
        payload = security.decode_token(refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("wrong token type")
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")

    user = db.query(models.User).filter(models.User.id == payload["sub"]).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    return schemas.LoginResponse(
        access_token=security.create_access_token(user.id),
        refresh_token=security.create_refresh_token(user.id),
    )


@router.get("/me", response_model=schemas.UserOut)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.post("/invite", response_model=schemas.UserOut, status_code=201)
def invite_viewer(
    body: schemas.InviteViewerRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Create a view-only login that can see this vault (e.g. spouse in another city)."""
    require_owner(current_user)
    existing = db.query(models.User).filter(models.User.email == body.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    viewer = models.User(
        email=body.email,
        hashed_password=security.hash_password(body.password),
        full_name=body.full_name,
        role=models.UserRole.viewer.value,
        vault_owner_id=vault_id(current_user),
    )
    db.add(viewer)
    db.commit()
    db.refresh(viewer)
    return viewer


@router.get("/members", response_model=list[schemas.UserOut])
def list_vault_members(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    return (
        db.query(models.User)
        .filter(models.User.vault_owner_id == vault_id(current_user))
        .order_by(models.User.created_at.asc())
        .all()
    )


@router.delete("/members/{user_id}", status_code=204)
def remove_vault_member(
    user_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot remove yourself")
    member = (
        db.query(models.User)
        .filter(models.User.id == user_id, models.User.vault_owner_id == vault_id(current_user))
        .first()
    )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    db.query(models.DeviceToken).filter(models.DeviceToken.user_id == member.id).delete()
    db.delete(member)
    db.commit()


@router.post("/devices", status_code=204)
def register_device(
    body: schemas.DeviceTokenIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    existing = db.query(models.DeviceToken).filter(models.DeviceToken.token == body.token).first()
    if existing:
        existing.user_id = current_user.id
        existing.platform = body.platform
    else:
        db.add(models.DeviceToken(user_id=current_user.id, token=body.token, platform=body.platform))
    db.commit()
