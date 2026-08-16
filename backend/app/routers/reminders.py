from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.deps import get_current_user, get_owned_person, require_owner, vault_id

router = APIRouter(prefix="/reminders", tags=["reminders"])


def _next_occurrence(remind_at, rule: models.RepeatRule):
    if rule == models.RepeatRule.daily:
        return remind_at + timedelta(days=1)
    if rule == models.RepeatRule.weekly:
        return remind_at + timedelta(weeks=1)
    if rule == models.RepeatRule.monthly:
        # naive but dependency-free 30-day step; fine for med refill reminders
        return remind_at + timedelta(days=30)
    if rule == models.RepeatRule.yearly:
        return remind_at + timedelta(days=365)
    return None


@router.get("", response_model=list[schemas.ReminderOut])
def list_reminders(
    person_id: Optional[str] = None,
    upcoming_only: bool = False,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    q = db.query(models.Reminder).join(models.Person).filter(models.Person.user_id == vault_id(current_user))
    if person_id:
        q = q.filter(models.Reminder.person_id == person_id)
    if upcoming_only:
        q = q.filter(models.Reminder.is_active == True)  # noqa: E712
    return q.order_by(models.Reminder.remind_at.asc()).all()


@router.post("", response_model=schemas.ReminderOut, status_code=201)
def create_reminder(
    body: schemas.ReminderCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    get_owned_person(body.person_id, db, current_user)
    reminder = models.Reminder(**body.dict())
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    push_reminder_schedule(db, current_user, reminder)
    return reminder


def _get_owned_reminder(reminder_id: str, db: Session, current_user: models.User) -> models.Reminder:
    r = (
        db.query(models.Reminder)
        .join(models.Person)
        .filter(models.Reminder.id == reminder_id, models.Person.user_id == vault_id(current_user))
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return r


def push_reminder_schedule(db: Session, user: models.User, rem: models.Reminder) -> int:
    """Tell signed-in phones to set a local AlarmManager notification for this reminder."""
    from app.push import send_fcm
    from app.server_settings import fcm_service_account

    account = fcm_service_account(db)
    tokens = (
        db.query(models.DeviceToken)
        .filter(models.DeviceToken.user_id.in_([user.id, vault_id(user)]))
        .all()
    )
    if not tokens or not account:
        return 0
    remind_iso = rem.remind_at.isoformat() if hasattr(rem.remind_at, "isoformat") else str(rem.remind_at)
    title = rem.title or "Vault reminder"
    body = rem.description or f"Due {remind_iso}"
    data = {
        "type": "reminder_schedule",
        "id": rem.id,
        "title": title,
        "body": body,
        "remind_at": remind_iso,
        "repeat_rule": rem.repeat_rule.value if hasattr(rem.repeat_rule, "value") else str(rem.repeat_rule),
    }
    sent = 0
    for tok in tokens:
        if send_fcm(tok.token, title, body, data=data, account=account):
            sent += 1
    return sent


def push_reminder_cancel(db: Session, user: models.User, reminder_id: str) -> int:
    from app.push import send_fcm
    from app.server_settings import fcm_service_account

    account = fcm_service_account(db)
    tokens = (
        db.query(models.DeviceToken)
        .filter(models.DeviceToken.user_id.in_([user.id, vault_id(user)]))
        .all()
    )
    if not tokens or not account:
        return 0
    data = {"type": "reminder_cancel", "id": reminder_id, "title": "Reminder cancelled", "body": ""}
    sent = 0
    for tok in tokens:
        if send_fcm(tok.token, "Reminder cancelled", "", data=data, account=account):
            sent += 1
    return sent


@router.patch("/{reminder_id}", response_model=schemas.ReminderOut)
def update_reminder(
    reminder_id: str,
    body: schemas.ReminderUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    r = _get_owned_reminder(reminder_id, db, current_user)
    for field, value in body.dict(exclude_unset=True).items():
        setattr(r, field, value)
    db.commit()
    db.refresh(r)
    if r.is_active:
        push_reminder_schedule(db, current_user, r)
    else:
        push_reminder_cancel(db, current_user, r.id)
    return r


@router.post("/{reminder_id}/complete", response_model=schemas.ReminderOut)
def complete_reminder(
    reminder_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Mark a reminder done. If it repeats, advances remind_at to the next occurrence
    and keeps it active; one-shot reminders get deactivated."""
    require_owner(current_user)
    r = _get_owned_reminder(reminder_id, db, current_user)
    nxt = _next_occurrence(r.remind_at, r.repeat_rule)
    if nxt is not None:
        r.remind_at = nxt
        r.is_active = True
    else:
        r.is_active = False
    db.commit()
    db.refresh(r)
    if r.is_active:
        push_reminder_schedule(db, current_user, r)
    else:
        push_reminder_cancel(db, current_user, r.id)
    return r


@router.delete("/{reminder_id}", status_code=204)
def delete_reminder(
    reminder_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    require_owner(current_user)
    r = _get_owned_reminder(reminder_id, db, current_user)
    rid = r.id
    db.delete(r)
    db.commit()
    push_reminder_cancel(db, current_user, rid)


@router.post("/dispatch")
def dispatch_due_reminders(
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Push due reminders to registered Android devices (FCM). Call from a Pi cron,
    e.g. every 5 minutes. If no Firebase service account is saved this still
    returns the due list so a local scheduler can fire notifications without
    polling the API from the phone every few seconds."""
    from datetime import datetime
    from app.push import send_fcm
    from app.server_settings import fcm_service_account
    account = fcm_service_account(db)

    now = datetime.utcnow()
    due = (
        db.query(models.Reminder)
        .join(models.Person)
        .filter(
            models.Person.user_id == vault_id(current_user),
            models.Reminder.is_active == True,  # noqa: E712
            models.Reminder.remind_at <= now,
        )
        .all()
    )
    tokens = (
        db.query(models.DeviceToken)
        .filter(models.DeviceToken.user_id.in_([current_user.id, vault_id(current_user)]))
        .all()
    )
    sent = 0
    payload = []
    for rem in due:
        remind_iso = rem.remind_at.isoformat() if hasattr(rem.remind_at, "isoformat") else str(rem.remind_at)
        payload.append({
            "id": rem.id, "title": rem.title, "description": rem.description,
            "remind_at": remind_iso,
            "repeat_rule": rem.repeat_rule.value,
        })
        for tok in tokens:
            if send_fcm(
                tok.token,
                rem.title,
                rem.description or "",
                data={
                    "type": "reminder_due",
                    "id": rem.id,
                    "title": rem.title,
                    "body": rem.description or "",
                    "remind_at": remind_iso,
                    "repeat_rule": rem.repeat_rule.value,
                },
                account=account,
            ):
                sent += 1
        # Advance / deactivate so we don't re-push every cron tick.
        nxt = _next_occurrence(rem.remind_at, rem.repeat_rule)
        if nxt is not None:
            rem.remind_at = nxt
            rem.is_active = True
            push_reminder_schedule(db, current_user, rem)
        else:
            rem.is_active = False
            push_reminder_cancel(db, current_user, rem.id)
    db.commit()
    return {"due": payload, "pushed": sent}
