"""Telegram Bot API helpers for reminder notifications."""
from __future__ import annotations

import logging
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

from sqlalchemy.orm import Session

from app import models
from app.deps import vault_id

log = logging.getLogger("vault.telegram")

TELEGRAM_API = "https://api.telegram.org"


def telegram_bot_token(db: Session) -> str:
    from app.server_settings import TELEGRAM_BOT_TOKEN_KEY, get_secret
    from app.config import settings

    token = get_secret(db, TELEGRAM_BOT_TOKEN_KEY)
    if token:
        return token
    return (getattr(settings, "TELEGRAM_BOT_TOKEN", "") or "").strip()


def send_telegram_message(token: str, chat_id: str, text: str, *, parse_mode: str = "HTML") -> bool:
    if not token or not chat_id or not text:
        return False
    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": str(chat_id).strip(),
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= getattr(resp, "status", 200) < 300
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        log.warning("telegram send failed chat_id=%s: %s", chat_id, exc)
        return False


def list_recipients(db: Session, user: models.User, *, enabled_only: bool = False) -> list[models.VaultTelegramRecipient]:
    q = (
        db.query(models.VaultTelegramRecipient)
        .filter(models.VaultTelegramRecipient.user_id == vault_id(user))
        .order_by(models.VaultTelegramRecipient.created_at.asc())
    )
    if enabled_only:
        q = q.filter(models.VaultTelegramRecipient.enabled.is_(True))
    return q.all()


def format_reminder_message(rem: models.Reminder, person_name: Optional[str] = None) -> str:
    when = rem.remind_at.strftime("%d %b %Y, %I:%M %p") if rem.remind_at else "now"
    who = f" · {person_name}" if person_name else ""
    lines = [
        f"<b>Family Vault reminder</b>{who}",
        f"<b>{rem.title}</b>",
        f"When: {when}",
    ]
    if rem.description:
        lines.append(rem.description)
    rule = rem.repeat_rule.value if rem.repeat_rule is not None else "none"
    if rule and rule != "none":
        lines.append(f"Repeat: {rule}")
    return "\n".join(lines)


def notify_reminder_telegram(db: Session, rem: models.Reminder) -> int:
    """Send this reminder to all enabled Telegram chat IDs for its vault. Returns send count."""
    if not getattr(rem, "notify_telegram", False):
        return 0
    token = telegram_bot_token(db)
    if not token:
        return 0
    person = rem.person
    if person is None:
        person = db.query(models.Person).filter(models.Person.id == rem.person_id).first()
    if not person:
        return 0
    recipients = (
        db.query(models.VaultTelegramRecipient)
        .filter(
            models.VaultTelegramRecipient.user_id == person.user_id,
            models.VaultTelegramRecipient.enabled.is_(True),
        )
        .all()
    )
    if not recipients:
        return 0
    text = format_reminder_message(rem, person.name)
    sent = 0
    for row in recipients:
        if send_telegram_message(token, row.chat_id, text):
            sent += 1
    return sent


def run_due_reminder_notifications() -> dict:
    """Scheduler entry: process due reminders (FCM + Telegram) for every vault."""
    from app.database import SessionLocal
    from app.routers.reminders import process_due_reminders

    db = SessionLocal()
    try:
        return process_due_reminders(db, vault_user_id=None)
    except Exception:
        db.rollback()
        log.exception("due reminder notification job failed")
        return {"due": [], "pushed": 0, "telegram_sent": 0, "error": True}
    finally:
        db.close()
