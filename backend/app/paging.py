"""Tiny page math for admin list UIs."""
from __future__ import annotations


def paginate(*, page: int | str | None, per_page: int = 25, total: int = 0, max_per_page: int = 100) -> dict:
    """Return page/offset helpers. `page` is 1-based."""
    try:
        page_n = int(page or 1)
    except (TypeError, ValueError):
        page_n = 1
    size = max(1, min(max_per_page, int(per_page or 25)))
    total_n = max(0, int(total or 0))
    pages = max(1, (total_n + size - 1) // size) if total_n else 1
    page_n = max(1, min(pages, page_n))
    offset = (page_n - 1) * size
    start = 0 if total_n == 0 else offset + 1
    end = min(total_n, offset + size)
    return {
        "page": page_n,
        "pages": pages,
        "per_page": size,
        "total": total_n,
        "offset": offset,
        "has_prev": page_n > 1,
        "has_next": page_n < pages,
        "start": start,
        "end": end,
    }
