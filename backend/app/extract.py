"""OCR / PDF text extraction and simple lab-value parsing.

Tesseract is optional: if it isn't installed, images are skipped and PDFs still
yield any embedded text via pypdf. Plain-text uploads are decoded as UTF-8.
"""
from __future__ import annotations

import io
import re

# Canonical metric name -> (unit, regex that captures the numeric value)
# Order matters: more specific names first.
_LAB_SPECS: list[tuple[str, str, re.Pattern]] = [
    ("hba1c", "%", re.compile(r"\b(?:hba1c|hb\s*a1c|a1c)\b[^\d]{0,20}(\d+(?:\.\d+)?)", re.I)),
    ("glucose", "mg/dL", re.compile(r"\b(?:fasting\s+)?(?:blood\s+)?(?:glucose|fbs|rbs|fbg|sugar)\b[^\d]{0,20}(\d+(?:\.\d+)?)", re.I)),
    ("ldl", "mg/dL", re.compile(r"\bldl\b[^\d]{0,20}(\d+(?:\.\d+)?)", re.I)),
    ("hdl", "mg/dL", re.compile(r"\bhdl\b[^\d]{0,20}(\d+(?:\.\d+)?)", re.I)),
    ("triglycerides", "mg/dL", re.compile(r"\b(?:triglycerides?|tg)\b[^\d]{0,20}(\d+(?:\.\d+)?)", re.I)),
    ("cholesterol", "mg/dL", re.compile(r"\b(?:total\s+)?cholesterol\b[^\d]{0,20}(\d+(?:\.\d+)?)", re.I)),
    ("creatinine", "mg/dL", re.compile(r"\bcreatinine\b[^\d]{0,20}(\d+(?:\.\d+)?)", re.I)),
]

_BP_RE = re.compile(r"\b(?:bp|blood\s*pressure)\b[^\d]{0,16}(\d{2,3})\s*/\s*(\d{2,3})", re.I)


def extract_text(raw: bytes, mime: str | None, filename: str | None) -> str:
    mime = (mime or "").lower()
    name = (filename or "").lower()
    chunks: list[str] = []

    if mime.startswith("text/") or name.endswith((".txt", ".csv")):
        chunks.append(_decode_text(raw))
    elif mime == "application/pdf" or name.endswith(".pdf"):
        chunks.append(_pdf_text(raw))
    elif mime.startswith("image/") or name.endswith((".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp")):
        chunks.append(_ocr_image(raw))
    else:
        # Last-ditch: if it looks like UTF-8 text, keep it (helps tests and notes).
        decoded = _decode_text(raw)
        if decoded and (decoded.isprintable() or "\n" in decoded):
            chunks.append(decoded)

    return "\n".join(c.strip() for c in chunks if c and c.strip())


def parse_lab_readings(text: str) -> list[dict]:
    """Return [{metric, value, unit}, ...] from extracted report text."""
    if not text:
        return []
    found: dict[str, dict] = {}
    for metric, unit, pattern in _LAB_SPECS:
        m = pattern.search(text)
        if m and metric not in found:
            found[metric] = {"metric": metric, "value": m.group(1), "unit": unit}
    bp = _BP_RE.search(text)
    if bp:
        found["bp_sys"] = {"metric": "bp_sys", "value": bp.group(1), "unit": "mmHg"}
        found["bp_dia"] = {"metric": "bp_dia", "value": bp.group(2), "unit": "mmHg"}
    return list(found.values())


def _decode_text(raw: bytes) -> str:
    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return ""


def _pdf_text(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(raw))
        parts = [(page.extract_text() or "") for page in reader.pages]
        text = "\n".join(parts).strip()
        if text:
            return text
    except Exception:
        pass
    # Scanned PDFs often have no text layer — OCR first page if possible.
    try:
        from pypdfium2 import PdfDocument
        doc = PdfDocument(raw)
        if len(doc) == 0:
            return ""
        page = doc[0]
        bitmap = page.render(scale=2).to_pil()
        buf = io.BytesIO()
        bitmap.save(buf, format="PNG")
        return _ocr_image(buf.getvalue())
    except Exception:
        return ""


