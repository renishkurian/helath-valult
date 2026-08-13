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
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

_MAX_BYTES = 512_000
_TIMEOUT = 8
_UA = "HealthVault-URLVault/1.0 (+https://localhost)"


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


def fetch_preview(url: str) -> dict:
    """Return og/twitter fields. Never raises for network/parse failures."""
    try:
        url = normalize_url(url)
    except ValueError:
        return {}
    host = urlparse(url).hostname or ""
    if not _host_is_public(host):
        return {}
    try:
        req = Request(url, headers={"User-Agent": _UA, "Accept": "text/html,application/xhtml+xml"})
        with urlopen(req, timeout=_TIMEOUT) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if "html" not in ctype and "xml" not in ctype and ctype:
                return {"site_name": hostname_of(url)}
            raw = resp.read(_MAX_BYTES)
            final_url = resp.geturl() or url
    except Exception:
        return {}
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
    return {
        "title": (title or "").strip()[:500] or None,
        "description": (desc or "").strip()[:2000] or None,
        "image": (image or "").strip()[:2000] or None,
        "site_name": (site or "").strip()[:255] or None,
        "favicon_url": (favicon or "").strip()[:2000] or None,
    }
