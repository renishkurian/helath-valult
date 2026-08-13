"""Optional FCM HTTP v1-less legacy send, used by /reminders/dispatch.

If FCM_SERVER_KEY is unset, dispatch is a no-op besides returning due reminders
(the Android app schedules local AlarmManager notifications itself).
"""
from __future__ import annotations

import json
import urllib.request

from app.config import settings


def send_fcm(token: str, title: str, body: str) -> bool:
    key = getattr(settings, "FCM_SERVER_KEY", "") or ""
    if not key:
        return False
    payload = json.dumps({
        "to": token,
        "notification": {"title": title, "body": body or "", "sound": "default"},
        "priority": "high",
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://fcm.googleapis.com/fcm/send",
        data=payload,
        headers={
            "Authorization": f"key={key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False
