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
        {"english": "Garlic", "malayalam": "വെളുത്തുള്ളി", "emoji": "🧄"},
        {"english": "Ginger", "malayalam": "ഇഞ്ചി", "emoji": "🫚"},
        {"english": "Green Chilli", "malayalam": "പച്ചമുളക്", "emoji": "🌶️"},
        {"english": "Carrot", "malayalam": "കാരറ്റ്", "emoji": "🥕"},
        {"english": "Cabbage", "malayalam": "കാബേജ്", "emoji": "🥬"},
        {"english": "Cauliflower", "malayalam": "കോളിഫ്‌ളവർ", "emoji": "🥦"},
        {"english": "Spinach", "malayalam": "ചീര", "emoji": "🥬"},
        {"english": "Beans", "malayalam": "ബീൻസ്", "emoji": "🫛"},
        {"english": "Lady's Finger", "malayalam": "വെണ്ട", "emoji": "🥒"},
        {"english": "Brinjal", "malayalam": "വാഴുതന", "emoji": "🍆"},
        {"english": "Cucumber", "malayalam": "വെള്ളരി", "emoji": "🥒"},
        {"english": "Bitter Gourd", "malayalam": "പാവയ്ക്ക", "emoji": "🥒"},
        {"english": "Drumstick", "malayalam": "മുരിങ്ങക്കായി", "emoji": "🥒"},
        {"english": "Tapioca", "malayalam": "കപ്പ", "emoji": "🥔"},
        {"english": "Yam", "malayalam": "ചേന", "emoji": "🥔"},
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
        {"english": "Sardine", "malayalam": "മത്തി", "emoji": "🐟"},
        {"english": "Mackerel", "malayalam": "അയല", "emoji": "🐟"},
        {"english": "Pearl Spot", "malayalam": "കരിമീൻ", "emoji": "🐟"},
        {"english": "Prawns", "malayalam": "ചെമ്മീൻ", "emoji": "🦐"},
        {"english": "Squid", "malayalam": "കൂന്തൾ", "emoji": "🦑"},
        {"english": "Pomfret", "malayalam": "ആവോലി", "emoji": "🐟"},
    ],
    "meat": [
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

# Transliteration keys → catalog item (from the original expense tracker).
SEED_KEYS = {
    "mutta": "Egg", "paal": "Milk", "pal": "Milk", "thair": "Curd", "ney": "Ghee",
    "venna": "Butter", "ari": "Rice", "gothambu": "Wheat", "aripodi": "Rice Flour",
    "ulli": "Onion", "savola": "Shallots", "veluthulli": "Garlic", "inji": "Ginger",
    "thakali": "Tomato", "urulakizhangu": "Potato", "kizhangu": "Potato",
    "vendakka": "Lady's Finger", "venda": "Lady's Finger", "vazhuthananga": "Brinjal",
    "payar": "Beans", "mulaku": "Green Chilli", "pachamulaku": "Green Chilli",
    "cheera": "Spinach", "kappa": "Tapioca", "chembu": "Taro", "chena": "Yam",
    "thenga": "Coconut", "pazham": "Banana", "vazha": "Banana", "manga": "Mango",
    "chakka": "Jackfruit", "ilaneer": "Tender Coconut", "kozhi": "Chicken",
    "meen": "Fish", "chemmeen": "Prawns", "aadu": "Mutton", "panni": "Pork",
    "irachi": "Meat", "manjal": "Turmeric", "mulakupodi": "Chilli Powder",
    "mallipodi": "Coriander Powder", "kurumulaku": "Pepper", "jeerakam": "Cumin",
    "kaduku": "Mustard Seeds", "grambu": "Cloves", "elakka": "Cardamom",
    "karuva": "Cinnamon", "kariveppila": "Curry Leaves", "puli": "Tamarind",
    "uluva": "Fenugreek", "uppu": "Salt", "panjasara": "Sugar", "chakkara": "Jaggery",
    "sharkara": "Jaggery", "sharkkara": "Jaggery", "sarkara": "Jaggery",
    "then": "Honey", "velichenna": "Coconut Oil", "enna": "Oil", "pappadam": "Pappadam",
    "parippu": "Toor Dal", "kadala": "Chickpeas", "uzhunnu": "Urad Dal",
    "chaya": "Tea Powder", "kappi": "Coffee Powder",
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


def grouped_quick_add() -> list[dict]:
    groups = []
    for key, items in QUICK_ADD.items():
        groups.append({
            "key": key,
            "label": GROUP_LABELS.get(key, key.title()),
            "items": [{**it, "category": key} for it in items],
        })
    return groups


def seed_dictionary(db: Session) -> None:
    if db.query(models.ShopDictItem).first():
        return
    catalog = {row["english"].lower(): row for row in _all_catalog()}
    seen = set()
    for key, english in SEED_KEYS.items():
        row = catalog.get(english.lower())
        if not row:
            continue
        k = key.lower().strip()
        if k in seen:
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
    for row in _all_catalog():
        k = row["english"].lower().strip()
        if k in seen:
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
    db.commit()


def recognize(db: Session, name: str) -> dict:
    seed_dictionary(db)
    raw = (name or "").strip()
    if not raw:
        return {"english": "", "malayalam": None, "emoji": "🛒", "category": None}
    q = raw.lower()
    hit = db.query(models.ShopDictItem).filter(models.ShopDictItem.key == q).first()
    if hit:
        return _dict_out(hit)
    rows = db.query(models.ShopDictItem).all()
    for row in rows:
        if (row.english or "").lower() == q or (row.malayalam or "") == raw:
            return _dict_out(row)
    for row in rows:
        en = (row.english or "").lower()
        ml = row.malayalam or ""
        if q in en or q in (row.key or "") or (ml and raw in ml):
            return _dict_out(row)
    return {"english": raw.title(), "malayalam": None, "emoji": "🛒", "category": None}


def _dict_out(row: models.ShopDictItem) -> dict:
    return {
        "english": row.english,
        "malayalam": row.malayalam,
        "emoji": row.emoji or "🛒",
        "category": row.category,
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
