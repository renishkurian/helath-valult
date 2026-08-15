"""Kerala grocery catalog, Malayalam dictionary, and item recognition."""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app import models

# First item in each group is the section label; the rest are quick-add rows.
QUICK_ADD: dict[str, list[dict]] = {
    "vegetables": [
        {"english": "Potato", "malayalam": "ഉരുളക്കിഴങ്ങ്", "emoji": "🥔"},
        {"english": "Tomato", "malayalam": "തക്കാളി", "emoji": "🍅"},
        {"english": "Onion", "malayalam": "ഉള്ളി", "emoji": "🧅"},
        {"english": "Big Onion", "malayalam": "വലിയ ഉള്ളി", "emoji": "🧅"},
        {"english": "Garlic", "malayalam": "വെളുത്തുള്ളി", "emoji": "🧄"},
        {"english": "Ginger", "malayalam": "ഇഞ്ചി", "emoji": "🫚"},
        {"english": "Green Chilli", "malayalam": "പച്ചമുളക്", "emoji": "🌶️"},
        {"english": "Carrot", "malayalam": "കാരറ്റ്", "emoji": "🥕"},
        {"english": "Cabbage", "malayalam": "കാബേജ്", "emoji": "🥬"},
        {"english": "Cauliflower", "malayalam": "കോളിഫ്‌ളവർ", "emoji": "🥦"},
        {"english": "Spinach", "malayalam": "ചീര", "emoji": "🥬"},
        {"english": "Beans", "malayalam": "ബീൻസ്", "emoji": "🫛"},
        {"english": "Lady's Finger", "malayalam": "വെണ്ട", "emoji": "🥒"},
        {"english": "Brinjal", "malayalam": "വാഴുതനങ്ങ", "emoji": "🍆"},
        {"english": "Ash Gourd", "malayalam": "കുമ്പളങ്ങ", "emoji": "🍈"},
        {"english": "Banana Flower", "malayalam": "വാഴപ്പൂ", "emoji": "🍌"},
        {"english": "Cucumber", "malayalam": "വെള്ളരി", "emoji": "🥒"},
        {"english": "Bitter Gourd", "malayalam": "പാവയ്ക്ക", "emoji": "🥒"},
        {"english": "Drumstick", "malayalam": "മുരിങ്ങക്കായി", "emoji": "🥒"},
        {"english": "Tapioca", "malayalam": "കപ്പ", "emoji": "🥔"},
        {"english": "Yam", "malayalam": "ചേന", "emoji": "🥔"},
        {"english": "Taro", "malayalam": "ചേമ്പ്", "emoji": "🥔"},
        {"english": "Raw Banana", "malayalam": "വാഴക", "emoji": "🍌"},
        {"english": "Raw Jackfruit", "malayalam": "ചക്ക", "emoji": "🍈"},
    ],
    "fruits": [
        {"english": "Coconut", "malayalam": "തേങ്ങ", "emoji": "🥥"},
        {"english": "Banana", "malayalam": "വാഴപ്പഴം", "emoji": "🍌"},
        {"english": "Apple", "malayalam": "ആപ്പിൾ", "emoji": "🍎"},
        {"english": "Orange", "malayalam": "ഓറഞ്ച്", "emoji": "🍊"},
        {"english": "Grapes", "malayalam": "മുന്തിരി", "emoji": "🍇"},
        {"english": "Mango", "malayalam": "മാമ്പഴം", "emoji": "🥭"},
        {"english": "Pineapple", "malayalam": "അനന്നാസ്", "emoji": "🍍"},
        {"english": "Papaya", "malayalam": "കപ്പലങ്ങ", "emoji": "🍈"},
        {"english": "Watermelon", "malayalam": "തണ്ണിമത്തൻ", "emoji": "🍉"},
        {"english": "Tender Coconut", "malayalam": "ഇളനീർ", "emoji": "🥥"},
        {"english": "Jackfruit", "malayalam": "ചക്ക", "emoji": "🍈"},
        {"english": "Guava", "malayalam": "പേരയ്ക്ക", "emoji": "🍐"},
        {"english": "Pomegranate", "malayalam": "മാതളനാരങ്ങ", "emoji": "🍎"},
    ],
    "spices": [
        {"english": "Turmeric", "malayalam": "മഞ്ഞൾ", "emoji": "🟡"},
        {"english": "Chilli Powder", "malayalam": "മുളകുപൊടി", "emoji": "🌶️"},
        {"english": "Coriander Powder", "malayalam": "മല്ലിപ്പൊടി", "emoji": "🌿"},
        {"english": "Pepper", "malayalam": "കുരുമുളക്", "emoji": "⚫"},
        {"english": "Cumin", "malayalam": "ജീരകം", "emoji": "🟤"},
        {"english": "Mustard Seeds", "malayalam": "കടുക്", "emoji": "🟡"},
        {"english": "Cloves", "malayalam": "ഗ്രാമ്പു", "emoji": "🟤"},
        {"english": "Cardamom", "malayalam": "ഏലം", "emoji": "🟢"},
        {"english": "Cinnamon", "malayalam": "കരുവാപ്പട്ട", "emoji": "🟤"},
        {"english": "Curry Leaves", "malayalam": "കറിവേപ്പില", "emoji": "🌿"},
        {"english": "Tamarind", "malayalam": "പുളി", "emoji": "🟤"},
        {"english": "Fenugreek", "malayalam": "ഉലുവ", "emoji": "🟡"},
        {"english": "Shallots", "malayalam": "ചെറുഉള്ളി", "emoji": "🧅"},
        {"english": "Garam Masala", "malayalam": "ഗരം മസാല", "emoji": "🌶️"},
    ],
    "dals": [
        {"english": "Toor Dal", "malayalam": "തുവരപ്പരിപ്പ്", "emoji": "🫘"},
        {"english": "Moong Dal", "malayalam": "പയർപ്പരിപ്പ്", "emoji": "🫘"},
        {"english": "Chana Dal", "malayalam": "കടലപരിപ്പ്", "emoji": "🫘"},
        {"english": "Chickpeas", "malayalam": "കടല", "emoji": "🫘"},
        {"english": "Urad Dal", "malayalam": "ഉഴുന്ന്", "emoji": "🫘"},
        {"english": "Masoor Dal", "malayalam": "മസൂർ", "emoji": "🫘"},
    ],
    "grains": [
        {"english": "Rice", "malayalam": "അരി", "emoji": "🍚"},
        {"english": "Kerala Matta Rice", "malayalam": "മട്ട അരി", "emoji": "🍚"},
        {"english": "Wheat", "malayalam": "ഗോതമ്പ്", "emoji": "🌾"},
        {"english": "Rice Flour", "malayalam": "അരിപ്പൊടി", "emoji": "🥣"},
        {"english": "Wheat Flour (Atta)", "malayalam": "ആട്ടപ്പൊടി", "emoji": "🥣"},
        {"english": "Maida", "malayalam": "മൈദ", "emoji": "🥣"},
        {"english": "Rava", "malayalam": "റവ", "emoji": "🥣"},
        {"english": "Puttu Podi", "malayalam": "പുട്ടുപൊടി", "emoji": "🥣"},
        {"english": "Dosa Batter", "malayalam": "ദോശമാവ്", "emoji": "🥞"},
        {"english": "Oats", "malayalam": "ഓട്സ്", "emoji": "🥣"},
    ],
    "essentials": [
        {"english": "Coconut Oil", "malayalam": "തേങ്ങാവെളിച്ചെണ്ണ", "emoji": "🫒"},
        {"english": "Sunflower Oil", "malayalam": "സൺഫ്ലവർ ഓയിൽ", "emoji": "🌻"},
        {"english": "Sugar", "malayalam": "പഞ്ചസാര", "emoji": "🍬"},
        {"english": "Salt", "malayalam": "ഉപ്പ്", "emoji": "🧂"},
        {"english": "Tea Powder", "malayalam": "ചായപ്പൊടി", "emoji": "🍵"},
        {"english": "Coffee Powder", "malayalam": "കാപ്പിപ്പൊടി", "emoji": "☕"},
        {"english": "Jaggery", "malayalam": "ശർക്കര", "emoji": "🟤"},
        {"english": "Honey", "malayalam": "തേൻ", "emoji": "🍯"},
        {"english": "Pappadam", "malayalam": "പപ്പടം", "emoji": "🥙"},
        {"english": "Vinegar", "malayalam": "വിനാഗിരി", "emoji": "🫙"},
        {"english": "Tomato Ketchup", "malayalam": "ടോമാറ്റോ കച്ചപ്പ്", "emoji": "🍅"},
    ],
    "dairy": [
        {"english": "Milk", "malayalam": "പാൽ", "emoji": "🥛"},
        {"english": "Butter", "malayalam": "വെണ്ണ", "emoji": "🧈"},
        {"english": "Ghee", "malayalam": "നെയ്യ്", "emoji": "🧈"},
        {"english": "Curd", "malayalam": "തൈര്", "emoji": "🥛"},
        {"english": "Coconut Milk", "malayalam": "തേങ്ങാപ്പാൽ", "emoji": "🥥"},
        {"english": "Cheese", "malayalam": "ചീസ്", "emoji": "🧀"},
        {"english": "Paneer", "malayalam": "പനീർ", "emoji": "🧀"},
        {"english": "Egg", "malayalam": "മുട്ട", "emoji": "🥚"},
    ],
    "fish": [
        {"english": "Fish", "malayalam": "മീൻ", "emoji": "🐟"},
        {"english": "Sardine", "malayalam": "മത്തി", "emoji": "🐟"},
        {"english": "Mackerel", "malayalam": "അയല", "emoji": "🐟"},
        {"english": "Pearl Spot", "malayalam": "കരിമീൻ", "emoji": "🐟"},
        {"english": "Prawns", "malayalam": "ചെമ്മീൻ", "emoji": "🦐"},
        {"english": "Squid", "malayalam": "കൂന്തൾ", "emoji": "🦑"},
        {"english": "Pomfret", "malayalam": "ആവോലി", "emoji": "🐟"},
    ],
    "meat": [
        {"english": "Meat", "malayalam": "ഇറച്ചി", "emoji": "🍖"},
        {"english": "Chicken", "malayalam": "കോഴി", "emoji": "🍗"},
        {"english": "Mutton", "malayalam": "ആട്ടിറച്ചി", "emoji": "🍖"},
        {"english": "Beef", "malayalam": "ബീഫ്", "emoji": "🥩"},
        {"english": "Pork", "malayalam": "പന്നിയിറച്ചി", "emoji": "🥓"},
        {"english": "Duck", "malayalam": "താറാവ്", "emoji": "🦆"},
    ],
    "snacks": [
        {"english": "Banana Chips", "malayalam": "വാഴക്ക ചിപ്സ്", "emoji": "🍌"},
        {"english": "Murukku", "malayalam": "മുറുക്ക്", "emoji": "🥨"},
        {"english": "Mixture", "malayalam": "മിക്സ്ചർ", "emoji": "🥜"},
        {"english": "Unniyappam", "malayalam": "ഉണ്ണിയപ്പം", "emoji": "🍩"},
        {"english": "Vada", "malayalam": "വട", "emoji": "🍩"},
    ],
    "household": [
        {"english": "Dishwash Liquid", "malayalam": "പാത്രം കഴുകുന്ന ലിക്വിഡ്", "emoji": "🧴"},
        {"english": "Washing Powder", "malayalam": "വാഷിംഗ് പൗഡർ", "emoji": "🧺"},
        {"english": "Toilet Cleaner", "malayalam": "ടോയ്ലറ്റ് ക്ലീനർ", "emoji": "🚽"},
        {"english": "Garbage Bag", "malayalam": "മാലിന്യപ്പൊതി", "emoji": "🗑️"},
        {"english": "Shampoo", "malayalam": "ഷാമ്പൂ", "emoji": "🧴"},
        {"english": "Bath Soap", "malayalam": "സോപ്പ്", "emoji": "🧼"},
        {"english": "Toothpaste", "malayalam": "പല്ലുതേപ്പ്", "emoji": "🪥"},
    ],
}

