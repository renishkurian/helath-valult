"""Open Graph / Twitter card preview fetch for URL Vault.

Fails soft: callers always get a dict (possibly empty). Private/loopback
hosts are skipped so a saved bookmark cannot be used as SSRF against the Pi.
"""
from __future__ import annotations

import ipaddress
import re
import socket
from html.parser import HTMLParser
from typing import Optional
from urllib.parse import parse_qs, quote, urljoin, urlparse
from urllib.request import Request, urlopen

_MAX_BYTES = 512_000
_MAX_IMAGE_BYTES = 2_000_000
_TIMEOUT = 8
_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


class _OgParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.og: dict[str, str] = {}
        self.title: Optional[str] = None
        self.favicon: Optional[str] = None
        self._in_title = False
        self._title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs):
        ad = {k.lower(): v for k, v in attrs if k}
        if tag == "meta":
            prop = (ad.get("property") or ad.get("name") or "").strip().lower()
            content = (ad.get("content") or "").strip()
            if content and (prop.startswith("og:") or prop.startswith("twitter:")):
                self.og.setdefault(prop, content)
        elif tag == "title":
            self._in_title = True
        elif tag == "link":
            rel = (ad.get("rel") or "").lower()
            href = ad.get("href")
            if href and "icon" in rel:
                if not self.favicon or rel in ("icon", "shortcut icon"):
                    self.favicon = href

    def handle_data(self, data: str):
        if self._in_title:
            self._title_parts.append(data)

    def handle_endtag(self, tag: str):
        if tag == "title":
            self._in_title = False
            if self.title is None:
                text = "".join(self._title_parts).strip()
                if text:
                    self.title = text[:500]


def normalize_url(raw: str) -> str:
    url = (raw or "").strip()
    if not url:
        raise ValueError("URL is required")
    if not re.match(r"^[a-z][a-z0-9+.-]*://", url, re.I):
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Only http(s) URLs are allowed")
    return url


def hostname_of(url: str) -> str:
    host = urlparse(url).hostname or ""
    return host[4:] if host.startswith("www.") else host


def _host_is_public(host: str) -> bool:
    if not host or host.lower() in ("localhost", "localhost.localdomain"):
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            return False
    return True


def _youtube_id(url: str) -> Optional[str]:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host == "youtu.be":
        vid = (parsed.path or "").strip("/").split("/")[0]
        return vid if re.fullmatch(r"[\w-]{11}", vid or "") else None
    if host in ("youtube.com", "m.youtube.com", "music.youtube.com"):
        vid = (parse_qs(parsed.query).get("v") or [""])[0]
        if re.fullmatch(r"[\w-]{11}", vid or ""):
            return vid
        match = re.match(r"/(?:embed|shorts|live)/([\w-]{11})", parsed.path or "")
        if match:
            return match.group(1)
    return None


def _read_public(url: str, *, limit: int, accept: str) -> Optional[tuple[bytes, str, str]]:
    """GET a public http(s) URL. Returns (body, content-type, final_url) or None."""
    try:
        url = normalize_url(url)
    except ValueError:
        return None
    host = urlparse(url).hostname or ""
    if not _host_is_public(host):
        return None
    try:
        req = Request(url, headers={"User-Agent": _UA, "Accept": accept})
        with urlopen(req, timeout=_TIMEOUT) as resp:
            final_url = resp.geturl() or url
            final_host = urlparse(final_url).hostname or ""
            if not _host_is_public(final_host):
                return None
            ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            raw = resp.read(limit + 1)
    except Exception:
        return None
    if len(raw) > limit:
        raw = raw[:limit]
    return raw, ctype, final_url


def _youtube_oembed(page_url: str) -> dict:
    endpoint = "https://www.youtube.com/oembed?format=json&url=" + quote(page_url, safe="")
    got = _read_public(endpoint, limit=64_000, accept="application/json")
    if not got:
        return {}
    raw, ctype, _final = got
    if "json" not in ctype and raw[:1] not in (b"{", b"["):
        return {}
    try:
        import json
        data = json.loads(raw.decode("utf-8", errors="ignore"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        "title": (data.get("title") or "").strip()[:500] or None,
        "image": (data.get("thumbnail_url") or "").strip()[:2000] or None,
        "site_name": (data.get("provider_name") or "YouTube").strip()[:255] or None,
        "author": (data.get("author_name") or "").strip()[:255] or None,
    }


def fetch_image_bytes(url: str) -> Optional[tuple[bytes, str]]:
    """Download a preview image. None on failure or a non-image response."""
    got = _read_public(url, limit=_MAX_IMAGE_BYTES, accept="image/*,*/*;q=0.8")
    if not got:
        return None
    raw, ctype, _final = got
    if not raw:
        return None
    if not ctype.startswith("image/"):
        if raw.startswith(b"\xff\xd8"):
            ctype = "image/jpeg"
        elif raw.startswith(b"\x89PNG"):
            ctype = "image/png"
        elif raw.startswith(b"GIF8"):
            ctype = "image/gif"
        elif raw.startswith(b"RIFF") and b"WEBP" in raw[:16]:
            ctype = "image/webp"
        else:
            return None
    if ctype == "image/svg+xml":
        return None
    return raw, ctype


def fetch_preview(url: str) -> dict:
    """Return og/twitter fields. Never raises for network/parse failures."""
    try:
        url = normalize_url(url)
    except ValueError:
        return {}
    host = urlparse(url).hostname or ""
    if not _host_is_public(host):
        return {}
    got = _read_public(url, limit=_MAX_BYTES, accept="text/html,application/xhtml+xml")
    if not got:
        return _preview_fallbacks(url, {})
    raw, ctype, final_url = got
    if "html" not in ctype and "xml" not in ctype and ctype:
        return _preview_fallbacks(url, {"site_name": hostname_of(url)})
    try:
        text = raw.decode("utf-8", errors="ignore")
    except Exception:
        return {}
    parser = _OgParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        pass
    og = parser.og
    title = og.get("og:title") or og.get("twitter:title") or parser.title
    desc = og.get("og:description") or og.get("twitter:description")
    image = og.get("og:image") or og.get("twitter:image") or og.get("twitter:image:src")
    site = og.get("og:site_name") or hostname_of(final_url)
    favicon = parser.favicon
    if image:
        image = urljoin(final_url, image)
    if favicon:
        favicon = urljoin(final_url, favicon)
    else:
        favicon = urljoin(final_url, "/favicon.ico")
    preview = {
        "title": (title or "").strip()[:500] or None,
        "description": (desc or "").strip()[:2000] or None,
        "image": (image or "").strip()[:2000] or None,
        "site_name": (site or "").strip()[:255] or None,
        "favicon_url": (favicon or "").strip()[:2000] or None,
    }
    return _preview_fallbacks(final_url or url, preview)


def _preview_fallbacks(url: str, preview: dict) -> dict:
    """Fill title and image when the HTML page hid them (YouTube consent wall)."""
    vid = _youtube_id(url)
    if not vid:
        return preview
    if not preview.get("image"):
        preview["image"] = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
    if not preview.get("site_name"):
        preview["site_name"] = "YouTube"
    title = (preview.get("title") or "").strip().lower()
    generic = title in {"", "youtube", "youtube.com", "- youtube"} or "before you continue" in title
    if not generic:
        return preview
    extra = _youtube_oembed(url)
    if extra.get("title"):
        preview["title"] = extra["title"]
    if extra.get("image") and not preview.get("image"):
        preview["image"] = extra["image"]
    if extra.get("author") and not preview.get("description"):
        preview["description"] = extra["author"]
    return preview
