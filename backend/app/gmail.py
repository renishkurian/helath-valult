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
    "from:(hdfcbank.net OR hdfcbank.com OR hdfcbank.co.in OR alerts.hdfcbank.net "
    "OR alerts.hdfcbank.com OR instalerts.hdfcbank.com OR hdfcbank.bank.in "
    "OR sbi.co.in OR onlinesbi.com OR icicibank.com OR axisbank.com OR kotak.com "
    "OR yesbank.in OR indusind.com OR citibank.com OR americanexpress.com OR amex "
    "OR rblbank.com OR idfcfirstbank.com OR southindianbank.com OR southindianbank.co.in "
    "OR sib.co.in OR sib.bank.in OR sibalerts OR phonepe.com OR googlepay OR paytm.com "
    "OR amazonpay)"
    " OR subject:(debit OR debited OR credited OR spent OR withdrawn OR \"txn\" OR transaction "
    "OR statement OR \"credit card\" OR \"e-statement\" OR \"e statement\" "
    "OR \"SIB Alerts\" OR \"SOUTH INDIAN BANK\" OR \"Debit Alert\")"
    " OR from:alerts@sib.co.in OR from:sib.co.in OR from:sib.bank.in"
    " OR (\"SOUTH INDIAN BANK\" spent)"
    ") newer_than:45d"
)

# Password-protected e-statements attached as PDFs (separate from alert text).
DEFAULT_PDF_QUERY = (
    "has:attachment filename:pdf newer_than:90d "
    "("
    "subject:(statement OR e-statement OR estatement OR \"e statement\" "
    "OR \"credit card\" OR \"account statement\" OR \"monthly statement\") "
    "OR from:(hdfcbank OR sbi.co.in OR onlinesbi OR icicibank OR axisbank "
    "OR kotak.com OR yesbank OR indusind OR rblbank OR idfcfirstbank "
    "OR southindianbank OR sib.co.in OR sib.bank.in OR sibalerts "
    "OR americanexpress OR amex)"
    ")"
)

_PDF_MIMES = ("application/pdf", "application/x-pdf")


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


def list_message_ids_paged(
    access_token: str,
    query: str,
    *,
    limit: int = 200,
) -> list[str]:
    """Walk Gmail pages until `limit` ids (Gmail caps each page at 100)."""
    want = max(1, min(500, limit))
    ids: list[str] = []
    page_token: str | None = None
    seen: set[str] = set()
    while len(ids) < want:
        batch, page_token = list_message_ids(
            access_token, query,
            max_results=min(100, want - len(ids)),
            page_token=page_token,
        )
        for mid in batch:
            if mid in seen:
                continue
            seen.add(mid)
            ids.append(mid)
            if len(ids) >= want:
                break
        if not page_token or not batch:
            break
    return ids


def get_attachment_bytes(access_token: str, message_id: str, attachment_id: str) -> bytes:
    # Attachment ids often contain "/" and "+" — encode the whole id as one path segment.
    url = (
        f"{GMAIL_API}/messages/{urllib.parse.quote(message_id, safe='')}"
        f"/attachments/{urllib.parse.quote(attachment_id, safe='')}"
    )
    data = _request_json(url, access_token)
    raw = data.get("data") or ""
    if not raw:
        return b""
    return _b64url_decode(raw)


def get_attachment(access_token: str, message_id: str, attachment_id: str) -> str:
    return get_attachment_bytes(access_token, message_id, attachment_id).decode(
        "utf-8", errors="replace",
    )


def get_message(access_token: str, message_id: str) -> dict[str, Any]:
    q = urllib.parse.urlencode({"format": "full"})
    return _request_json(
        f"{GMAIL_API}/messages/{urllib.parse.quote(message_id, safe='')}?{q}",
        access_token,
    )