GROUP_LABELS = {
    "vegetables": "Vegetables · പച്ചക്കറികൾ",
    "fruits": "Fruits · പഴങ്ങൾ",
    "spices": "Spices · മസാലകൾ",
    "dals": "Dals · പരിപ്പ്",
    "grains": "Grains · ധാന്യങ്ങൾ",
    "essentials": "Essentials · അടിസ്ഥാനം",
    "dairy": "Dairy · പാൽ",
    "fish": "Fish · മീൻ",
    "meat": "Meat · ഇറച്ചി",
    "snacks": "Snacks · പലഹാരം",
    "household": "Household · വീട്",
}

GROUP_ICONS = {
    "vegetables": "🥬", "fruits": "🍎", "spices": "🌶️", "dals": "🫘",
    "grains": "🍚", "essentials": "🧂", "dairy": "🥛", "fish": "🐟",
    "meat": "🍗", "snacks": "🥨", "household": "🧴",
}

FREQUENT = {
    "onion", "big onion", "tomato", "potato", "garlic", "ginger",
    "rice", "milk", "egg", "shallots", "green chilli",
}

# Transliteration keys → catalog item (from the original expense tracker).
SEED_KEYS = {
    "mutta": "Egg", "paal": "Milk", "pal": "Milk", "thair": "Curd", "thayir": "Curd",
    "ney": "Ghee", "neyyi": "Ghee",
    "venna": "Butter", "ari": "Rice", "gothambu": "Wheat", "aripodi": "Rice Flour",
    "ulli": "Onion", "ullii": "Onion", "savola": "Shallots", "sabola": "Shallots",
    "cheruulli": "Shallots",
    "valiyaulli": "Big Onion", "bigonion": "Big Onion",
    "veluthulli": "Garlic", "veluthulli": "Garlic", "inji": "Ginger",
    "thakali": "Tomato", "thakkali": "Tomato", "urulakizhangu": "Potato",
    "kizhangu": "Potato", "urula": "Potato",
    "vendakka": "Lady's Finger", "venda": "Lady's Finger", "vendaka": "Lady's Finger",
    "vazhuthananga": "Brinjal", "vazhuthanga": "Brinjal", "vazhuthananga": "Brinjal",
    "vazhuth": "Brinjal", "vaazhuthananga": "Brinjal", "baingan": "Brinjal",
    "eggplant": "Brinjal", "kathirikka": "Brinjal",
    "kumbalam": "Ash Gourd", "kumbalanga": "Ash Gourd", "ashgourd": "Ash Gourd",
    "vazhapoo": "Banana Flower", "vazhappoo": "Banana Flower", "bananaflower": "Banana Flower",
    "payar": "Beans", "mulaku": "Green Chilli", "pachamulaku": "Green Chilli",
    "cheera": "Spinach", "kappa": "Tapioca", "chembu": "Taro", "chena": "Yam",
    "thenga": "Coconut", "pazham": "Banana", "vazha": "Banana", "manga": "Mango",
    "chakka": "Jackfruit", "ilaneer": "Tender Coconut", "ilaneer": "Tender Coconut",
    "kozhi": "Chicken",
    "meen": "Fish", "chemmeen": "Prawns", "aadu": "Mutton", "panni": "Pork",
    "irachi": "Meat", "manjal": "Turmeric", "mulakupodi": "Chilli Powder",
    "mallipodi": "Coriander Powder", "kurumulaku": "Pepper", "jeerakam": "Cumin",
    "kaduku": "Mustard Seeds", "grambu": "Cloves", "elakka": "Cardamom",
    "karuva": "Cinnamon", "kariveppila": "Curry Leaves", "puli": "Tamarind",
    "uluva": "Fenugreek", "uppu": "Salt", "panjasara": "Sugar", "chakkara": "Jaggery",
    "sharkara": "Jaggery", "sharkkara": "Jaggery", "sarkara": "Jaggery",
    "then": "Honey", "velichenna": "Coconut Oil", "enna": "Coconut Oil", "pappadam": "Pappadam",
    "parippu": "Toor Dal", "kadala": "Chickpeas", "uzhunnu": "Urad Dal",
    "chaya": "Tea Powder", "chaaya": "Tea Powder", "kappi": "Coffee Powder",
    "mathi": "Sardine", "ayala": "Mackerel", "karimeen": "Pearl Spot",
}