def _ocr_image(raw: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image
        from app.config import settings
        img = Image.open(io.BytesIO(raw))
        if img.mode not in ("L", "RGB"):
            img = img.convert("RGB")
        langs = settings.OCR_LANGS or "eng"
        try:
            return pytesseract.image_to_string(img, lang=langs) or ""
        except Exception:
            return pytesseract.image_to_string(img) or ""
    except Exception:
        return ""


def file_sha256(raw: bytes) -> str:
    import hashlib
    return hashlib.sha256(raw).hexdigest()


def extract_file_created_at(
    raw: bytes,
    mime: str | None = None,
    filename: str | None = None,
    *,
    client_mtime_ms: int | None = None,
) -> datetime | None:
    """Best-effort original created/modified time from file bytes or browser mtime.

    Prefer EXIF / PDF metadata; fall back to the client's File.lastModified (ms).
    """
    from datetime import datetime

    mime = (mime or "").lower()
    name = (filename or "").lower()
    found: datetime | None = None

    if mime.startswith("image/") or name.endswith((".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".heic")):
        found = _exif_created_at(raw)
    elif mime == "application/pdf" or name.endswith(".pdf"):
        found = _pdf_created_at(raw)

    if found is None and client_mtime_ms:
        try:
            ms = int(client_mtime_ms)
            if ms > 0:
                # Ignore absurd futures / epoch noise
                ts = ms / 1000.0
                if 946684800 <= ts <= datetime.utcnow().timestamp() + 86400 * 2:
                    found = datetime.utcfromtimestamp(ts)
        except (TypeError, ValueError, OSError, OverflowError):
            found = None
    return found


def _parse_exif_dt(value: str | bytes | None) -> datetime | None:
    from datetime import datetime
    if value is None:
        return None
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8", errors="ignore")
        except Exception:
            return None
    text = str(value).strip().split("\x00")[0].strip()
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d"):
        try:
            return datetime.strptime(text[:19] if len(text) >= 19 else text, fmt)
        except ValueError:
            continue
    return None


def _exif_created_at(raw: bytes) -> datetime | None:
    try:
        from PIL import Image, ExifTags
        img = Image.open(io.BytesIO(raw))
        exif = img.getexif()
        if not exif:
            return None
        # Prefer DateTimeOriginal (36867), then Digitized, then DateTime
        tag_map = {v: k for k, v in ExifTags.TAGS.items()}
        for name in ("DateTimeOriginal", "DateTimeDigitized", "DateTime"):
            key = tag_map.get(name)
            if key is None:
                continue
            parsed = _parse_exif_dt(exif.get(key))
            if parsed:
                return parsed
        # Nested IFD for some cameras
        try:
            from PIL.ExifTags import IFD
            ifd = exif.get_ifd(IFD.Exif)
            for key in (36867, 36868, 306):
                parsed = _parse_exif_dt(ifd.get(key) if ifd else None)
                if parsed:
                    return parsed
        except Exception:
            pass
    except Exception:
        return None
    return None


def _pdf_created_at(raw: bytes) -> datetime | None:
    from datetime import datetime
    try:
        from pypdf import PdfReader
        meta = PdfReader(io.BytesIO(raw)).metadata
        if not meta:
            return None
        raw_dt = getattr(meta, "creation_date", None)
        if raw_dt is None and hasattr(meta, "get"):
            raw_dt = meta.get("/CreationDate")
        if isinstance(raw_dt, datetime):
            return raw_dt.replace(tzinfo=None) if raw_dt.tzinfo else raw_dt
        if not raw_dt:
            return None
        text = str(raw_dt).strip()
        if text.startswith("D:"):
            text = text[2:]
        digits = re.sub(r"[^\d]", "", text)[:14]
        if len(digits) >= 8:
            y, mo, d = int(digits[0:4]), int(digits[4:6]), int(digits[6:8])
            hh = int(digits[8:10]) if len(digits) >= 10 else 0
            mm = int(digits[10:12]) if len(digits) >= 12 else 0
            ss = int(digits[12:14]) if len(digits) >= 14 else 0
            return datetime(y, mo, d, hh, mm, ss)
    except Exception:
        return None
    return None


def enhance_scan(raw: bytes, mime: str | None = None, *, max_edge: int = 2048, quality: int = 78) -> bytes:
    """Downscale large photos, autocontrast + mild sharpen, JPEG-compress.

    Non-images (e.g. PDF) pass through unchanged. Failed decode returns original bytes.
    """
    mime = (mime or "").lower()
    if mime and not mime.startswith("image/") and "pdf" in mime:
        return raw
    if mime and not mime.startswith("image/") and mime not in ("", "application/octet-stream"):
        # Unknown binary — don't force through Pillow
        if "pdf" in mime or "zip" in mime or "octet" in mime:
            return raw
    try:
        from PIL import Image, ImageFilter, ImageOps
        img = Image.open(io.BytesIO(raw))
        if img.mode not in ("L", "RGB"):
            img = img.convert("RGB")
        w, h = img.size
        longest = max(w, h)
        if max_edge and longest > max_edge:
            scale = max_edge / float(longest)
            img = img.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.Resampling.LANCZOS)
        img = ImageOps.autocontrast(img, cutoff=1)
        img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=120, threshold=3))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=quality, optimize=True)
        compressed = out.getvalue()
        return compressed if compressed else raw
    except Exception:
        return raw


def watermark_bytes(raw: bytes, mime: str | None, label: str = "Shared from Health Vault") -> bytes:
    mime = (mime or "").lower()
    if not mime.startswith("image/"):
        return raw
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.open(io.BytesIO(raw)).convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None
        margin = 12
        draw.text((margin, img.height - 28), label, fill=(255, 255, 255, 160), font=font)
        merged = Image.alpha_composite(img, overlay).convert("RGB")
        out = io.BytesIO()
        merged.save(out, format="JPEG", quality=88)
        return out.getvalue()
    except Exception:
        return raw
