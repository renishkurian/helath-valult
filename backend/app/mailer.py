"""Outbound email for Vault Send Email OTP.

Super Admin chooses:
  - system (default): env SYSTEM_SMTP_* / localhost sendmail-style SMTP
  - smtp: custom host/user/password saved under Server settings
"""
from __future__ import annotations

import logging
import smtplib
import ssl
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.config import settings
from app import server_settings as ss

log = logging.getLogger("healthvault.mailer")


def mail_mode(db: Session | None = None) -> str:
    mode = (ss.get_plain(db, ss.MAIL_MODE_KEY) if db is not None else "") or "system"
    return "smtp" if mode.strip().lower() == "smtp" else "system"


def _system_cfg() -> dict:
    return {
        "host": (getattr(settings, "SYSTEM_SMTP_HOST", None) or "127.0.0.1").strip(),
        "port": int(getattr(settings, "SYSTEM_SMTP_PORT", 25) or 25),
        "user": (getattr(settings, "SYSTEM_SMTP_USER", None) or "").strip(),
        "password": (getattr(settings, "SYSTEM_SMTP_PASSWORD", None) or "").strip(),
        "from_addr": (getattr(settings, "SYSTEM_MAIL_FROM", None) or "vault@localhost").strip(),
        "tls": bool(getattr(settings, "SYSTEM_SMTP_TLS", False)),
    }


def _smtp_cfg(db: Session) -> dict:
    host = ss.get_plain(db, ss.SMTP_HOST_KEY)
    port = ss.clamp_int(ss.get_plain(db, ss.SMTP_PORT_KEY), 587, 1, 65535)
    user = ss.get_plain(db, ss.SMTP_USER_KEY)
    password = ss.get_secret(db, ss.SMTP_PASSWORD_KEY)
    from_addr = ss.get_plain(db, ss.SMTP_FROM_KEY) or user
    tls = ss.get_plain(db, ss.SMTP_TLS_KEY) != "0"
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "from_addr": from_addr or "vault@localhost",
        "tls": tls,
    }


def mail_config(db: Session | None = None) -> dict:
    if db is not None and mail_mode(db) == "smtp":
        cfg = _smtp_cfg(db)
        if cfg["host"]:
            return {**cfg, "mode": "smtp"}
    cfg = _system_cfg()
    return {**cfg, "mode": "system"}


def mail_ready(db: Session | None = None) -> bool:
    cfg = mail_config(db)
    return bool(cfg.get("host") and cfg.get("from_addr"))


def send_email(
    to: str,
    subject: str,
    body: str,
    *,
    db: Session | None = None,
) -> bool:
    to_addr = (to or "").strip()
    if not to_addr or "@" not in to_addr:
        return False
    cfg = mail_config(db)
    if not cfg.get("host"):
        log.warning("mail: no SMTP host configured")
        return False
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = cfg["from_addr"]
    msg["To"] = to_addr
    msg.set_content(body)
    try:
        if cfg.get("tls") and int(cfg["port"]) != 465:
            context = ssl.create_default_context()
            with smtplib.SMTP(cfg["host"], int(cfg["port"]), timeout=20) as smtp:
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
                if cfg.get("user"):
                    smtp.login(cfg["user"], cfg["password"] or "")
                smtp.send_message(msg)
        elif int(cfg["port"]) == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(cfg["host"], int(cfg["port"]), context=context, timeout=20) as smtp:
                if cfg.get("user"):
                    smtp.login(cfg["user"], cfg["password"] or "")
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(cfg["host"], int(cfg["port"]), timeout=20) as smtp:
                if cfg.get("user"):
                    smtp.login(cfg["user"], cfg["password"] or "")
                smtp.send_message(msg)
        return True
    except Exception:
        log.exception("mail: send failed to %s", to_addr)
        return False


def send_vault_otp(to: str, code: str, send_name: str, *, db: Session | None = None) -> bool:
    subject = f"Vault access code — {send_name}"
    body = (
        f"Your one-time code for “{send_name}” is:\n\n"
        f"  {code}\n\n"
        f"It expires in 10 minutes. If you did not request this, ignore this email.\n"
    )
    return send_email(to, subject, body, db=db)
