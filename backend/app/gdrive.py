"""Minimal Google Drive REST helper (no Google client libraries)."""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

LOGIN_SCOPE = "openid email profile"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file https://www.googleapis.com/auth/userinfo.email"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DRIVE_FILES = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
USERINFO = "https://www.googleapis.com/oauth2/v2/userinfo"
FOLDER_NAME = "Health Vault Backups"


def login_auth_url(client_id: str, redirect_uri: str, state: str) -> str:
    q = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": LOGIN_SCOPE,
        "prompt": "select_account",
        "state": state,
    })
    return f"{AUTH_URL}?{q}"


def user_profile(access_token: str) -> dict[str, Any]:
    """Fetch user profile (email, name, picture, verified_email) from Google userinfo endpoint."""
    try:
        info = _request_json(USERINFO, access_token)
        return {
            "email": (info.get("email") or "").strip().lower(),
            "name": (info.get("name") or "").strip(),
            "picture": info.get("picture"),
            "verified_email": info.get("verified_email", True),
        }
    except Exception:
        return {}


def auth_url(client_id: str, redirect_uri: str, state: str) -> str:
    q = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": DRIVE_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    })
    return f"{AUTH_URL}?{q}"


def _oauth_http_error(exc: urllib.error.HTTPError) -> None:
    body = exc.read().decode(errors="replace")
    try:
        err = json.loads(body)
    except json.JSONDecodeError:
        raise RuntimeError(f"Google OAuth failed (HTTP {exc.code})") from exc
    code = str(err.get("error") or "").strip()
    desc = str(err.get("error_description") or "").strip()
    if code == "invalid_grant":
        raise RuntimeError(
            "Google access expired or revoked — disconnect and reconnect Gmail in Expense Analyser settings"
        ) from exc
    if desc:
        raise RuntimeError(f"Google OAuth error: {desc}") from exc
    if code:
        raise RuntimeError(f"Google OAuth error: {code}") from exc
    raise RuntimeError(f"Google OAuth failed (HTTP {exc.code})") from exc


def _post_form(url: str, data: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Content-Type": "application/x-www-form-urlencoded",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        _oauth_http_error(exc)


def _request_json(url: str, token: str, method: str = "GET", payload: dict | None = None) -> dict[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Authorization": f"Bearer {token}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def exchange_code(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict[str, Any]:
    return _post_form(TOKEN_URL, {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    })


def refresh_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    data = _post_form(TOKEN_URL, {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })
    token = data.get("access_token")
    if not token:
        raise RuntimeError("Google did not return an access token")
    return token


def user_email(access_token: str) -> str | None:
    try:
        info = _request_json(USERINFO, access_token)
        return info.get("email")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError, KeyError):
        return None


def ensure_folder(access_token: str, folder_id: str | None) -> str:
    if folder_id:
        try:
            _request_json(f"{DRIVE_FILES}/{urllib.parse.quote(folder_id)}?fields=id,trashed", access_token)
            return folder_id
        except urllib.error.HTTPError:
            pass
    q = urllib.parse.urlencode({
        "q": f"name='{FOLDER_NAME}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        "fields": "files(id,name)",
        "pageSize": "1",
    })
    listing = _request_json(f"{DRIVE_FILES}?{q}", access_token)
    files = listing.get("files") or []
    if files:
        return files[0]["id"]
    created = _request_json(DRIVE_FILES, access_token, method="POST", payload={
        "name": FOLDER_NAME,
        "mimeType": "application/vnd.google-apps.folder",
    })
    return created["id"]


def upload_bytes(access_token: str, folder_id: str, name: str, blob: bytes, mime: str = "application/octet-stream") -> str:
    boundary = "====healthvaultdrive===="
    meta = json.dumps({"name": name, "parents": [folder_id]})
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
        f"--{boundary}\r\nContent-Type: {mime}\r\n\r\n"
    ).encode() + blob + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        f"{DRIVE_UPLOAD}?uploadType=multipart",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": f"multipart/related; boundary={boundary}",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        out = json.loads(resp.read().decode())
    return out.get("id") or ""


def list_backups(access_token: str, folder_id: str) -> list[dict[str, Any]]:
    q = urllib.parse.urlencode({
        "q": f"'{folder_id}' in parents and trashed=false",
        "fields": "files(id,name,createdTime,size)",
        "orderBy": "createdTime desc",
        "pageSize": "100",
    })
    listing = _request_json(f"{DRIVE_FILES}?{q}", access_token)
    return listing.get("files") or []


def get_file(access_token: str, file_id: str) -> dict[str, Any]:
    fields = "id,name,createdTime,size,parents,trashed"
    return _request_json(
        f"{DRIVE_FILES}/{urllib.parse.quote(file_id)}?fields={fields}",
        access_token,
    )


def download_bytes(access_token: str, file_id: str, *, max_bytes: int = 512 * 1024 * 1024) -> bytes:
    """Download a Drive file's content (alt=media). Caps size to avoid DoS."""
    meta = get_file(access_token, file_id)
    if meta.get("trashed"):
        raise RuntimeError("Backup file is in Drive trash")
    try:
        size = int(meta.get("size") or 0)
    except (TypeError, ValueError):
        size = 0
    if size and size > max_bytes:
        raise RuntimeError(f"Backup is too large to restore ({size} bytes)")
    url = f"{DRIVE_FILES}/{urllib.parse.quote(file_id)}?alt=media"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise RuntimeError("Backup is too large to restore")
            chunks.append(chunk)
    return b"".join(chunks)


def delete_file(access_token: str, file_id: str) -> None:
    req = urllib.request.Request(
        f"{DRIVE_FILES}/{urllib.parse.quote(file_id)}",
        method="DELETE",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()