PARSER_TO_FINANCE = {
    "grocery": ("Groceries", "expense"),
    "fuel": ("Fuel", "expense"),
    "travel": ("Travel", "expense"),
    "food": ("Food & dining", "expense"),
    "utilities": ("Bills & utilities", "expense"),
    "investment": ("Other", "expense"),
    "dividend": ("Interest", "income"),
    "salary": ("Salary", "income"),
    "transfer": ("UPI / transfers", "expense"),
    "upi": ("UPI / transfers", "expense"),
    "cash_withdrawal": ("ATM / cash", "expense"),
    "shopping": ("Shopping", "expense"),
    "entertainment": ("Entertainment", "expense"),
    "emi": ("EMI / loans", "expense"),
    "other": ("Other", "expense"),
}


def _all_catalog() -> list[dict]:
    rows = []
    for cat, items in QUICK_ADD.items():
        for item in items:
            rows.append({**item, "category": cat})
    return rows


def _fold(s: str) -> str:
    return "".join(ch for ch in (s or "").lower() if ch.isalnum())


def _bare_name(name: str) -> str:
    raw = (name or "").strip()
    if "(" in raw and raw.endswith(")"):
        raw = raw[: raw.rfind("(")].strip()
    return raw


def _aliases_for() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for key, english in SEED_KEYS.items():
        out.setdefault(english.lower(), []).append(_fold(key) or key.lower())
    return out


