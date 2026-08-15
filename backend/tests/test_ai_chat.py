"""Ask AI — vault context and chat persistence."""
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app import models
from app.ai_chat import build_vault_context, detect_months, suggestion_hints
from app.ai_providers import create_provider
from app.deps import vault_id
from app.main import app

client = TestClient(app)


def _headers():
    email = f"ask-{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/auth/register", json={
        "email": email, "password": "password123", "full_name": "Ask User",
    })
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, email


def test_detect_months():
    today = datetime(2026, 8, 14)
    assert "2026-08" in detect_months("spend this month", today)
    assert "2026-07" in detect_months("last month statement", today)
    assert detect_months("HDFC statement for March 2026", today) == ["2026-03"]
    assert "2026-01" in detect_months("January 2026 credit card", today)
    two = detect_months("create a list from my last 2 months purchase history", today)
    assert "2026-07" in two and "2026-06" in two
    assert "2026-07" in detect_months("past two months of groceries", today)
    assert "2026-07" in detect_months("kazhinja maasam enna vaangiya?", today)
    randu = detect_months("randu maasam purchase history vech list undaakkan", today)
    assert "2026-07" in randu and "2026-06" in randu


def test_manglish_query_hints():
    from app.ai_chat import _manglish_query_hints
    hits = _manglish_query_hints("list il ulli sharkara enna atta podi vekkanam")
    joined = " ".join(hits).lower()
    assert "onion" in joined
    assert "jaggery" in joined
    assert "oil" in joined or "coconut" in joined
    assert "wheat" in joined or "atta" in joined


def test_context_includes_hospital_and_card_not_secrets():
    headers, email = _headers()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        uid = vault_id(user)
        person = models.Person(user_id=uid, name="Meera", relation=models.Relation.self_)
        db.add(person)
        db.flush()
        db.add(models.HospitalCard(
            person_id=person.id, hospital_name="Aster Medcity", ward="3A",
            patient_id_enc="should-never-appear-plain",
        ))
        db.add(models.Document(
            person_id=person.id,
            category=models.DocCategory.lab_report,
            title="CBC report",
            hospital_name="Aster Medcity",
            doc_date="2026-07-12",
            amount="1800",
            extracted_text="Haemoglobin 13.2 g/dL",
        ))
        card = models.FinanceAccount(
            user_id=uid, name="HDFC Millennia", account_type="credit_card",
            institution="HDFC", last4="4411", credit_limit=Decimal("200000"),
        )
        db.add(card)
        db.flush()
        cat = models.FinanceCategory(user_id=uid, name="Shopping", kind="expense")
        db.add(cat)
        db.flush()
        db.add(models.FinanceTransaction(
            user_id=uid, account_id=card.id, category_id=cat.id,
            txn_type="expense", amount=Decimal("2499.00"),
            txn_date="2026-08-03", payee="Amazon Pay", payment_method="credit_card",
        ))
        db.add(models.VaultItem(
            user_id=uid, name="Gmail", item_type="login",
            username="secret-user", password_enc="encrypted-password-blob",
        ))
        db.add(models.LockerItem(
            user_id=uid, title="PAN card", doc_type="pan",
            holder_name="Meera", id_number_enc="PAN-SECRET",
        ))
        db.commit()

        ctx = build_vault_context(
            db, user, "Aster Medcity reports and HDFC Millennia statement for August 2026"
        )
    finally:
        db.close()

    assert "Aster Medcity" in ctx
    assert "CBC report" in ctx
    assert "HDFC Millennia" in ctx
    assert "Amazon Pay" in ctx
    assert "2,499.00" in ctx
    assert "PAN card" in ctx
    assert "Gmail" in ctx
    assert "should-never-appear-plain" not in ctx
    assert "encrypted-password-blob" not in ctx
    assert "secret-user" not in ctx
    assert "PAN-SECRET" not in ctx
    assert "omitted" in ctx.lower()


def test_chat_requires_provider():
    headers, _ = _headers()
    r = client.post("/ai/chat", headers=headers, json={"message": "How much did we spend?"})
    assert r.status_code == 400
    assert "provider" in r.json()["detail"].lower()


