"""Household brain — durable memories Ask AI learns without retraining the model.

Facts stay in this vault (encrypted). They are injected into the snapshot on
later questions. Nothing here is sent to a fine-tune job.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

from sqlalchemy.orm import Session

from app import crypto, models
from app.deps import vault_id

MAX_MEMORIES = 80
MAX_CONTENT = 240
KINDS = ("fact", "preference", "alias", "habit")

_VAULT_MEMORY_RE = re.compile(
    r"```vault-memory\s*(\{.*?\})\s*```",
    re.DOTALL | re.IGNORECASE,
)
_SECRET_RE = re.compile(
    r"\b(password|passwd|otp|pin\b|aadhaar|aadhar|pan\s*card|cvv|api[_\s-]?key|"
    r"secret\s*key|account\s*number)\b",
    re.I,
)
_DIGIT_RUN = re.compile(r"\d{8,}")
_QUESTIONISH = re.compile(
    r"\b(how much|did i|do we have|what|when|which|list|show|summar)\b|\?",
    re.I,
)
_TEACH_HEAD = re.compile(
    r"^\s*(?:please\s+)?(?:"
    r"remember(?:\s+that)?|"
    r"don't forget|do not forget|"
    r"from now on|"
    r"always|"
    r"never|"
    r"i prefer|we prefer|"
    r"ormma\s+vekk?u?"
    r")\s*[:\-]?\s*(.+)$",
    re.I | re.DOTALL,
)
_ALIAS_RE = re.compile(
    r"^\s*(?:remember(?:\s+that)?\s+)?"
    r"['\"]?(.{1,40}?)['\"]?\s+(?:means|is called|aka|=)\s+['\"]?(.{1,80}?)['\"]?\s*\.?\s*$",
    re.I,
)
_FORGET_HEAD = re.compile(
    r"^\s*(?:please\s+)?(?:forget(?:\s+that)?|stop remembering|unlearn)\s+(.+)$",
    re.I | re.DOTALL,
)
_INLINE_TEACH = re.compile(
    r"(?:^|[.!?]\s+)(?:please\s+)?(?:remember(?:\s+that)?|don't forget|do not forget)\s+(.+?)(?:[.!?]|$)",
    re.I,
)


def _uid(user: models.User) -> str:
    return vault_id(user)


def _fold(s: str) -> str:
    t = re.sub(r"\s+", " ", (s or "").strip().casefold())
    t = re.sub(r"[^\w\u0d00-\u0d7f]+", "", t)
    return t[:48]


def _clip(s: str, n: int = MAX_CONTENT) -> str:
    text = re.sub(r"\s+", " ", (s or "").strip())
    if len(text) <= n:
        return text
    return text[: n - 1].rstrip() + "…"


def _looks_secret(text: str) -> bool:
    if _SECRET_RE.search(text or ""):
        return True
    return bool(_DIGIT_RUN.search(text or ""))


def _kind_for(text: str, explicit: str | None = None) -> str:
    k = (explicit or "").strip().lower()
    if k in KINDS:
        return k
    low = (text or "").casefold()
    if low.startswith("always") or low.startswith("never") or "prefer" in low:
        return "preference"
    if " means " in f" {low} " or " aka " in f" {low} ":
        return "alias"
    if low.startswith("when logging") or "account" in low and "categor" in low:
        return "habit"
    return "fact"


def _slug(kind: str, content: str, explicit: str | None = None) -> str:
    given = _fold(explicit or "")
    if given:
        return f"{kind}:{given}"[:80]
    folded = _fold(content) or "note"
    return f"{kind}:{folded}"[:80]


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


def memory_out(row: models.AiBrainMemory) -> dict:
    return {
        "id": row.id,
        "kind": row.kind,
        "slug": row.slug,
        "content": crypto.decrypt_text(row.content_enc) or "",
        "source": row.source,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at or row.created_at),
    }


def list_memories(db: Session, user: models.User, *, include_inactive: bool = False) -> list[dict]:
    q = db.query(models.AiBrainMemory).filter(models.AiBrainMemory.user_id == _uid(user))
    if not include_inactive:
        q = q.filter(models.AiBrainMemory.active.is_(True))
    rows = q.order_by(models.AiBrainMemory.updated_at.desc()).limit(MAX_MEMORIES).all()
    return [memory_out(r) for r in rows]


def get_memory(db: Session, user: models.User, memory_id: str) -> models.AiBrainMemory | None:
    return (
        db.query(models.AiBrainMemory)
        .filter(
            models.AiBrainMemory.id == memory_id,
            models.AiBrainMemory.user_id == _uid(user),
        )
        .first()
    )


def _evict_if_needed(db: Session, user_id: str) -> None:
    rows = (
        db.query(models.AiBrainMemory)
        .filter(models.AiBrainMemory.user_id == user_id, models.AiBrainMemory.active.is_(True))
        .order_by(models.AiBrainMemory.updated_at.asc())
        .all()
    )
    overflow = len(rows) - MAX_MEMORIES
    if overflow <= 0:
        return
    for row in rows[:overflow]:
        if row.source == "manual":
            continue
        db.delete(row)


def upsert_memory(
    db: Session,
    user: models.User,
    *,
    content: str,
    kind: str | None = None,
    slug: str | None = None,
    source: str = "chat",
) -> dict | None:
    text = _clip(content)
    if len(text) < 8:
        return None
    if _looks_secret(text):
        return None
    kind_s = _kind_for(text, kind)
    slug_s = _slug(kind_s, text, slug)
    uid = _uid(user)
    row = (
        db.query(models.AiBrainMemory)
        .filter(models.AiBrainMemory.user_id == uid, models.AiBrainMemory.slug == slug_s)
        .first()
    )
    now = datetime.utcnow()
    if row:
        row.content_enc = crypto.encrypt_text(text)
        row.kind = kind_s
        row.source = source or row.source
        row.active = True
        row.updated_at = now
    else:
        row = models.AiBrainMemory(
            user_id=uid, kind=kind_s, slug=slug_s,
            content_enc=crypto.encrypt_text(text),
            source=source or "chat", active=True,
            created_at=now, updated_at=now,
        )
        db.add(row)
        db.flush()
        _evict_if_needed(db, uid)
    return memory_out(row)


def forget_memory(db: Session, user: models.User, memory_id: str) -> bool:
    row = get_memory(db, user, memory_id)
    if not row:
        return False
    db.delete(row)
    return True


def forget_matching(db: Session, user: models.User, phrase: str) -> list[dict]:
    needle = _fold(phrase)
    if len(needle) < 4:
        return []
    removed: list[dict] = []
    rows = (
        db.query(models.AiBrainMemory)
        .filter(models.AiBrainMemory.user_id == _uid(user), models.AiBrainMemory.active.is_(True))
        .all()
    )
    for row in rows:
        content = crypto.decrypt_text(row.content_enc) or ""
        if needle in _fold(content) or needle in _fold(row.slug):
            removed.append(memory_out(row))
            db.delete(row)
    return removed


def format_brain_context(db: Session, user: models.User) -> str:
    rows = list_memories(db, user)
    if not rows:
        return ""
    lines = [
        "## HOUSEHOLD BRAIN (self-learned — durable preferences, not live totals)",
        "Use these when guessing brands, aliases, default accounts, or household habits.",
        "Money Manager / Shopping List snapshot numbers still win for amounts and dates.",
    ]
    for row in rows[:40]:
        lines.append(f"- [{row['kind']}] {row['content']}")
    lines.append("")
    return "\n".join(lines)


def extract_vault_memory(text: str) -> tuple[str, list[dict]]:
    """Strip ```vault-memory``` fences and return (display, memory dicts)."""
    raw = text or ""
    found: list[dict] = []
    for m in _VAULT_MEMORY_RE.finditer(raw):
        try:
            data = json.loads(m.group(1))
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        items = data.get("memories")
        if isinstance(items, list):
            found.extend(x for x in items if isinstance(x, dict))
        elif data.get("content") or data.get("text"):
            found.append(data)
    cleaned = _VAULT_MEMORY_RE.sub("", raw).strip()
    return cleaned, found


def _candidate_teaches(message: str) -> list[tuple[str, str | None]]:
    text = (message or "").strip()
    if not text:
        return []
    out: list[tuple[str, str | None]] = []
    alias = _ALIAS_RE.match(text)
    if alias:
        left, right = alias.group(1).strip(), alias.group(2).strip()
        if left and right:
            out.append((f"{left} means {right}", "alias"))
            return out
    head = _TEACH_HEAD.match(text)
    if head:
        body = head.group(1).strip().rstrip(".")
        if body and not _QUESTIONISH.search(body):
            out.append((body, None))
            return out
    for m in _INLINE_TEACH.finditer(" " + text):
        body = m.group(1).strip().rstrip(".")
        if body and not _QUESTIONISH.search(body):
            out.append((body, None))
    return out


def remember_from_user_text(db: Session, user: models.User, message: str) -> list[dict]:
    saved: list[dict] = []
    seen: set[str] = set()
    for content, kind in _candidate_teaches(message):
        row = upsert_memory(db, user, content=content, kind=kind, source="chat")
        if row and row["id"] not in seen:
            seen.add(row["id"])
            saved.append(row)
    return saved


def remember_from_model(db: Session, user: models.User, items: list[dict]) -> list[dict]:
    saved: list[dict] = []
    seen: set[str] = set()
    for item in items:
        content = str(item.get("content") or item.get("text") or "").strip()
        kind = item.get("kind")
        slug = item.get("slug") or item.get("key")
        row = upsert_memory(
            db, user, content=content, kind=kind, slug=str(slug) if slug else None, source="chat",
        )
        if row and row["id"] not in seen:
            seen.add(row["id"])
            saved.append(row)
    return saved


def learn_finance_habit(db: Session, user: models.User, *, payee: str, account: str, category: str | None) -> dict | None:
    payee_s = _clip(payee, 80)
    if not payee_s or not account:
        return None
    bits = [f"When logging {payee_s}, use account {account}"]
    if category:
        bits.append(f"and category {category}")
    content = " ".join(bits)
    return upsert_memory(
        db, user,
        content=content,
        kind="habit",
        slug=_fold(payee_s),
        source="action",
    )


def classify_brain_command(message: str) -> str | None:
    """'teach', 'forget', or None when the whole message is a brain command."""
    text = (message or "").strip()
    if not text:
        return None
    if _QUESTIONISH.search(text):
        return None
    if _FORGET_HEAD.match(text):
        return "forget"
    if _TEACH_HEAD.match(text) or _ALIAS_RE.match(text):
        return "teach"
    return None


def apply_brain_command(db: Session, user: models.User, message: str) -> tuple[str, list[dict], list[dict]] | None:
    """Handle a remember/forget-only turn. Returns (reply, learned, forgotten) or None."""
    kind = classify_brain_command(message)
    if kind == "forget":
        m = _FORGET_HEAD.match((message or "").strip())
        phrase = (m.group(1) if m else "").strip()
        removed = forget_matching(db, user, phrase)
        if not removed:
            return ("I didn't find that in the household brain.", [], [])
        labels = ", ".join(r["content"] for r in removed[:4])
        return (f"Forgotten from the household brain: {labels}.", [], removed)
    if kind == "teach":
        if _looks_secret(message):
            return ("I won't store passwords, OTPs, or ID numbers in the brain.", [], [])
        saved = remember_from_user_text(db, user, message)
        if not saved:
            return ("I couldn't save that — try a short household fact, like “remember we prefer coconut oil”.", [], [])
        bits = "; ".join(r["content"] for r in saved[:3])
        return (f"Saved to the household brain: {bits}. I'll use it on later questions.", saved, [])
    return None