def _entry_keys(row: dict) -> list[str]:
    keys = [_fold(row.get("english") or ""), _fold(row.get("malayalam") or "")]
    for alias in _aliases_for().get((row.get("english") or "").lower(), []):
        keys.append(alias)
    return [k for k in dict.fromkeys(keys) if k]


def grouped_quick_add() -> list[dict]:
    groups = []
    for key, items in QUICK_ADD.items():
        groups.append({
            "key": key,
            "label": GROUP_LABELS.get(key, key.title()),
            "icon": GROUP_ICONS.get(key, "🛒"),
            # Use "entries" — Jinja treats dict.items as dict.items(), which 500s the list page.
            "entries": [
                {
                    **it,
                    "category": key,
                    "aliases": _entry_keys({**it, "category": key}),
                    "star": (it.get("english") or "").lower() in FREQUENT,
                }
                for it in items
            ],
        })
    return groups


def catalog_payload() -> dict:
    return {"groups": grouped_quick_add()}


def format_item_name(english: str, malayalam: Optional[str] = None) -> str:
    en = (english or "").strip()
    ml = (malayalam or "").strip()
    if en and ml:
        return f"{en} ({ml})"
    return en or ml


def seed_dictionary(db: Session) -> None:
    catalog = {row["english"].lower(): row for row in _all_catalog()}
    existing = {row[0] for row in db.query(models.ShopDictItem.key).all()}
    added = False
    seen: set[str] = set()
    for key, english in SEED_KEYS.items():
        row = catalog.get(english.lower())
        if not row:
            continue
        k = key.lower().strip()
        if not k or k in seen:
            continue
        seen.add(k)
        if k in existing:
            continue
        db.add(models.ShopDictItem(
            key=k,
            english=row["english"],
            malayalam=row.get("malayalam"),
            emoji=row.get("emoji") or "🛒",
            source="seed",
            category=row.get("category"),
        ))
        added = True
    for row in _all_catalog():
        k = (row["english"] or "").lower().strip()
        if not k or k in seen or k in existing:
            continue
        seen.add(k)
        db.add(models.ShopDictItem(
            key=k,
            english=row["english"],
            malayalam=row.get("malayalam"),
            emoji=row.get("emoji") or "🛒",
            source="seed",
            category=row.get("category"),
        ))
        added = True
    if added:
        db.commit()


