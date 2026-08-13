from datetime import timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.deps import get_current_user, get_owned_person

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
    q = db.query(models.Reminder).join(models.Person).filter(models.Person.user_id == current_user.id)
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
    get_owned_person(body.person_id, db, current_user)
    reminder = models.Reminder(**body.dict())
    db.add(reminder)
    db.commit()
    db.refresh(reminder)
    return reminder


def _get_owned_reminder(reminder_id: str, db: Session, current_user: models.User) -> models.Reminder:
    r = (
        db.query(models.Reminder)
        .join(models.Person)
        .filter(models.Reminder.id == reminder_id, models.Person.user_id == current_user.id)
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return r


@router.patch("/{reminder_id}", response_model=schemas.ReminderOut)
def update_reminder(
    reminder_id: str,
    body: schemas.ReminderUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    r = _get_owned_reminder(reminder_id, db, current_user)
    for field, value in body.dict(exclude_unset=True).items():
        setattr(r, field, value)
    db.commit()
    db.refresh(r)
    return r


@router.post("/{reminder_id}/complete", response_model=schemas.ReminderOut)
def complete_reminder(
    reminder_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Mark a reminder done. If it repeats, advances remind_at to the next occurrence
    and keeps it active; one-shot reminders get deactivated."""
    r = _get_owned_reminder(reminder_id, db, current_user)
    nxt = _next_occurrence(r.remind_at, r.repeat_rule)
    if nxt is not None:
        r.remind_at = nxt
        r.is_active = True
    else:
        r.is_active = False
    db.commit()
    db.refresh(r)
    return r


@router.delete("/{reminder_id}", status_code=204)
def delete_reminder(
    reminder_id: str,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    r = _get_owned_reminder(reminder_id, db, current_user)
    db.delete(r)
    db.commit()
