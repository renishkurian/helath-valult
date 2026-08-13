"""Web login challenges that the already-signed-in Android app can allow or deny."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app import models
from app.push import send_fcm


CHALLENGE_MINUTES = 5
KIND_APP = "app"
KIND_QR = "qr"
QR_PAYLOAD_PREFIX = "healthvault://login/"


def qr_payload(challenge_id: str) -> str:
    return f"{QR_PAYLOAD_PREFIX}{challenge_id}"


def parse_qr_payload(raw: str | None) -> str | None:
    text = (raw or "").strip()
    if text.startswith(QR_PAYLOAD_PREFIX):
        text = text[len(QR_PAYLOAD_PREFIX):].strip().strip("/")
    if len(text) == 32 and all(c in "0123456789abcdefABCDEF" for c in text):
        return text.lower()
    return None


def _is_app_kind(row: models.LoginChallenge) -> bool:
    return (getattr(row, "kind", None) or KIND_APP) != KIND_QR


def create_challenge(
    db: Session,
    user: models.User,
    ip: str | None,
    user_agent: str,
    *,
    kind: str = KIND_APP,
) -> models.LoginChallenge:
    now = datetime.utcnow()
    kind = KIND_QR if kind == KIND_QR else KIND_APP
    pending = db.query(models.LoginChallenge).filter(
        models.LoginChallenge.user_id == user.id,
        models.LoginChallenge.status == "pending",
    )
    if kind == KIND_QR:
        pending = pending.filter(models.LoginChallenge.kind == KIND_QR)
    else:
        pending = pending.filter(or_(
            models.LoginChallenge.kind == KIND_APP,
            models.LoginChallenge.kind.is_(None),
            models.LoginChallenge.kind == "",
        ))
    pending.update({"status": "expired", "decided_at": now}, synchronize_session=False)
    row = models.LoginChallenge(
        user_id=user.id,
        ip=ip,
        user_agent=(user_agent or "")[:400],
        status="pending",
        kind=kind,
        expires_at=now + timedelta(minutes=CHALLENGE_MINUTES),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_challenge(db: Session, challenge_id: str | None) -> models.LoginChallenge | None:
    if not challenge_id:
        return None
    row = db.query(models.LoginChallenge).filter(models.LoginChallenge.id == challenge_id).first()
    if not row:
        return None
    if row.status == "pending" and row.expires_at and row.expires_at < datetime.utcnow():
        row.status = "expired"
        row.decided_at = datetime.utcnow()
        db.commit()
    return row


def pending_for_user(db: Session, user_id: str) -> list[models.LoginChallenge]:
    now = datetime.utcnow()
    rows = (
        db.query(models.LoginChallenge)
        .filter(
            models.LoginChallenge.user_id == user_id,
            models.LoginChallenge.status == "pending",
            or_(
                models.LoginChallenge.kind == KIND_APP,
                models.LoginChallenge.kind.is_(None),
                models.LoginChallenge.kind == "",
            ),
        )
        .order_by(models.LoginChallenge.created_at.desc())
        .all()
    )
    live = []
    for row in rows:
        if row.expires_at and row.expires_at < now:
            row.status = "expired"
            row.decided_at = now
        else:
            live.append(row)
    if len(live) != len(rows):
        db.commit()
    return live


def decide(db: Session, row: models.LoginChallenge, status: str) -> bool:
    row = get_challenge(db, row.id) or row
    if row.status != "pending":
        return False
    row.status = status
    row.decided_at = datetime.utcnow()
    db.commit()
    return True


def consume(db: Session, challenge_id: str | None) -> None:
    row = get_challenge(db, challenge_id)
    if not row or row.status != "pending":
        return
    row.status = "approved"
    row.decided_at = datetime.utcnow()
    db.commit()


def notify_devices(db: Session, user: models.User, challenge: models.LoginChallenge) -> int:
    from app.server_settings import fcm_server_key
    key = fcm_server_key(db)
    tokens = db.query(models.DeviceToken).filter(models.DeviceToken.user_id == user.id).all()
    if not tokens or not key:
        return 0
    title = "Approve web login"
    where = challenge.ip or "a browser"
    body = f"Vault sign-in from {where}. Open the app to allow or deny."
    sent = 0
    for tok in tokens:
        if send_fcm(
            tok.token, title, body,
            data={"type": "login_challenge", "id": challenge.id},
            server_key=key,
        ):
            sent += 1
    return sent
