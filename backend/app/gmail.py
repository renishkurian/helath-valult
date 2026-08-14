"""Minimal Gmail REST helper (no Google client libraries). Read-only scopes."""
from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from email.utils import parsedate_to_datetime
from typing import Any

from app import gdrive

GMAIL_SCOPE = (
    "https://www.googleapis.com/auth/gmail.readonly "
    "https://www.googleapis.com/auth/userinfo.email"
)
GMAIL_API = "https://gmail.googleapis.com/gmail/v1/users/me"

# Bank / card / UPI alerts + statement-ish subjects (India-focused starter set).
DEFAULT_SYNC_QUERY = (
    "("
    "from:(hdfcbank.net OR alerts.hdfcbank.net OR hdfcbank.bank.in OR sbi.co.in OR onlinesbi.com "
    "OR icicibank.com OR axisbank.com OR kotak.com OR yesbank.in OR indusind.com "
    "OR citibank.com OR americanexpress.com OR amex OR rblbank.com OR idfcfirstbank.com "
    "OR phonepe.com OR googlepay OR paytm.com OR amazonpay)"
    " OR subject:(debited OR credited OR spent OR withdrawn OR \"txn\" OR transaction "
    "OR statement OR \"credit card\" OR \"e-statement\" OR \"e statement\")"
    ") newer_than:45d"
)


def auth_url(client_id: str, redirect_uri: str, state: str) -> str:
    q = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GMAIL_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    })
    return f"{gdrive.AUTH_URL}?{q}"


def exchange_code(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict[str, Any]:
    return gdrive.exchange_code(client_id, client_secret, code, redirect_uri)


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    return gdrive.refresh_access_token(client_id, client_secret, refresh_token)


def user_email(access_token: str) -> str | None:
    return gdrive.user_email(access_token)


def _request_json(url: str, token: str, method: str = "GET", payload: dict | None = None) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Authorization": f"Bearer {token}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=45) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def list_message_ids(
    access_token: str,
    query: str,
    *,
    max_results: int = 50,
    page_token: str | None = None,
) -> tuple[list[str], str | None]:
    params: dict[str, str] = {
        "q": query,
        "maxResults": str(max(1, min(100, max_results))),
    }
    if page_token:
        params["pageToken"] = page_token
    url = f"{GMAIL_API}/messages?{urllib.parse.urlencode(params)}"
    data = _request_json(url, access_token)
    ids = [m["id"] for m in (data.get("messages") or []) if m.get("id")]
    return ids, data.get("nextPageToken")


def get_message(access_token: str, message_id: str) -> dict[str, Any]:
    q = urllib.parse.urlencode({"format": "full"})
    return _request_json(f"{GMAIL_API}/messages/{urllib.parse.quote(message_id)}?{q}", access_token)


def _header(headers: list[dict[str, str]], name: str) -> str | None:
    want = name.lower()
    for h in headers or []:
        if (h.get("name") or "").lower() == want:
            return h.get("value")
    return None


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _walk_parts(part: dict[str, Any], out: list[tuple[str, str]]) -> None:
    mime = (part.get("mimeType") or "").lower()
    body = part.get("body") or {}
    data = body.get("data")
    if data and mime in ("text/plain", "text/html"):
        try:
            out.append((mime, _b64url_decode(data).decode("utf-8", errors="replace")))
        except (ValueError, UnicodeError):
            pass
    for child in part.get("parts") or []:
        _walk_parts(child, out)


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t]+\n")


def html_to_text(html: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n", text)
    text = re.sub(r"(?i)</div>", "\n", text)
    text = _TAG_RE.sub(" ", text)
    text = (
        text.replace("&nbsp;", " ")
        .replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
    )
    text = _WS_RE.sub("\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_message(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize a Gmail message resource into subject/from/date/text."""
    headers = (payload.get("payload") or {}).get("headers") or []
    subject = _header(headers, "Subject")
    from_addr = _header(headers, "From")
    date_hdr = _header(headers, "Date")
    received_at = None
    if date_hdr:
        try:
            received_at = parsedate_to_datetime(date_hdr)
            if received_at.tzinfo:
                received_at = received_at.replace(tzinfo=None)
        except (TypeError, ValueError, IndexError, OverflowError):
            received_at = None

    parts: list[tuple[str, str]] = []
    root = payload.get("payload") or {}
    _walk_parts(root, parts)
    plain = next((t for m, t in parts if m == "text/plain"), None)
    html = next((t for m, t in parts if m == "text/html"), None)
    text = (plain or "").strip() or (html_to_text(html) if html else "")
    if not text:
        text = (payload.get("snippet") or "").strip()

    return {
        "id": payload.get("id"),
        "thread_id": payload.get("threadId"),
        "subject": subject,
        "from_addr": from_addr,
        "received_at": received_at,
        "snippet": payload.get("snippet"),
        "text": text,
    }


def looks_like_statement(subject: str | None, text: str) -> bool:
    blob = f"{subject or ''}\n{text or ''}".lower()
    keys = (
        "e-statement", "estatement", "e statement", "credit card statement",
        "card statement", "monthly statement", "statement of account",
    )
    return any(k in blob for k in keys)


def is_http_error(exc: BaseException) -> bool:
    return isinstance(exc, (urllib.error.URLError, urllib.error.HTTPError, TimeoutError))
