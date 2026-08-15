"""Quick Add catalog — personal vs global chips."""
import uuid

from fastapi.testclient import TestClient

from app import models
from app.database import SessionLocal
from app.deps import vault_id
from app.grocery import grouped_quick_add
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
