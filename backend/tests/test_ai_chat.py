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


def test_resolve_ledger_day_and_deterministic_today_spend():
    from app.ai_chat import (
        ask,
        format_money_manager_day_reply,
        resolve_ledger_day,
        should_answer_ledger_day,
        vault_today,
    )

    today = datetime(2026, 8, 16, 19, 0, 0)
    assert resolve_ledger_day("todays total expesne", today) == "2026-08-16"
    assert resolve_ledger_day("What is the todays total expense", today) == "2026-08-16"
    assert resolve_ledger_day("yesterday spend", today) == "2026-08-15"
    assert resolve_ledger_day("any upi trasaction today?", today) == "2026-08-16"
    assert resolve_ledger_day("what about yesterday", today) == "2026-08-15"
    from app.ai_chat import needs_spend_clarify, resolve_spend_source
    assert needs_spend_clarify("any upi trasaction today?") is True
    assert needs_spend_clarify("todays total expense") is False
    assert resolve_spend_source("gmail") == "analyser"
    assert resolve_spend_source("ledger") == "ledger"
    assert should_answer_ledger_day(
        "are u sure",
        [{"role": "user", "content": "todays total expense"}],
        today,
    ) == "2026-08-16"

    headers, email = _headers()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        uid = vault_id(user)
        acc = models.FinanceAccount(user_id=uid, name="Home", account_type="cash")
        db.add(acc)
        db.flush()
        cat = models.FinanceCategory(user_id=uid, name="Shopping", kind="expense")
        db.add(cat)
        db.flush()
        day = vault_today()
        db.add(models.FinanceTransaction(
            user_id=uid, account_id=acc.id, category_id=cat.id,
            txn_type="expense", amount=Decimal("962.00"),
            txn_date=day, payee="Be A Bank Employee",
        ))
        db.add(models.FinanceTransaction(
            user_id=uid, account_id=acc.id, category_id=cat.id,
            txn_type="expense", amount=Decimal("158.00"),
            txn_date=day, payee="HDFC Bank",
        ))
        from app import crypto
        db.add(models.DiaryEntry(
            user_id=uid, title="Petrol",
            body_enc=crypto.encrypt_text("| Petrol | 250 |\n| Total | 250 |"),
            entry_date="2026-08-15",
        ))
        db.commit()
        reply = format_money_manager_day_reply(db, user, day)
        assert "1,120.00" in reply or "1120.00" in reply.replace(",", "")
        assert "Be A Bank Employee" in reply
        assert "Petrol" not in reply
        assert "Digital Diary" in reply

        out = ask(db, user, "todays total expense")
        assert "1,120.00" in out["reply"] or "1120.00" in out["reply"].replace(",", "")
        assert "Petrol" not in out["reply"]
        assert out["action"] is None
    finally:
        db.close()


