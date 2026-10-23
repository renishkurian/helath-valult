"""Company logos for dividend issuers.

The page only reads rows already stored. Sync downloads a logo once and
keeps the file under /static/company-logos/.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from app import models

_DIR = Path(__file__).resolve().parent / "static" / "company-logos"

# Longer phrases first. Statement text is often truncated.
_DOMAINS: list[tuple[str, str]] = [
    ("bharat heavy", "bhel.com"),
    ("oil and natural", "ongcindia.com"),
    ("indian energy", "iexindia.com"),
    ("datamatics", "datamatics.com"),
    ("dr reddy", "drreddys.com"),
    ("coal india", "coalindia.in"),
    ("welspun", "welspun.com"),
    ("hpcl", "hpcl.co.in"),
    ("ntpc", "ntpc.co.in"),
    ("gail", "gailonline.com"),
    ("ongc", "ongcindia.com"),
    ("bhel", "bhel.com"),
    ("ioc", "iocl.com"),
    ("bpcl", "bharatpetroleum.in"),
    ("power grid", "powergrid.in"),
    ("sbin", "sbi.co.in"),
    ("sbi", "sbi.co.in"),
    ("itc", "itcportal.com"),
    ("tcs", "tcs.com"),
    ("infosys", "infosys.com"),
    ("reliance", "ril.com"),
    ("hdfc", "hdfcbank.com"),
]


def issuer_name(desc: str) -> str:
    text = re.sub(r"\s+", " ", desc or "").strip()
    m = re.search(r"ACHCr\s+[A-Z0-9]+\s+(.+?)\s+-\s+\d", text, re.I)
    name = m.group(1).strip(" -") if m else ""
    if not name:
        for pat in (
            r"DIVIDEND(?:\s+FROM)?[:\s/-]+([A-Za-z0-9][A-Za-z0-9 &.\-]{2,48})",
            r"\bDIV[:\s/-]+([A-Za-z0-9][A-Za-z0-9 &.\-]{2,48})",
        ):
            hit = re.search(pat, text, re.I)
            if hit:
                name = re.split(r"[/\n]", hit.group(1))[0].strip(" -:")
                break
    if not name:
        name = text[:48]
    name = re.sub(r"\s*(FNL[-\s]?DIV|FIN\s+DIV|FNLDIV|DIVIDEND).*$", "", name, flags=re.I)
    name = re.sub(r"[\s\-]*\d{2,4}(?:[\s\-]+\d{2,4})?\s*$", "", name).strip(" -")
    return (name[:48] or "Unknown").title()


_BUNDLED: list[tuple[str, str]] = [
    ("bharat heavy", "bhel.png"),
    ("oil and natural", "ongc.png"),
    ("indian energy", "iex.png"),
    ("datamatics", "datamatics.png"),
    ("dr reddy", "drreddys.png"),
    ("coal india", "coal-india.png"),
    ("welspun", "welspun.png"),
    ("hpcl", "hpcl.png"),
    ("ntpc", "ntpc.png"),
    ("gail", "gail.png"),
    ("ongc", "ongc.png"),
    ("bhel", "bhel.png"),
]


def name_key(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())[:80]


def _bundled(name: str) -> str | None:
    key = name_key(name)
    for needle, filename in _BUNDLED:
        if needle in key and (_DIR / filename).is_file():
            return f"/static/company-logos/{filename}"
    return None
    return re.sub(r"\s+", " ", (name or "").strip().lower())[:80]


def domain_for(name: str) -> str | None:
    key = name_key(name)
    for needle, domain in _DOMAINS:
        if needle in key:
            return domain
    return None


def logos_for(db: Session, names: list[str]) -> dict[str, str]:
    keys = {name_key(n) for n in names if n}
    if not keys:
        return {}
    rows = (
        db.query(models.DividendCompanyLogo)
        .filter(models.DividendCompanyLogo.name_key.in_(keys))
        .all()
    )
    return {r.name_key: r.logo_path for r in rows if r.logo_path}


def sync_logos(db: Session, names: list[str]) -> int:
    """Download missing logos. Skips names fetched in the last day."""
    saved = 0
    now = datetime.utcnow()
    fresh = now - timedelta(days=1)
    _DIR.mkdir(parents=True, exist_ok=True)
    for name in names:
        key = name_key(name)
        if not key:
            continue
        row = (
            db.query(models.DividendCompanyLogo)
            .filter(models.DividendCompanyLogo.name_key == key)
            .first()
        )
        if row and row.logo_path:
            continue
        bundled = _bundled(name)
        if bundled:
            if row is None:
                row = models.DividendCompanyLogo(name_key=key)
                db.add(row)
            row.logo_path = bundled
            row.domain = domain_for(name)
            row.fetched_at = now
            saved += 1
            db.commit()
            continue
        if row and row.fetched_at and row.fetched_at > fresh:
            continue
        if row is None:
            row = models.DividendCompanyLogo(name_key=key)
            db.add(row)
        row.fetched_at = now
        domain = domain_for(name)
        row.domain = domain
        if domain:
            path = _download(domain, key)
            if path:
                row.logo_path = path
                saved += 1
        db.commit()
    return saved


def _download(domain: str, key: str) -> str | None:
    url = f"https://www.google.com/s2/favicons?domain={domain}&sz=128"
    try:
        req = Request(url, headers={"User-Agent": "HealthVault/1.0"})
        with urlopen(req, timeout=8) as resp:
            data = resp.read()
    except Exception:
        return None
    if len(data) < 80:
        return None
    safe = re.sub(r"[^a-z0-9]+", "-", key).strip("-")[:40] or "logo"
    filename = f"{safe}.png"
    (_DIR / filename).write_bytes(data)
    return f"/static/company-logos/{filename}"