def test_chat_roundtrip_with_mocked_llm():
    headers, email = _headers()
    create_r = client.post("/ai/providers", headers=headers, json={
        "name": "Test OpenRouter", "kind": "openrouter", "api_key": "sk-test",
        "is_default": True, "model": "openai/gpt-4o-mini",
    })
    assert create_r.status_code == 200, create_r.text

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        uid = vault_id(user)
        person = models.Person(user_id=uid, name="Arun", relation=models.Relation.self_)
        db.add(person)
        db.flush()
        db.add(models.Document(
            person_id=person.id, category=models.DocCategory.lab_report,
            title="Lipid profile", hospital_name="KIMS", doc_date="2026-06-01",
        ))
        db.commit()
    finally:
        db.close()

    with patch("app.ai_chat.complete_chat", return_value={
        "content": "KIMS has a Lipid profile dated 2026-06-01 for Arun.",
        "kind": "openrouter", "model": "openai/gpt-4o-mini",
        "prompt_tokens": 120, "completion_tokens": 40, "total_tokens": 160,
    }):
        r = client.post("/ai/chat", headers=headers, json={
            "message": "What reports do I have at KIMS?",
        })
    assert r.status_code == 200, r.text
    body = r.json()
    assert "KIMS" in body["reply"]
    assert body["thread_id"]
    assert len(body["messages"]) == 2
    assert body["messages"][0]["role"] == "user"
    assert body["messages"][1]["role"] == "assistant"

    # Usage log written for Ask AI
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        logs = db.query(models.AiUsageLog).filter(models.AiUsageLog.user_id == vault_id(user)).all()
        assert len(logs) >= 1
        log = logs[-1]
        assert log.client == "ask_ai"
        assert log.model == "openai/gpt-4o-mini"
        assert log.prompt_tokens == 120
        assert log.completion_tokens == 40
        assert log.total_tokens == 160
        assert log.ok is True
        assert log.request_text
        assert "KIMS" in (log.response_text or "") or log.response_text
    finally:
        db.close()

    listed = client.get("/ai/chat/threads", headers=headers)
    assert listed.status_code == 200
    assert any(t["id"] == body["thread_id"] for t in listed.json())

    detail = client.get(f"/ai/chat/threads/{body['thread_id']}", headers=headers)
    assert detail.status_code == 200
    assert len(detail.json()["messages"]) == 2

    gone = client.delete(f"/ai/chat/threads/{body['thread_id']}", headers=headers)
    assert gone.status_code == 200
    assert client.get("/ai/chat/threads", headers=headers).json() == []


def test_admin_ask_page_and_session_chat():
    email = f"ask-admin-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/auth/register", json={
        "email": email, "password": "password123", "full_name": "Admin Ask",
    })
    assert r.status_code == 201, r.text
    session = TestClient(app)
    login = session.post(
        "/admin/login",
        data={"email": email, "password": "password123"},
        follow_redirects=False,
    )
    assert login.status_code in (302, 303)

    page = session.get("/admin/ai")
    assert page.status_code == 200
    assert "Ask AI" in page.text
    assert "ask-shell" in page.text
    assert "/static/ask-ai.js" in page.text

    providers = session.get("/admin/ai/providers")
    assert providers.status_code == 200
    assert "Add provider" in providers.text

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        create_provider(
            db, user, name="Local", kind="ollama", is_default=True, api_key=None,
        )
        hints = suggestion_hints(db, user)
        assert hints
    finally:
        db.close()

    with patch("app.ai_chat.complete_chat", return_value={
        "content": "Nothing filed yet.", "kind": "ollama", "model": "llama3.2",
        "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
    }):
        chat = session.post("/admin/ai/ask/send", json={"message": "Any hospital reports?"})
    assert chat.status_code == 200, chat.text
    payload = chat.json()
    assert payload["reply"] == "Nothing filed yet."
    assert payload["thread_id"]

    with patch("app.ai_chat.complete_chat", return_value={
        "content": "pong", "kind": "ollama", "model": "llama3.2",
        "prompt_tokens": 8, "completion_tokens": 1, "total_tokens": 9,
    }):
        probe = session.post("/admin/ai/ask/test")
    assert probe.status_code == 200, probe.text
    assert probe.json()["ok"] is True
    assert "pong" in probe.json()["sample"].lower()

    # REST API uses the same connection probe
    tok = client.post("/auth/login", data={"username": email, "password": "password123"})
    assert tok.status_code == 200, tok.text
    headers = {"Authorization": f"Bearer {tok.json()['access_token']}"}
    with patch("app.ai_chat.complete_chat", return_value={
        "content": "pong", "kind": "ollama", "model": "llama3.2",
        "prompt_tokens": 8, "completion_tokens": 1, "total_tokens": 9,
    }):
        api_probe = client.post("/ai/test", headers=headers)
    assert api_probe.status_code == 200, api_probe.text
    assert api_probe.json()["ok"] is True

    logs_page = session.get("/admin/ai/logs")
    assert logs_page.status_code == 200
    assert "Usage logs" in logs_page.text
    assert "Ask AI" in logs_page.text or "ask_ai" in logs_page.text
    assert "Connection test" in logs_page.text or "connection_test" in logs_page.text


