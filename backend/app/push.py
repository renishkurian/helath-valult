"""Optional FCM HTTP v1 send for login-approve and reminder dispatch.

Uses a Firebase service account (Super Admin → Server settings). If none is
saved, dispatch is a no-op — the Android app still polls while it is open and
schedules local AlarmManager reminders itself.
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Any

from jose import jwt

_FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_TOKEN_URL = "https://oauth2.googleapis.com/token"
_cached: dict[str, Any] = {"email": "", "token": "", "exp": 0.0}


def _access_token(account: dict) -> str:
    email = str(account.get("client_email") or "")
    now = time.time()
    if _cached["email"] == email and _cached["token"] and _cached["exp"] > now + 60:
        return str(_cached["token"])
    assertion = jwt.encode(
        {
            "iss": email,
            "sub": email,
            "aud": _TOKEN_URL,
            "iat": int(now),
            "exp": int(now) + 3600,
            "scope": _FCM_SCOPE,
        },
        account["private_key"],
        algorithm="RS256",
    )
    body = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion,
    }).encode("utf-8")
    req = urllib.request.Request(
        _TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    token = str(payload.get("access_token") or "")
    if not token:
        raise RuntimeError("FCM token exchange returned no access_token")
    _cached.update(email=email, token=token, exp=now + int(payload.get("expires_in") or 3500))
    return token


def send_fcm(
    token: str,
    title: str,
    body: str,
    data: dict | None = None,
    *,
    account: dict | None = None,
) -> bool:
    if not token or not account:
        return False
    project = str(account.get("project_id") or "").strip()
    if not project:
        return False
    message: dict[str, Any] = {
        "token": token,
        "notification": {"title": title, "body": body or ""},
        "android": {"priority": "HIGH"},
    }
    if data:
        message["data"] = {str(k): str(v) for k, v in data.items()}
    payload = json.dumps({"message": message}).encode("utf-8")
    try:
        bearer = _access_token(account)
        req = urllib.request.Request(
            f"https://fcm.googleapis.com/v1/projects/{project}/messages:send",
            data=payload,
            headers={
                "Authorization": f"Bearer {bearer}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False