def _candidate_rows(db: Session) -> list[dict]:
    seed_dictionary(db)
    by_en: dict[str, dict] = {}
    for row in _all_catalog():
        by_en[(row["english"] or "").lower()] = {
            "english": row["english"],
            "malayalam": row.get("malayalam"),
            "emoji": row.get("emoji") or "🛒",
            "category": row.get("category"),
            "keys": _entry_keys(row),
        }
    for row in db.query(models.ShopDictItem).all():
        en = (row.english or "").strip()
        if not en:
            continue
        slot = by_en.setdefault(en.lower(), {
            "english": en,
            "malayalam": row.malayalam,
            "emoji": row.emoji or "🛒",
            "category": row.category,
            "keys": [],
        })
        extra = _fold(row.key or "")
        if extra and extra not in slot["keys"]:
            slot["keys"].append(extra)
        if row.malayalam and not slot.get("malayalam"):
            slot["malayalam"] = row.malayalam
    return list(by_en.values())


def _score_row(q: str, q_fold: str, row: dict) -> int:
    en = (row.get("english") or "").lower()
    ml = row.get("malayalam") or ""
    ml_fold = _fold(ml)
    keys = row.get("keys") or []
    best = 0
    if q == en or q == ml or q_fold == ml_fold:
        best = max(best, 100)
    if q_fold and q_fold == _fold(en):
        best = max(best, 100)
    for key in keys:
        if not key:
            continue
        if key == q_fold or key == q:
            best = max(best, 100)
        elif q_fold and key.startswith(q_fold):
            best = max(best, 92 if len(q_fold) >= 4 else 80)
        elif q_fold and q_fold.startswith(key) and len(key) >= 4:
            best = max(best, 78)
        elif q_fold and q_fold in key:
            best = max(best, 70)
    if q_fold and _fold(en).startswith(q_fold):
        best = max(best, 88)
    if q and ml.startswith(q):
        best = max(best, 90)
    if q_fold and ml_fold.startswith(q_fold):
        best = max(best, 90)
    if q_fold and q_fold in _fold(en):
        best = max(best, 65)
    if q and q in ml:
        best = max(best, 75)
    return best


