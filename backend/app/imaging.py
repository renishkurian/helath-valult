"""Image helpers for Health Vault (rotate + re-encode)."""
from __future__ import annotations

import io

from fastapi import HTTPException

_IMAGE_MIMES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/gif"}


def rotate_image_bytes(raw: bytes, degrees: int, mime: str | None = None) -> tuple[bytes, str]:
    """Rotate clockwise by 90/180/270 and return (bytes, mime)."""
    deg = int(degrees) % 360
    if deg not in (90, 180, 270):
        raise HTTPException(400, "Rotate by 90, 180, or 270 degrees")
    mime_n = (mime or "image/jpeg").split(";")[0].strip().lower()
    if mime_n == "image/jpg":
        mime_n = "image/jpeg"
    if mime_n not in _IMAGE_MIMES:
        raise HTTPException(400, "Only image files can be rotated")
    try:
        from PIL import Image
    except ImportError as exc:
        raise HTTPException(500, "Image processing unavailable") from exc

    try:
        img = Image.open(io.BytesIO(raw))
        # Pillow rotate() is counter-clockwise; negate for clockwise UX.
        img = img.rotate(-deg, expand=True)
        out = io.BytesIO()
        fmt = "JPEG"
        save_kw: dict = {"quality": 92, "optimize": True}
        if mime_n == "image/png":
            fmt = "PNG"
            save_kw = {}
            if img.mode not in ("RGB", "RGBA", "L", "P"):
                img = img.convert("RGBA")
        elif mime_n == "image/webp":
            fmt = "WEBP"
            save_kw = {"quality": 92}
        elif mime_n == "image/gif":
            fmt = "PNG"
            mime_n = "image/png"
            save_kw = {}
        else:
            mime_n = "image/jpeg"
            if img.mode in ("RGBA", "P", "LA"):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")
        img.save(out, format=fmt, **save_kw)
        return out.getvalue(), mime_n
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, "Could not rotate this image") from exc
