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
    assert out["payment_method"] == "upi"
    assert "UPI" in (out["description"] or "")


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
    assert msgs[0]["payment_method"] == "upi"


def test_heuristic_card_and_atm():
    cc = classify_heuristic("INR 2,500.00 spent on HDFC credit card xx1234 at AMAZON on 12-08-2026")
    assert cc["direction"] == "debit"
    assert cc["payment_method"] == "credit_card"
    assert cc["category"] == "Shopping"
    dc = classify_heuristic("Rs.800.00 debited from debit card xx7788 at RELIANCE POS")
    assert dc["direction"] == "debit"
    assert dc["payment_method"] == "debit_card"
    atm = classify_heuristic("Rs.2000 withdrawn at ATM from a/c XX12 on 11-08-2026")
    assert atm["direction"] == "debit"
    assert atm["payment_method"] == "atm"
    assert atm["category"] == "ATM / cash"


def test_month_carry_forward():
    r = client.post("/auth/register", json={
        "email": "carry@example.com", "password": "password123", "full_name": "Carry User",
    })
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    accounts = client.get("/finance/accounts", headers=headers).json()
    cats = client.get("/finance/categories", headers=headers).json()
    bank = next(a for a in accounts if a["account_type"] == "bank")
    income_cat = next(c for c in cats if c["kind"] == "income")
    expense_cat = next(c for c in cats if c["kind"] == "expense")
    assert client.post("/finance/transactions", headers=headers, json={
        "account_id": bank["id"], "category_id": income_cat["id"], "txn_type": "income",
        "amount": 10000, "txn_date": "2026-07-05", "payee": "Salary",
        "description": "July salary", "payment_method": "netbanking",
    }).status_code == 200
    assert client.post("/finance/transactions", headers=headers, json={
        "account_id": bank["id"], "category_id": expense_cat["id"], "txn_type": "expense",
        "amount": 2500, "txn_date": "2026-07-20", "payee": "Rent",
        "description": "July rent", "payment_method": "upi",
    }).status_code == 200
    assert client.post("/finance/transactions", headers=headers, json={
        "account_id": bank["id"], "category_id": expense_cat["id"], "txn_type": "expense",
        "amount": 500, "txn_date": "2026-08-03", "payee": "Milk",
        "description": "Morning milk", "payment_method": "cash",
    }).status_code == 200
    august = client.get("/finance/summary", headers=headers, params={"year_month": "2026-08"}).json()
    assert august["prev_income"] == 10000
    assert august["prev_expense"] == 2500
    assert august["opening"] == 7500
    assert august["income"] == 0
    assert august["expense"] == 500
    assert august["total"] == -500
    assert august["closing"] == 7000
    txn = client.get("/finance/transactions", headers=headers, params={"year_month": "2026-08"}).json()[0]
    assert txn["description"] == "Morning milk"
    assert txn["payment_method"] == "cash"


def test_account_scoped_categories():
    r = client.post("/auth/register", json={
        "email": "home@example.com", "password": "password123", "full_name": "Home User",
    })
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    client.get("/finance/accounts", headers=headers)
    home = client.post("/finance/accounts", headers=headers, json={
        "name": "Home", "account_type": "bank",
    }).json()
    personal = client.post("/finance/accounts", headers=headers, json={
        "name": "Personal", "account_type": "bank",
    }).json()
    maid = client.post("/finance/categories", headers=headers, json={
        "name": "Maid", "kind": "expense", "account_id": home["id"],
    }).json()
    assert maid["scope"] == "account"
    assert maid["account_name"] == "Home"
    gym = client.post("/finance/categories", headers=headers, json={
        "name": "Gym", "kind": "expense", "account_id": personal["id"],
    }).json()
    assert gym["account_name"] == "Personal"
    home_cats = client.get("/finance/categories", headers=headers, params={"account_id": home["id"]}).json()
    names = {c["name"] for c in home_cats}
    assert "Maid" in names
    assert "Gym" not in names
    assert "Food & dining" in names
    bad = client.post("/finance/transactions", headers=headers, json={
        "account_id": personal["id"], "category_id": maid["id"], "txn_type": "expense",
        "amount": 50, "txn_date": "2026-08-13",
    })
    assert bad.status_code == 400
    ok = client.post("/finance/transactions", headers=headers, json={
        "account_id": home["id"], "category_id": maid["id"], "txn_type": "expense",
        "amount": 50, "txn_date": "2026-08-13", "description": "August maid",
    })
    assert ok.status_code == 200, ok.text
    general = next(c for c in client.get("/finance/categories", headers=headers).json() if c["name"] == "Food & dining")
    shared = client.post("/finance/transactions", headers=headers, json={
        "account_id": personal["id"], "category_id": general["id"], "txn_type": "expense",
        "amount": 20, "txn_date": "2026-08-13",
    })
    assert shared.status_code == 200, shared.text


def test_admin_finance_monthly_view():
    client.post("/auth/register", json={
        "email": "monthly@example.com", "password": "password123", "full_name": "Monthly User",
    })
    r = client.post(
        "/admin/login",
        data={"email": "monthly@example.com", "password": "password123"},
        follow_redirects=False,
    )
    assert r.status_code in (200, 302), r.text
    r = client.get("/admin/finance?month=2026-08&view=monthly")
    assert r.status_code == 200, r.text
    assert "Internal Server Error" not in r.text
    assert "Monthly" in r.text


def test_transaction_optional_image():
    r = client.post("/auth/register", json={
        "email": "photo@example.com", "password": "password123", "full_name": "Photo User",
    })
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    accounts = client.get("/finance/accounts", headers=headers).json()
    bank = next(a for a in accounts if a["account_type"] == "bank")
    r = client.post("/finance/transactions", headers=headers, json={
        "account_id": bank["id"], "txn_type": "expense",
        "amount": 12, "txn_date": "2026-08-13", "payee": "Tea",
    })
    assert r.status_code == 200, r.text
    txn = r.json()
    assert txn["has_image"] is False
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    up = client.post(
        f"/finance/transactions/{txn['id']}/image",
        headers=headers,
        files={"file": ("tea.png", png, "image/png")},
    )
    assert up.status_code == 200, up.text
    assert up.json()["has_image"] is True
    img = client.get(f"/finance/transactions/{txn['id']}/image", headers=headers)
    assert img.status_code == 200
    assert img.content