def test_connection_requires_provider():
    headers, _ = _headers()
    r = client.post("/ai/test", headers=headers)
    assert r.status_code == 400
    assert "provider" in r.json()["detail"].lower()


def test_parse_usage_openai_and_anthropic():
    from app.ai_usage import parse_usage
    assert parse_usage({"usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}}) == {
        "prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18,
    }
    assert parse_usage({"usage": {"input_tokens": 5, "output_tokens": 3}}) == {
        "prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8,
    }


def test_shopping_context_and_apply_list_action():
    from app.ai_chat import apply_shop_list_action, extract_vault_action

    display, action = extract_vault_action(
        "Here is a list.\n\n```vault-action\n"
        '{"type":"create_shop_list","name":"Sunday market","items":['
        '{"name":"atta podi"},{"name":"sharkara","quantity":2,"unit":"kg"},"mav podi"]}\n```'
    )
    assert "vault-action" not in display
    assert action["name"] == "Sunday market"
    assert len(action["items"]) == 3

    headers, email = _headers()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        uid = vault_id(user)
        lst = models.ShopList(user_id=uid, name="July shop", completed=True, completed_at=datetime(2026, 7, 20))
        db.add(lst)
        db.flush()
        db.add(models.ShopItem(
            list_id=lst.id, name="Coconut Oil (തേങ്ങാവെളിച്ചെണ്ണ)", checked=True,
            category="essentials", status="approved",
            updated_at=datetime(2026, 7, 18),
        ))
        db.add(models.ShopItem(
            list_id=lst.id, name="Rice (അരി)", checked=True, status="approved",
            updated_at=datetime(2026, 7, 18),
        ))
        db.commit()
        ctx = build_vault_context(db, user, "last month did I purchase oil?")
        assert "## Shopping List" in ctx
        assert "Coconut Oil" in ctx
        assert "2026-07" in ctx
        created = apply_shop_list_action(db, user, action)
    finally:
        db.close()

    assert created["list_id"]
    assert created["item_count"] >= 3
    assert "/admin/tracker/lists/" in created["url"]

    detail = client.get(f"/tracker/lists/{created['list_id']}", headers=headers)
    assert detail.status_code == 200, detail.text
    names = " ".join(i["name"].lower() for i in detail.json()["items"])
    assert "atta" in names or "wheat" in names or "podi" in names


def test_chat_returns_shop_list_action():
    headers, email = _headers()
    assert client.post("/ai/providers", headers=headers, json={
        "name": "Shop AI", "kind": "openrouter", "api_key": "sk-test",
        "is_default": True, "model": "openai/gpt-4o-mini",
    }).status_code == 200

    reply = (
        "I'll make a list with atta and jaggery.\n\n```vault-action\n"
        '{"type":"create_shop_list","name":"Kitchen restock","items":['
        '{"name":"Atta"},{"name":"Jaggery"}]}\n```'
    )
    with patch("app.ai_chat.complete_chat", return_value={
        "content": reply, "kind": "openrouter", "model": "openai/gpt-4o-mini",
        "prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30,
    }):
        r = client.post("/ai/chat", headers=headers, json={
            "message": "create a shopping list with atta and sharkara",
        })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["action"]["type"] == "create_shop_list"
    assert body["action"]["name"] == "Kitchen restock"
    assert "vault-action" not in body["reply"]

    applied = client.post("/ai/chat/apply-shop-list", headers=headers, json=body["action"])
    assert applied.status_code == 200, applied.text
    assert applied.json()["item_count"] == 2
    assert client.get(f"/tracker/lists/{applied.json()['list_id']}", headers=headers).status_code == 200

