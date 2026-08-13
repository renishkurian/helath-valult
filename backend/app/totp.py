"""Account TOTP helpers shared by the API, web login, and Super Admin."""
from __future__ import annotations

import base64

from sqlalchemy.orm import Session

from app import crypto, models, security


def is_enabled(user: models.User | None) -> bool:
    return bool(user and user.totp_enabled and user.totp_secret_enc)


def is_blocked(user: models.User | None) -> bool:
    return bool(user and getattr(user, "blocked", False))


def app_approve_on(user: models.User | None) -> bool:
    return bool(user and getattr(user, "app_approve", False))


def needs_step_up(user: models.User | None) -> bool:
    """Web login must wait for the phone and/or an authenticator code."""
    return is_enabled(user) or app_approve_on(user)


def otpauth_url(email: str, secret: str) -> str:
    return f"otpauth://totp/HealthVault:{email}?secret={secret}&issuer=HealthVault"


def qr_data_uri(data: str) -> str:
    """SVG data URI for an authenticator QR. Empty string if qrcode is missing."""
    try:
        import qrcode
        from qrcode.image.svg import SvgPathImage
        qr = qrcode.QRCode(box_size=8, border=2, image_factory=SvgPathImage)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image()
        raw = img.to_string()
        if isinstance(raw, bytes):
            raw = raw.decode("ascii")
        return "data:image/svg+xml;base64," + base64.b64encode(raw.encode("utf-8")).decode("ascii")
    except Exception:
        return ""


def begin_setup(user: models.User) -> str:
    secret = security.new_totp_secret()
    user.totp_secret_enc = crypto.encrypt_text(secret)
    user.totp_enabled = False
    return secret


def verify_code(user: models.User, code: str) -> bool:
    secret = crypto.decrypt_text(user.totp_secret_enc)
    return bool(secret and security.verify_totp(secret, code))


def enable(user: models.User) -> None:
    user.totp_enabled = True


def disable(user: models.User) -> None:
    user.totp_enabled = False
    user.totp_secret_enc = None


def pending_user(db: Session, token: str | None) -> models.User | None:
    if not token:
        return None
    try:
        payload = security.decode_token(token)
        if payload.get("type") != "totp":
            return None
    except ValueError:
        return None
    return db.query(models.User).filter(models.User.id == payload["sub"]).first()
