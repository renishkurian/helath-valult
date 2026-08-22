"""Quick Add catalog — personal vs global chips."""
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal
from app.deps import vault_id
from app.grocery import grouped_quick_add, translate_via_dictionary
from app.main import app

client = TestClient(app)


def _headers(prefix="cat"):
    email = f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/auth/register", json={
        "email": email, "password": "password123", "full_name": "Cat User",
    })
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, email


def test_personal_and_global_quick_add():
    h1, email1 = _headers("a")
    h2, email2 = _headers("b")

    r = client.post("/tracker/catalog", headers=h1, json={
        "english": "Vazhuth Special",
        "malayalam": "വാഴുത്",
        "emoji": "🍆",
        "category": "vegetables",
        "scope": "personal",
        "aliases": "vazhuth",
    })
    assert r.status_code == 201, r.text

    r = client.post("/tracker/catalog", headers=h1, json={
        "english": "Shared Snack",
        "emoji": "🥨",
        "category": "snacks",
        "scope": "global",
    })
    assert r.status_code == 201, r.text

    g1 = client.get("/tracker/quick-add", headers=h1).json()["groups"]
    g2 = client.get("/tracker/quick-add", headers=h2).json()["groups"]
    names1 = {e["english"] for g in g1 for e in g["entries"]}
    names2 = {e["english"] for g in g2 for e in g["entries"]}
    assert "Vazhuth Special" in names1
    assert "Vazhuth Special" not in names2
    assert "Shared Snack" in names1
    assert "Shared Snack" in names2

    db = SessionLocal()
    try:
        u1 = db.query(models.User).filter(models.User.email == email1).first()
        u2 = db.query(models.User).filter(models.User.email == email2).first()
        mine = {e["english"] for g in grouped_quick_add(db, vault_id(u1)) for e in g["entries"]}
        theirs = {e["english"] for g in grouped_quick_add(db, vault_id(u2)) for e in g["entries"]}
        assert "Vazhuth Special" in mine and "Vazhuth Special" not in theirs
        assert "Shared Snack" in mine and "Shared Snack" in theirs
    finally:
        db.close()

    listed = client.get("/tracker/catalog", headers=h2).json()
    assert any(i["english"] == "Shared Snack" for i in listed)
    assert not any(i["english"] == "Vazhuth Special" for i in listed)


def test_translate_via_dictionary_manglish():
    db = SessionLocal()
    try:
        hit = translate_via_dictionary(db, "vazhuthananga")
        assert hit is not None
        assert hit["english"] == "Brinjal"
        assert hit["source"] == "dictionary"
        same = translate_via_dictionary(db, "Brinjal")
        assert same is not None
        assert same["source"] == "unchanged"
    finally:
        db.close()


def test_catalog_translate_api_dictionary():
    headers, _ = _headers("tr")
    r = client.post("/tracker/catalog/translate", headers=headers, json={"q": "ulli"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["english"] == "Onion"
    assert body["source"] == "dictionary"
    assert body["manglish"] == "ulli"


def test_catalog_translate_api_ai_fallback():
    headers, _ = _headers("ai")
    fake = {
        "content": '{"english":"Drumstick Leaves","malayalam":"മുരിങ്ങയില","emoji":"🌿","category":"vegetables"}',
        "kind": "openrouter",
        "model": "test-model",
        "prompt_tokens": 10,
        "completion_tokens": 8,
        "total_tokens": 18,
    }
    with patch("app.ai_providers.get_default_bundle", return_value={
        "kind": "openrouter", "api_key": "sk-test", "model": "test-model",
        "base_url": "https://example.com/v1", "name": "Test",
    }), patch("app.ai_chat.complete_chat", return_value=fake):
        r = client.post("/tracker/catalog/translate", headers=headers, json={
            "q": "muringayila xyzunique",
        })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["english"] == "Drumstick Leaves"
    assert body["source"] == "ai"
    assert body["malayalam"] == "മുരിങ്ങയില"


def test_admin_catalog_page_has_ai_translate():
    headers, email = _headers("page")
    assert client.get("/tracker/catalog", headers=headers).status_code == 200
    session = TestClient(app)
    login = session.post(
        "/admin/login",
        data={"email": email, "password": "password123"},
        follow_redirects=False,
    )
    assert login.status_code in (302, 303), login.text[:300]
    page = session.get("/admin/tracker/catalog")
    assert page.status_code == 200, page.text[:500]
    assert "AI translate Manglish" in page.text
    assert 'id="c-ai-translate"' in page.text
    assert "/admin/tracker/catalog/translate" in page.text
    assert "Potato" in page.text
    assert "Tomato" in page.text
    assert "Built-in" in page.text
    assert 'id="catalog-search"' in page.text


def test_builtin_catalog_override():
    headers, email = _headers("builtin")
    session = TestClient(app)
    session.post("/admin/login", data={"email": email, "password": "password123"}, follow_redirects=True)
    save = session.post("/admin/tracker/catalog/builtin/save", data={
        "seed_key": "vegetables:potato",
        "english": "Potato XL",
        "malayalam": "ഉരുളക്കിഴങ്ങ്",
        "emoji": "🥔",
        "category": "vegetables",
        "scope": "personal",
        "aliases": "urula",
    }, follow_redirects=False)
    assert save.status_code == 302, save.text
    groups = client.get("/tracker/quick-add", headers=headers).json()["groups"]
    veg = next(g for g in groups if g["key"] == "vegetables")
    names = [e["english"] for e in veg["entries"]]
    assert "Potato XL" in names
    assert "Potato" not in names
    reset = session.post("/admin/tracker/catalog", data={
        "english": "Only Mine",
        "emoji": "⭐",
        "category": "custom",
        "scope": "personal",
    }, follow_redirects=False)
    assert reset.status_code == 302