def test_upi_day_includes_unposted_gmail_alerts():
    from app.ai_chat import ask, format_money_manager_day_reply, vault_today

    headers, email = _headers()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        uid = vault_id(user)
        day = vault_today()
        db.add(models.ExpenseAnalyserItem(
            user_id=uid, gmail_message_id="m-upi-1", kind="alert",
            subject="UPI transaction", from_addr="alerts@hdfcbank.bank.in",
            amount=Decimal("42.00"), payee="HDFC UPI", txn_date=day,
            payment_method="upi", status="pending", direction="debit",
        ))
        db.add(models.ExpenseAnalyserItem(
            user_id=uid, gmail_message_id="m-cc-1", kind="alert",
            subject="Credit card statement AUGUST 2026",
            from_addr="cc.statements@axis.bank.in",
            amount=Decimal("1500.00"), payee="Axis", txn_date=day,
            payment_method="credit_card", status="pending", direction="debit",
        ))
        db.commit()
        reply = format_money_manager_day_reply(
            db, user, day, question="any upi trasaction today?",
        )
        assert "42.00" in reply.replace(",", "")
        assert "HDFC UPI" in reply
        assert "Expense Analyser" in reply
        assert "1500" not in reply.replace(",", "")
        assert "Axis" not in reply
        out = ask(db, user, "any upi trasaction today?")
        assert "Which should I check?" in out["reply"]
        assert "42.00" not in out["reply"].replace(",", "")
        picked = ask(db, user, "2", thread_id=out["thread_id"])
        assert "42.00" in picked["reply"].replace(",", "")
        assert "HDFC UPI" in picked["reply"]
        assert "Inbox" in picked["reply"] or "Expense Analyser" in picked["reply"]
        # Recheck in the same thread must re-read live DB, not repeat a stale chat answer.
        db.add(models.ExpenseAnalyserItem(
            user_id=uid, gmail_message_id="m-upi-sib", kind="alert",
            subject="Transaction Alert!", from_addr="alerts@southindianbank.com",
            amount=Decimal("5775.00"), payee="Jibin S", txn_date=day,
            payment_method="upi", status="pending", direction="debit",
        ))
        db.commit()
        again = ask(db, user, "double checkit", thread_id=out["thread_id"])
        assert "5775" in again["reply"].replace(",", "")
        yday = ask(db, user, "what about yesterday", thread_id=out["thread_id"])
        assert "Expense Analyser" in yday["reply"] or "Gmail" in yday["reply"]
    finally:
        db.close()


def test_analyser_upi_breakdown_matches_insights_category_total():
    from app.ai_chat import ask, parse_question_amount, wants_analyser_upi_breakdown, vault_today

    q = "list out 97,055.27 upi trans actions fro expense analayser"
    assert wants_analyser_upi_breakdown(q) is True
    assert parse_question_amount(q) == 97055.27

    headers, email = _headers()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        uid = vault_id(user)
        day = vault_today()
        db.add(models.ExpenseAnalyserItem(
            user_id=uid, gmail_message_id="m-a", kind="alert",
            amount=Decimal("40000.00"), payee="Ramanathan", txn_date=day,
            payment_method="upi", suggested_category="UPI / transfers",
            status="pending", direction="debit",
        ))
        db.add(models.ExpenseAnalyserItem(
            user_id=uid, gmail_message_id="m-b", kind="alert",
            amount=Decimal("5775.00"), payee="Jibin S", txn_date=day,
            payment_method="upi", suggested_category="UPI / transfers",
            status="pending", direction="debit",
        ))
        db.add(models.ExpenseAnalyserItem(
            user_id=uid, gmail_message_id="m-c", kind="alert",
            amount=Decimal("1500.00"), payee="Axis", txn_date=day,
            payment_method="credit_card", suggested_category="UPI / transfers",
            status="pending", direction="debit",
        ))
        db.commit()
        out = ask(db, user, q)
        reply = out["reply"]
        assert "UPI / transfers" in reply
        assert "47,275" in reply or "47275" in reply.replace(",", "")
        assert "Jibin" in reply
        assert "Axis" in reply
        assert "payment_method" in reply.lower() or "payment method" in reply.lower() or "Inbox UPI filter" in reply
    finally:
        db.close()


def test_highest_purchase_uses_ledger_payee_not_category():
    from app.ai_chat import ask, wants_highest_expense, should_answer_highest_expense

    q = "in my purchase which is teh hght pid item"
    assert wants_highest_expense(q) is True
    assert should_answer_highest_expense("what was that", [{"role": "user", "content": q}]) is True

    headers, email = _headers()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        uid = vault_id(user)
        acc = models.FinanceAccount(user_id=uid, name="Home", account_type="cash")
        db.add(acc)
        db.flush()
        cat = models.FinanceCategory(user_id=uid, name="Shopping", kind="expense")
        db.add(cat)
        db.flush()
        db.add(models.FinanceTransaction(
            user_id=uid, account_id=acc.id, category_id=cat.id,
            txn_type="expense", amount=Decimal("209.00"),
            txn_date="2026-08-15", payee="Home Purchase",
        ))
        db.add(models.FinanceTransaction(
            user_id=uid, account_id=acc.id, category_id=cat.id,
            txn_type="expense", amount=Decimal("88.00"),
            txn_date="2026-08-16", payee="HDFC Bank",
        ))
        db.commit()
        out = ask(db, user, q)
        assert "Home Purchase" in out["reply"]
        assert "209" in out["reply"]
        assert "962" not in out["reply"]
        assert "not available" not in out["reply"].lower()
        follow = ask(db, user, "what was that", thread_id=out["thread_id"])
        assert "Home Purchase" in follow["reply"]
    finally:
        db.close()