def _header(headers: list[dict[str, str]], name: str) -> str | None:
    want = name.lower()
    for h in headers or []:
        if (h.get("name") or "").lower() == want:
            return h.get("value")
    return None


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def _walk_parts(
    part: dict[str, Any],
    out: list[tuple[str, str]],
    pending: list[tuple[str, str]] | None = None,
) -> None:
    mime = (part.get("mimeType") or "").lower()
    body = part.get("body") or {}
    data = body.get("data")
    aid = body.get("attachmentId")
    if data and mime in ("text/plain", "text/html"):
        try:
            out.append((mime, _b64url_decode(data).decode("utf-8", errors="replace")))
        except (ValueError, UnicodeError):
            pass
    elif aid and pending is not None and mime in ("text/plain", "text/html"):
        pending.append((mime, aid))
    for child in part.get("parts") or []:
        _walk_parts(child, out, pending)


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
    pending: list[tuple[str, str]] = []
    root = payload.get("payload") or {}
    _walk_parts(root, parts, pending)
    plain = next((t for m, t in parts if m == "text/plain"), None)
    html = next((t for m, t in parts if m == "text/html"), None)
    snippet = (payload.get("snippet") or "").strip()
    text = (plain or "").strip() or (html_to_text(html) if html else "")
    # SIB HTML alerts are image-only; Gmail snippet still has "INR 5775 was spent…".
    if snippet and (not text or len(text) < 80):
        text = snippet if not text else f"{text}\n{snippet}"

    return {
        "id": payload.get("id"),
        "thread_id": payload.get("threadId"),
        "subject": subject,
        "from_addr": from_addr,
        "received_at": received_at,
        "snippet": payload.get("snippet"),
        "text": text,
        "pending_attachments": pending,
    }


def hydrate_message_text(access_token: str, mail: dict[str, Any]) -> dict[str, Any]:
    """Fetch Gmail parts that only have attachmentId (common for HTML alerts)."""
    pending = mail.get("pending_attachments") or []
    if not pending or not mail.get("id"):
        return mail
    plains: list[str] = []
    htmls: list[str] = []
    for mime, aid in pending:
        try:
            body = get_attachment(access_token, mail["id"], aid)
        except Exception:  # noqa: BLE001 — per-part soft fail
            continue
        if not body.strip():
            continue
        if mime == "text/html":
            htmls.append(body)
        else:
            plains.append(body)
    text = "\n".join(plains).strip() or html_to_text("\n".join(htmls))
    if text:
        mail["text"] = text
    mail["pending_attachments"] = []
    return mail


def _walk_pdfs(part: dict[str, Any], out: list[dict[str, Any]]) -> None:
    mime = (part.get("mimeType") or "").lower()
    filename = (part.get("filename") or "").strip()
    body = part.get("body") or {}
    aid = body.get("attachmentId")
    data = body.get("data")
    is_pdf = mime in _PDF_MIMES or filename.lower().endswith(".pdf")
    if is_pdf and (aid or data):
        raw = None
        if data and not aid:
            try:
                raw = _b64url_decode(data)
            except (ValueError, UnicodeError):
                raw = None
        out.append({
            "filename": filename or "statement.pdf",
            "mime": mime or "application/pdf",
            "attachment_id": aid,
            "data": raw,
            "size": int(body.get("size") or 0),
        })
    for child in part.get("parts") or []:
        _walk_pdfs(child, out)


def extract_pdf_parts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect PDF attachments from a Gmail message resource."""
    out: list[dict[str, Any]] = []
    _walk_pdfs(payload.get("payload") or {}, out)
    return out


def looks_like_statement(subject: str | None, text: str | None = None) -> bool:
    """True only from the subject — alert footers often mention 'statement'."""
    subj = (subject or "").lower()
    keys = (
        "e-statement", "estatement", "e statement", "credit card statement",
        "card statement", "monthly statement", "statement of account",
        "account statement",
    )
    return any(k in subj for k in keys)


def is_http_error(exc: BaseException) -> bool:
    return isinstance(exc, (urllib.error.URLError, urllib.error.HTTPError, TimeoutError))
