from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas, security
from app.accounts import AccountExists, create_vault_user
from app.deps import get_current_user, require_owner, vault_id
from app.login_guard import authenticate, client_ip, client_ua, log_attempt, rate_limited, touch_last_seen
from app import totp as totp_util

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=schemas.LoginResponse, status_code=201)
def register(body: schemas.RegisterRequest, db: Session = Depends(get_db)):
    try:
        user = create_vault_user(
            db, email=body.email, password=body.password,
            full_name=body.full_name, role=models.UserRole.owner.value,
        )
    except AccountExists:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return schemas.LoginResponse(
        access_token=security.create_access_token(user.id),
        refresh_token=security.create_refresh_token(user.id),
    )


@router.post("/login", response_model=schemas.LoginResponse)
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user, err = authenticate(db, request, email=form.username, password=form.password)
    if err or not user:
        code = status.HTTP_429_TOO_MANY_REQUESTS if err and err.startswith("Too many") else status.HTTP_401_UNAUTHORIZED
        raise HTTPException(status_code=code, detail=err or "Incorrect email or password")
    if totp_util.is_enabled(user):
        return schemas.LoginResponse(
            totp_required=True,
            totp_token=security.create_totp_pending_token(user.id),
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
    if not user or totp_util.is_blocked(user):
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
    db.flush()
    for pid in body.person_ids or []:
        person = (
            db.query(models.Person)
            .filter(models.Person.id == pid, models.Person.user_id == vault_id(current_user))
            .first()
        )
        if person:
            db.add(models.ViewerAccess(viewer_user_id=viewer.id, person_id=person.id))
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
    db.query(models.ViewerAccess).filter(models.ViewerAccess.viewer_user_id == member.id).delete()
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


@router.post("/totp/setup", response_model=schemas.TotpSetupOut)
def totp_setup(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    secret = totp_util.begin_setup(current_user)
    db.commit()
    return schemas.TotpSetupOut(secret=secret, otpauth_url=totp_util.otpauth_url(current_user.email, secret))


@router.post("/totp/enable", status_code=204)
def totp_enable(body: schemas.TotpVerifyIn, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    if not totp_util.verify_code(current_user, body.code):
        raise HTTPException(status_code=400, detail="Invalid authenticator code")
    totp_util.enable(current_user)
    db.commit()


@router.post("/totp/disable", status_code=204)
def totp_disable(body: schemas.TotpVerifyIn, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    require_owner(current_user)
    if current_user.totp_enabled and not totp_util.verify_code(current_user, body.code):
        raise HTTPException(status_code=400, detail="Invalid authenticator code")
    totp_util.disable(current_user)
    db.commit()


@router.post("/app-approve", response_model=schemas.UserOut)
def set_app_approve(
    body: schemas.AppApproveIn,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    current_user.app_approve = bool(body.enabled)
    if not current_user.app_approve:
        db.query(models.LoginChallenge).filter(
            models.LoginChallenge.user_id == current_user.id,
            models.LoginChallenge.status == "pending",
        ).update({"status": "expired"}, synchronize_session=False)
    db.commit()
    db.refresh(current_user)
    return current_user


@router.post("/totp/verify", response_model=schemas.LoginResponse)
def totp_verify(body: schemas.TotpVerifyIn, request: Request, db: Session = Depends(get_db)):
    if not body.totp_token:
        raise HTTPException(status_code=400, detail="Missing totp token")
    user = totp_util.pending_user(db, body.totp_token)
    if not user or totp_util.is_blocked(user) or not totp_util.is_enabled(user):
        raise HTTPException(status_code=401, detail="Invalid or expired totp token")
    ip, ua = client_ip(request), client_ua(request)
    blocked, retry = rate_limited(db, user.email, ip)
    if blocked:
        log_attempt(db, email=user.email, ip=ip, user_agent=ua, success=False, reason="rate_limited")
        raise HTTPException(status_code=429, detail=f"Too many failed attempts. Try again in {retry} minute(s).")
    if not totp_util.verify_code(user, body.code):
        log_attempt(db, email=user.email, ip=ip, user_agent=ua, success=False, reason="totp_bad")
        raise HTTPException(status_code=401, detail="Invalid authenticator code")
    log_attempt(db, email=user.email, ip=ip, user_agent=ua, success=True, reason="ok")
    touch_last_seen(user)
    return schemas.LoginResponse(
        access_token=security.create_access_token(user.id),
        refresh_token=security.create_refresh_token(user.id),
    )


@router.get("/login-challenges", response_model=list[schemas.LoginChallengeOut])
def list_login_challenges(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app.login_challenge import pending_for_user
    return pending_for_user(db, current_user.id)


@router.get("/login-challenges/{challenge_id}", response_model=schemas.LoginChallengeOut)
def get_login_challenge(
    challenge_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app.login_challenge import get_challenge, parse_qr_payload
    cid = parse_qr_payload(challenge_id) or challenge_id
    row = get_challenge(db, cid)
    if not row or row.user_id != current_user.id or row.status != "pending":
        raise HTTPException(status_code=404, detail="Login request not found")
    return row


@router.post("/login-challenges/{challenge_id}/approve", status_code=204)
def approve_login_challenge(
    challenge_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app.login_challenge import KIND_QR, decide, get_challenge, parse_qr_payload
    cid = parse_qr_payload(challenge_id) or challenge_id
    row = get_challenge(db, cid)
    if not row or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Login request not found")
    if not decide(db, row, "approved"):
        raise HTTPException(status_code=409, detail="This login request is no longer pending")
    reason = "qr_ok" if (getattr(row, "kind", None) or "") == KIND_QR else "app_ok"
    log_attempt(
        db, email=current_user.email, ip=client_ip(request),
        user_agent=client_ua(request), success=True, reason=reason,
    )


@router.post("/login-challenges/{challenge_id}/deny", status_code=204)
def deny_login_challenge(
    challenge_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    from app.login_challenge import KIND_QR, decide, get_challenge, parse_qr_payload
    cid = parse_qr_payload(challenge_id) or challenge_id
    row = get_challenge(db, cid)
    if not row or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Login request not found")
    if not decide(db, row, "denied"):
        raise HTTPException(status_code=409, detail="This login request is no longer pending")
    reason = "qr_denied" if (getattr(row, "kind", None) or "") == KIND_QR else "app_denied"
    log_attempt(
        db, email=current_user.email, ip=client_ip(request),
        user_agent=client_ua(request), success=False, reason=reason,
    )