def test_password_lookup_is_local_view_link_not_secret():
    from app.ai_chat import ask, wants_password_lookup

    assert wants_password_lookup("what is my password for Gmail") is True
    headers, email = _headers()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        uid = vault_id(user)
        item = models.VaultItem(
            user_id=uid, name="Gmail", item_type="login",
            username="secret-user", password_enc="encrypted-password-blob",
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        out = ask(db, user, "what is my password for Gmail")
        assert "/admin/passwords/" + item.id in out["reply"]
        assert "Gmail" in out["reply"]
        assert "encrypted-password-blob" not in out["reply"]
        assert "secret-user" not in out["reply"]
        assert "not" in out["reply"].lower() and "sent" in out["reply"].lower()
    finally:
        db.close()


def test_locker_lookup_finds_land_tax_typo_locally():
    from app.ai_chat import ask, wants_locker_lookup

    assert wants_locker_lookup("any land taxx file u have") is True
    assert wants_locker_lookup("lab report file") is False
    headers, email = _headers()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        uid = vault_id(user)
        folder = models.LockerFolder(user_id=uid, name="Govt")
        db.add(folder)
        db.flush()
        item = models.LockerItem(
            user_id=uid, folder_id=folder.id, title="land tax",
            doc_type="govt", holder_name="Renish", id_number_enc="TAX-SECRET",
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        assert wants_locker_lookup("any land taxx file u have", db, user) is True
        out = ask(db, user, "any land taxx file u have")
        assert "/admin/locker/" + item.id in out["reply"]
        assert "land tax" in out["reply"].lower()
        assert "TAX-SECRET" not in out["reply"]
        assert "Document Vault" in out["reply"]
    finally:
        db.close()


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

    assert "HDFC Millennia" in ctx
    assert "Amazon Pay" in ctx
    assert "2,499.00" in ctx
    assert "should-never-appear-plain" not in ctx
    assert "encrypted-password-blob" not in ctx
    assert "secret-user" not in ctx
    assert "PAN-SECRET" not in ctx
    assert "Haemoglobin" not in ctx
    assert "not sent to the AI provider" in ctx
    # Login names and medical titles stay off the provider snapshot
    assert "Gmail (" not in ctx
    assert "CBC report" not in ctx
    assert "PAN card" not in ctx


def test_today_money_manager_block_in_context():
    from app.ai_chat import vault_today

    headers, email = _headers()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        uid = vault_id(user)
        acc = models.FinanceAccount(
            user_id=uid, name="Cash", account_type="cash",
        )
        db.add(acc)
        db.flush()
        cat = models.FinanceCategory(user_id=uid, name="Transport", kind="expense")
        db.add(cat)
        db.flush()
        day = vault_today()
        db.add(models.FinanceTransaction(
            user_id=uid, account_id=acc.id, category_id=cat.id,
            txn_type="expense", amount=Decimal("962.00"),
            txn_date=day, payee="Be A Bank Employee", payment_method="credit_card",
        ))
        db.add(models.FinanceTransaction(
            user_id=uid, account_id=acc.id, category_id=cat.id,
            txn_type="expense", amount=Decimal("88.00"),
            txn_date=day, payee="HDFC Bank", payment_method="upi",
        ))
        # Diary petrol must not replace ledger “today”
        from app import crypto
        db.add(models.DiaryEntry(
            user_id=uid, title="Petrol", body_enc=crypto.encrypt_text("Petrol | 250"),
            entry_date="2026-08-15",
        ))
        db.commit()
        ctx = build_vault_context(db, user, "What is the todays total expense")
    finally:
        db.close()

    assert f"Today (Money Manager) {day}" in ctx
    assert "1,050.00" in ctx or "1050.00" in ctx.replace(",", "")
    assert "Be A Bank Employee" in ctx
    assert "HDFC Bank" in ctx
    assert "Omitted for this question" in ctx or "CANONICAL ANSWER" in ctx


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
    assert "Lipid profile" in body["reply"]
    assert "/admin/documents/" in body["reply"]
    assert "not" in body["reply"].lower() and "sent" in body["reply"].lower()
    assert body["thread_id"]
    assert len(body["messages"]) == 2
    assert body["messages"][0]["role"] == "user"
    assert body["messages"][1]["role"] == "assistant"

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

    brain = session.get("/admin/ai/brain")
    assert brain.status_code == 200
    assert "Household brain" in brain.text
    assert "remember" in brain.text.lower()

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
        chat = session.post("/admin/ai/ask/send", json={"message": "Summarise my shopping lists"})
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


def test_diary_context_search_and_apply_entry_action():
    from app import crypto
    from app.ai_chat import apply_diary_entry_action, extract_vault_action, format_diary_charges_table

    table = format_diary_charges_table(
        [{"label": "Cake", "amount": 1200}, {"label": "Decor", "amount": 800}],
        preface="Party rough costs",
    )
    assert "Cake" in table and "2,000.00" in table and "Total" in table

    display, action = extract_vault_action(
        "Here is the total.\n\n| Item | Amount |\n| --- | ---: |\n| Cake | 1200 |\n\n"
        "```vault-action\n"
        '{"type":"create_diary_entry","title":"Party charges","body":"Rough list",'
        '"charges":[{"label":"Cake","amount":1200},{"label":"Decor","amount":800}],'
        '"category":"Personal","tags":"party"}\n```'
    )
    assert "vault-action" not in display
    assert action["type"] == "create_diary_entry"
    assert action["title"] == "Party charges"
    assert "Total" in action["body"]
    assert len(action["charges"]) == 2

    headers, email = _headers()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        uid = vault_id(user)
        from app.routers import diary as dy
        dy.ensure_defaults(db, user)
        cat = (
            db.query(models.DiaryCategory)
            .filter(models.DiaryCategory.user_id == uid, models.DiaryCategory.name == "Personal")
            .first()
        )
        db.add(models.DiaryEntry(
            user_id=uid, title="Beach day",
            body_enc=crypto.encrypt_text("We bought coconut water and snacks by the shore."),
            entry_date="2026-08-10", category_id=cat.id if cat else None, tags="travel",
        ))
        db.commit()
        ctx = build_vault_context(db, user, "diary beach coconut")
        assert "## Digital Diary" in ctx
        assert "Beach day" in ctx
        assert "coconut" in ctx.lower()
        created = apply_diary_entry_action(db, user, action)
    finally:
        db.close()

    assert created["entry_id"]
    assert "/admin/diary/" in created["url"]

    listed = client.get("/diary", headers=headers, params={"q": "coconut"}).json()
    assert any(e["title"] == "Beach day" for e in listed)

    detail = client.get(f"/diary/{created['entry_id']}", headers=headers)
    assert detail.status_code == 200, detail.text
    body = detail.json()["body"]
    assert "Cake" in body and "2,000.00" in body


def test_chat_returns_diary_entry_action():
    headers, _ = _headers()
    assert client.post("/ai/providers", headers=headers, json={
        "name": "Diary AI", "kind": "openrouter", "api_key": "sk-test",
        "is_default": True, "model": "openai/gpt-4o-mini",
    }).status_code == 200

    reply = (
        "Total is 2450.\n\n```vault-action\n"
        '{"type":"create_diary_entry","title":"Snack run","charges":['
        '{"label":"Tea","amount":50},{"label":"Snacks","amount":2400}],'
        '"tags":"food"}\n```'
    )
    with patch("app.ai_chat.complete_chat", return_value={
        "content": reply, "kind": "openrouter", "model": "openai/gpt-4o-mini",
        "prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30,
    }):
        r = client.post("/ai/chat", headers=headers, json={
            "message": "tea 50 snacks 2400 add to diary",
        })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["action"]["type"] == "create_diary_entry"
    assert body["action"]["title"] == "Snack run"
    assert "vault-action" not in body["reply"]

    applied = client.post("/ai/chat/apply-diary-entry", headers=headers, json=body["action"])
    assert applied.status_code == 200, applied.text
    assert applied.json()["entry_id"]
    assert client.get(f"/diary/{applied.json()['entry_id']}", headers=headers).status_code == 200



def test_finance_txn_action_normalize_and_apply():
    from app.ai_chat import apply_finance_txn_action, extract_vault_action

    display, action = extract_vault_action(
        "Got it — ₹250 petrol on Cash.\n\n"
        "```vault-action\n"
        '{"type":"create_finance_txn","amount":250,"payee":"Petrol","account":"Cash",'
        '"category":"Transport","txn_type":"expense","payment_method":"cash"}\n```'
    )
    assert "vault-action" not in display
    assert action["type"] == "create_finance_txn"
    assert action["amount"] == 250
    assert action["payee"] == "Petrol"

    headers, email = _headers()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        from app.routers import finance as fn
        fn.ensure_defaults(db, user)
        created = apply_finance_txn_action(db, user, action)
    finally:
        db.close()

    assert created["txn_id"]
    assert created["amount"] == 250
    assert "/admin/finance" in created["url"]

    listed = client.get("/finance/transactions", headers=headers)
    assert listed.status_code == 200, listed.text
    assert any(
        float(t["amount"]) == 250 and (t.get("payee") or "").lower().find("petrol") >= 0
        for t in listed.json()
    )


def test_chat_returns_finance_txn_action():
    headers, _ = _headers()
    assert client.post("/ai/providers", headers=headers, json={
        "name": "Finance AI", "kind": "openrouter", "api_key": "sk-test",
        "is_default": True, "model": "openai/gpt-4o-mini",
    }).status_code == 200

    reply = (
        "Saving petrol to Money Manager.\n\n```vault-action\n"
        '{"type":"create_finance_txn","amount":250,"payee":"Petrol","payment_method":"cash"}\n```'
    )
    with patch("app.ai_chat.complete_chat", return_value={
        "content": reply, "kind": "openrouter", "model": "openai/gpt-4o-mini",
        "prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30,
    }):
        r = client.post("/ai/chat", headers=headers, json={
            "message": "money manager — 250 petrol",
        })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["action"]["type"] == "create_finance_txn"
    assert body["action"]["amount"] == 250
    assert "vault-action" not in body["reply"]

    applied = client.post("/ai/chat/apply-finance-txn", headers=headers, json=body["action"])
    assert applied.status_code == 200, applied.text
    assert applied.json()["txn_id"]


def test_diary_folder_action_and_api():
    from app.ai_chat import apply_diary_folder_action, extract_vault_action

    display, action = extract_vault_action(
        "I'll make a folder for the trip.\n\n"
        "```vault-action\n"
        '{"type":"create_diary_folder","name":"Thidanad trip","color":"#22D3EE"}\n```'
    )
    assert "vault-action" not in display
    assert action["type"] == "create_diary_folder"
    assert action["name"] == "Thidanad trip"

    headers, email = _headers()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        created = apply_diary_folder_action(db, user, action)
        again = apply_diary_folder_action(db, user, action)
    finally:
        db.close()

    assert created["created"] is True
    assert created["folder_id"]
    assert again["created"] is False
    assert again["folder_id"] == created["folder_id"]

    listed = client.get("/diary/categories", headers=headers)
    assert listed.status_code == 200
    assert any(c["name"] == "Thidanad trip" for c in listed.json())

    dup = client.post("/diary/categories", headers=headers, json={"name": "Thidanad trip"})
    assert dup.status_code == 400


def test_household_brain_learns_from_chat_without_provider():
    from app.ai_brain import extract_vault_memory

    cleaned, items = extract_vault_memory(
        "Noted.\n\n```vault-memory\n"
        '{"memories":[{"kind":"preference","slug":"oil","content":"Prefer coconut oil"}]}\n```'
    )
    assert "vault-memory" not in cleaned
    assert items[0]["content"] == "Prefer coconut oil"

    headers, email = _headers()
    taught = client.post(
        "/ai/chat",
        headers=headers,
        json={"message": "Remember that we always buy coconut oil, not sunflower"},
    )
    assert taught.status_code == 200, taught.text
    body = taught.json()
    assert body["learned"]
    assert any("coconut" in (m.get("content") or "").lower() for m in body["learned"])

    listed = client.get("/ai/brain", headers=headers)
    assert listed.status_code == 200
    rows = listed.json()
    assert any("coconut" in (m.get("content") or "").lower() for m in rows)

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        ctx = build_vault_context(db, user, "which oil should I buy")
    finally:
        db.close()
    assert "HOUSEHOLD BRAIN" in ctx
    assert "coconut" in ctx.lower()

    secret = client.post(
        "/ai/chat",
        headers=headers,
        json={"message": "Remember my password is hunter2secret"},
    )
    assert secret.status_code == 200, secret.text
    assert secret.json()["learned"] == []

    forgot = client.post(
        "/ai/chat",
        headers=headers,
        json={"message": "Forget coconut oil"},
    )
    assert forgot.status_code == 200, forgot.text
    after = client.get("/ai/brain", headers=headers).json()
    assert not any("coconut" in (m.get("content") or "").lower() for m in after)

    added = client.post(
        "/ai/brain",
        headers=headers,
        json={"content": "Petrol usually posts to the Home cash account", "kind": "habit"},
    )
    assert added.status_code == 200, added.text
    mem_id = added.json()["id"]
    gone = client.delete(f"/ai/brain/{mem_id}", headers=headers)
    assert gone.status_code == 200


def test_household_brain_persists_model_vault_memory_block():
    """Model-emitted ```vault-memory``` must be saved (not only explicit remember…)."""
    headers, email = _headers()
    create_r = client.post("/ai/providers", headers=headers, json={
        "name": "Brain Mock", "kind": "openrouter", "api_key": "sk-test",
        "is_default": True, "model": "openai/gpt-4o-mini",
    })
    assert create_r.status_code == 200, create_r.text

    fake = (
        "Got it — I'll use Home for petrol.\n\n"
        "```vault-memory\n"
        '{"memories":[{"kind":"habit","slug":"petrol-account",'
        '"content":"When logging petrol, use account Home"}]}\n'
        "```"
    )
    with patch("app.ai_chat.complete_chat", return_value={
        "content": fake,
        "kind": "openrouter", "model": "openai/gpt-4o-mini",
        "prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30,
    }):
        r = client.post("/ai/chat", headers=headers, json={
            "message": "Which account should petrol go to? Use Home cash going forward.",
        })
    assert r.status_code == 200, r.text
    body = r.json()
    assert "vault-memory" not in (body.get("reply") or "")
    assert body.get("learned")
    assert any("petrol" in (m.get("content") or "").lower() for m in body["learned"])

    listed = client.get("/ai/brain", headers=headers)
    assert listed.status_code == 200
    rows = listed.json()
    assert any("petrol" in (m.get("content") or "").lower() for m in rows)