def suggest(db: Session, name: str, limit: int = 12) -> list[dict]:
    raw = (name or "").strip()
    if not raw:
        return []
    q = _bare_name(raw).lower()
    q_fold = _fold(q) or _fold(raw)
    scored: list[tuple[int, dict]] = []
    for row in _candidate_rows(db):
        score = _score_row(q, q_fold, row)
        if score < 65:
            continue
        scored.append((score, row))
    scored.sort(key=lambda pair: (-pair[0], pair[1]["english"]))
    out = []
    seen = set()
    for score, row in scored:
        key = row["english"].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "english": row["english"],
            "malayalam": row.get("malayalam"),
            "emoji": row.get("emoji") or "🛒",
            "category": row.get("category"),
            "matched": True,
            "score": score,
        })
        if len(out) >= max(1, min(int(limit or 12), 20)):
            break
    return out


def recognize(db: Session, name: str) -> dict:
    raw = (name or "").strip()
    if not raw:
        return {"english": "", "malayalam": None, "emoji": "🛒", "category": None, "matched": False}
    hits = suggest(db, raw, limit=1)
    if hits and hits[0].get("score", 0) >= 70:
        hit = hits[0]
        return {
            "english": hit["english"],
            "malayalam": hit.get("malayalam"),
            "emoji": hit.get("emoji") or "🛒",
            "category": hit.get("category"),
            "matched": True,
        }
    return {
        "english": _bare_name(raw).title(),
        "malayalam": None,
        "emoji": "🛒",
        "category": None,
        "matched": False,
    }


def _dict_out(row: models.ShopDictItem) -> dict:
    return {
        "english": row.english,
        "malayalam": row.malayalam,
        "emoji": row.emoji or "🛒",
        "category": row.category,
        "matched": True,
    }


def money(val) -> float:
    if val is None:
        return 0.0
    if isinstance(val, Decimal):
        return float(val)
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0
