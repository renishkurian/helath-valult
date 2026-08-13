from fastapi.testclient import TestClient
from app.main import app
from app.finance_ai import classify_heuristic, split_messages

client = TestClient(app)


def _headers():
    r = client.post("/auth/register", json={
        "email": "money@example.com", "password": "password123", "full_name": "Money User",
    })
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_heuristic_debit_upi():
    out = classify_heuristic("Dear Customer, Rs.450.00 has been debited via UPI to SWIGGY on 13-08-2026.")
    assert out["direction"] == "debit"
    assert out["amount"] == 450
    assert out["category"] == "Food & dining"


def test_heuristic_credit_salary():
    out = classify_heuristic("INR 25,000.00 credited to your account from ACME PAYROLL on 01-08-2026")
    assert out["direction"] == "credit"
    assert out["amount"] == 25000
    assert out["category"] == "Salary"


def test_split_blank_lines():
    chunks = split_messages("msg one\n\nmsg two")
    assert chunks == ["msg one", "msg two"]


def test_finance_summary_and_txn():
    headers = _headers()
    r = client.get("/finance/summary", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "income" in body and "expense" in body

    accounts = client.get("/finance/accounts", headers=headers).json()
    cats = client.get("/finance/categories", headers=headers).json()
    assert accounts and cats
    expense_cat = next(c for c in cats if c["kind"] == "expense")
    r = client.post("/finance/transactions", headers=headers, json={
        "account_id": accounts[0]["id"],
        "category_id": expense_cat["id"],
        "txn_type": "expense",
        "amount": 199,
        "txn_date": "2026-08-13",
        "payee": "Netflix",
    })
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == 199

    r = client.post("/finance/messages/ingest", headers=headers, json={
        "text": "Rs.99.00 debited via UPI to NETFLIX on 13-08-2026",
        "account_id": accounts[0]["id"],
        "auto_accept": False,
    })
    assert r.status_code == 200, r.text
    msgs = r.json()
    assert msgs[0]["direction"] == "debit"
    assert msgs[0]["suggested_category"] == "Subscriptions"
