"""Shared AI providers module."""
import uuid

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app import models
from app.ai_providers import create_provider, get_default_bundle, list_providers
from app.main import app
from app.deps import vault_id

client = TestClient(app)


def _headers():
    email = f"ai-{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/auth/register", json={
        "email": email, "password": "password123", "full_name": "AI User",
    })
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, email


def test_shared_ai_providers_and_finance_alias():
    headers, email = _headers()
    r = client.get("/ai/providers", headers=headers)
    assert r.status_code == 200
    assert r.json() == []

    r = client.post("/ai/providers", headers=headers, json={
        "name": "Local Ollama", "kind": "ollama", "is_default": True,
        "base_url": "http://127.0.0.1:11434/v1", "model": "llama3.2",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Local Ollama"
    assert body["is_default"] is True

    # Finance alias reads the same store
    r = client.get("/finance/ai-keys", headers=headers)
    assert r.status_code == 200
    assert any(k["name"] == "Local Ollama" for k in r.json())

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        bundle = get_default_bundle(db, user)
        assert bundle is not None
        assert bundle["kind"] == "ollama"
        assert len(list_providers(db, user)) == 1
        # Migration table may exist empty; shared table has the row
        assert db.query(models.AiProvider).filter(models.AiProvider.user_id == vault_id(user)).count() == 1
    finally:
        db.close()

    r = client.delete(f"/ai/providers/{body['id']}", headers=headers)
    assert r.status_code == 200
    assert client.get("/ai/providers", headers=headers).json() == []


def test_create_via_finance_alias_writes_shared():
    headers, _ = _headers()
    r = client.post("/finance/ai-keys", headers=headers, json={
        "name": "Via Finance", "kind": "openai", "api_key": "sk-test", "is_default": True,
    })
    assert r.status_code == 200, r.text
    shared = client.get("/ai/providers", headers=headers).json()
    assert any(p["name"] == "Via Finance" and p["has_key"] for p in shared)
