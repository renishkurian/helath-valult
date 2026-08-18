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
    assert out["date"] == "2026-08-13"


def test_heuristic_south_indian_bank_upi_alert():
    html = """
    <html><body>
    <p>Dear Customer, This is to inform you that,</p>
    <p><span>INR 5775</span> was spent from your SOUTH INDIAN BANK account XXXXX5835
    Info - UPI/SBIN/659519060532/JIBIN S/UPI on 17-08-2026</p>
    </body></html>
    """
    from app.gmail import html_to_text
    text = html_to_text(html)
    out = classify_heuristic(text)
    assert out["direction"] == "debit"
    assert out["amount"] == 5775
    assert out["payment_method"] == "upi"
    assert out["date"] == "2026-08-17"
    assert out["payee"]
    assert "JIBIN" in out["payee"].upper()
    assert out["payee"].upper().rstrip(".").endswith("S")


def test_heuristic_sib_debit_alert_subject_style():
    out = classify_heuristic(
        "Dear Customer, This is to inform you that, "
        "INR 40000 was spent from your SOUTH INDIAN BANK account XXXXX5835 "
        "Info - UPI/PUNB/659577041995/RAMANATHAN NAIR D/UPI on 17-08-2026"
    )
    assert out["direction"] == "debit"
    assert out["amount"] == 40000
    assert out["payment_method"] == "upi"
    assert out["date"] == "2026-08-17"
    assert "RAMANATHAN" in (out["payee"] or "").upper()


def test_heuristic_hdfc_upi_txn_subject_style():
    out = classify_heuristic(
        "Dear Customer, You have done a UPI txn from HDFC Bank A/c XX1234 "
        "for Rs.100.00 to MERCHANT NAME on 14-08-2026"
    )
    assert out["direction"] == "debit"
    assert out["amount"] == 100
    assert out["payment_method"] == "upi"
    assert out["date"] == "2026-08-14"


def test_parse_txn_date_ignores_footer_statement_day():
    from app.finance_ai import _parse_txn_date
    text = (
        "Statement period 01-08-2026 to 05-08-2026. "
        "Available Credit Limit Rs.50000. "
        "Your ICICI Bank Credit Card XX2006 has been used for a transaction "
        "of INR 636.00 on Aug 10, 2026 at 04:56:03. Info: AMAZON PAY."
    )
    assert _parse_txn_date(text) == "2026-08-10"


def test_normalize_payee_casing():
    from app.finance_ai import normalize_payee, format_payee
    assert normalize_payee("FLIPKART I of INR 476.00 with your SBI Cr") == "Flipkart"
    assert normalize_payee("inform you that") is None
    assert normalize_payee("merchant platform using your SBI Credit C") is None
    assert format_payee("amazon pay") == "Amazon Pay"
    assert format_payee("HDFC BANK") == "HDFC Bank"


def test_heuristic_icici_credit_card_amazon():
    from app.finance_ai import classify_message, hard_correct
    text = (
        "Dear Customer, Your ICICI Bank Credit Card XX2006 has been used for a transaction "
        "of INR 636.00 on Aug 10, 2026 at 04:56:03. Info: AMAZON PAY IN RECHARGE. "
        "The Available Credit Limit on your card is INR 50000"
    )
    out = classify_heuristic(text)
    assert out["direction"] == "debit"
    assert out["payment_method"] == "credit_card"
    assert out["amount"] == 636
    assert out["category"] == "Shopping"
    assert "Amazon" in (out["payee"] or "")
    bad = {
        "direction": "credit", "amount": 636, "payee": "the primary card holder",
        "category": "ATM / cash", "payment_method": "atm", "confidence": 0.99,
    }
    fixed = hard_correct(text, bad)
    assert fixed["direction"] == "debit"
    assert fixed["payment_method"] == "credit_card"
    assert fixed["category"] == "Shopping"
    assert "Amazon" in (fixed["payee"] or "")
    assert classify_message(text)["payment_method"] == "credit_card"


def test_medical_merchant_not_emi_and_personal_upi_not_insurance():
    from app.finance_ai import classify_message, hard_correct

    medical = (
        "Dear Cardholder, This is to inform you that, Rs.481.00 spent on your "
        "SBI Credit Card ending 5824 at PALADIOCESANMEDICAL on 14/08/26. "
        "Trxn. not done by you? Report at https://example.com/click-here. "
        "Convert to Easy EMI on your next statement."
    )
    out = classify_heuristic(medical)
    assert out["direction"] == "debit"
    assert out["payment_method"] == "credit_card"
    assert out["category"] == "Health"
    # AI wrongly saying EMI must be corrected.
    fixed = hard_correct(medical, {
        "direction": "debit", "amount": 481, "payee": "PALADIOCESANMEDICAL",
        "category": "EMI / loans", "payment_method": "credit_card", "confidence": 0.99,
    })
    assert fixed["category"] == "Health"
    assert classify_message(medical)["category"] == "Health"

    personal = (
        "Dear Customer, Greetings from HDFC Bank! Rs.30.00 is debited from your "
        "account ending 6030 towards VPA sviji795@oksbi (VJ BIJI) on 14-08-26. "
        "UPI transaction reference no.: 659210606381. Please click here to manage alerts."
    )
    pout = classify_heuristic(personal)
    assert pout["direction"] == "debit"
    assert pout["payment_method"] == "upi"
    assert pout["category"] == "UPI / transfers"
    assert pout["category"] != "Insurance"
    pfixed = hard_correct(personal, {
        "direction": "debit", "amount": 30, "payee": "VJ BIJI",
        "category": "Insurance", "payment_method": "upi", "confidence": 0.99,
    })
    assert pfixed["category"] == "UPI / transfers"
    assert classify_message(personal)["category"] == "UPI / transfers"


def test_keyword_boundaries_skip_click_and_prefer_medical():
    from app.finance_ai import _keyword_category, _keyword_hit
    assert _keyword_hit("please click here to apply", "lic") is False
    assert _keyword_hit("lic premium due", "lic") is True
    assert _keyword_hit("convert to emi today", "emi") is True
    assert _keyword_hit("premium due now", "emi") is False
    cat, _ = _keyword_category(
        "spent at PALADIOCESANMEDICAL. Convert to Easy EMI. click here.",
        "debit",
    )
    assert cat == "Health"
    # Marketing EMI footer must not beat a medical merchant.
    assert _keyword_hit("convert to easy emi today", "emi") is True
    assert classify_heuristic(
        "Rs.100 spent on credit card at CITY HOSPITAL. Convert to Easy EMI. click here."
    )["category"] == "Health"


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


def test_bulk_delete_transactions():
    import uuid
    email = f"bulkdel-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/auth/register", json={
        "email": email, "password": "password123", "full_name": "Bulk Del",
    })
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    accounts = client.get("/finance/accounts", headers=headers).json()
    cats = client.get("/finance/categories", headers=headers).json()
    expense_cat = next(c for c in cats if c["kind"] == "expense" and not c.get("parent_id"))
    ids = []
    for i, payee in enumerate(("One", "Two", "Keep")):
        created = client.post("/finance/transactions", headers=headers, json={
            "account_id": accounts[0]["id"],
            "category_id": expense_cat["id"],
            "txn_type": "expense",
            "amount": 10 + i,
            "txn_date": "2026-08-16",
            "payee": payee,
        })
        assert created.status_code == 200, created.text
        ids.append(created.json()["id"])
    doomed = ids[:2]
    r = client.post("/finance/transactions/bulk-delete", headers=headers, json={"ids": doomed})
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] == 2
    left = client.get("/finance/transactions", headers=headers, params={"year_month": "2026-08"}).json()
    payees = {t["payee"] for t in left}
    assert "Keep" in payees
    assert "One" not in payees and "Two" not in payees
    trash = client.get("/finance/trash", headers=headers).json()
    trash_payees = {t["payee"] for t in trash}
    assert "One" in trash_payees and "Two" in trash_payees
    restore_id = next(t["id"] for t in trash if t["payee"] == "One")
    r = client.post(f"/finance/transactions/{restore_id}/restore", headers=headers)
    assert r.status_code == 200, r.text
    left = client.get("/finance/transactions", headers=headers, params={"year_month": "2026-08"}).json()
    assert "One" in {t["payee"] for t in left}
    r = client.post("/finance/trash/empty", headers=headers)
    assert r.status_code == 200, r.text
    assert client.get("/finance/trash", headers=headers).json() == []
    left = client.get("/finance/transactions", headers=headers, params={"year_month": "2026-08"}).json()
    assert "Keep" in {t["payee"] for t in left}
    assert "One" in {t["payee"] for t in left}


def test_finance_charts_endpoint():
    import uuid
    email = f"charts-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/auth/register", json={
        "email": email, "password": "password123", "full_name": "Charts User",
    })
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    accounts = client.get("/finance/accounts", headers=headers).json()
    cats = client.get("/finance/categories", headers=headers).json()
    expense_cat = next(c for c in cats if c["kind"] == "expense" and not c.get("parent_id"))
    client.post("/finance/transactions", headers=headers, json={
        "account_id": accounts[0]["id"],
        "category_id": expense_cat["id"],
        "txn_type": "expense",
        "amount": 250,
        "txn_date": "2026-08-16",
        "payee": "Cafe",
        "payment_method": "upi",
    })
    r = client.get("/finance/charts", headers=headers, params={"year_month": "2026-08"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["year_month"] == "2026-08"
    assert body["expense"] == 250
    assert len(body["daily"]) >= 28
    assert body["histogram"]
    assert len(body["weekday"]) == 7
    assert len(body["trend"]) == 12
    assert any(s["amount"] == 250 for s in body["categories"])
    assert body["payees"]
    assert body["days_in_month"] >= 28
    assert "heatmap_pad" in body
    assert body["period"] == "month"
    assert body["grain"] == "day"

    week = client.get("/finance/charts", headers=headers, params={"period": "week", "week": "2026-08-16"})
    assert week.status_code == 200, week.text
    wbody = week.json()
    assert wbody["period"] == "week"
    assert len(wbody["daily"]) == 7
    assert wbody["expense"] == 250
    assert wbody["week_start"] == "2026-08-10"

    year = client.get("/finance/charts", headers=headers, params={"period": "year", "year": "2026"})
    assert year.status_code == 200, year.text
    ybody = year.json()
    assert ybody["period"] == "year"
    assert ybody["grain"] == "month"
    assert len(ybody["daily"]) == 12
    assert ybody["expense"] == 250
    assert ybody["label"] == "2026"


def test_update_transaction():
    import uuid
    email = f"edit-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/auth/register", json={
        "email": email, "password": "password123", "full_name": "Edit User",
    })
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    accounts = client.get("/finance/accounts", headers=headers).json()
    cats = client.get("/finance/categories", headers=headers).json()
    expense_cat = next(c for c in cats if c["kind"] == "expense" and not c.get("parent_id"))
    created = client.post("/finance/transactions", headers=headers, json={
        "account_id": accounts[0]["id"],
        "category_id": expense_cat["id"],
        "txn_type": "expense",
        "amount": 50,
        "txn_date": "2026-08-16",
        "payee": "Old title",
        "payment_method": "upi",
    })
    assert created.status_code == 200, created.text
    txn_id = created.json()["id"]
    updated = client.put(f"/finance/transactions/{txn_id}", headers=headers, json={
        "account_id": accounts[0]["id"],
        "category_id": expense_cat["id"],
        "txn_type": "expense",
        "amount": 88,
        "txn_date": "2026-08-16",
        "payee": "HDFC Bank",
        "payment_method": "upi",
    })
    assert updated.status_code == 200, updated.text
    assert updated.json()["amount"] == 88
    assert updated.json()["payee"] == "HDFC Bank"
    got = client.get(f"/finance/transactions/{txn_id}", headers=headers)
    assert got.status_code == 200
    assert got.json()["payee"] == "HDFC Bank"


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


def test_category_subcategory():
    r = client.post("/auth/register", json={
        "email": "subcat@example.com", "password": "password123", "full_name": "Sub User",
    })
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    cats = client.get("/finance/categories", headers=headers).json()
    health = next(c for c in cats if c["name"] == "Health")
    assert health["parent_id"] is None
    medicine = client.post("/finance/categories", headers=headers, json={
        "name": "Medicine", "parent_id": health["id"],
    })
    assert medicine.status_code == 200, medicine.text
    body = medicine.json()
    assert body["parent_id"] == health["id"]
    assert body["parent_name"] == "Health"
    assert body["kind"] == "expense"
    listed = client.get("/finance/categories", headers=headers).json()
    med = next(c for c in listed if c["name"] == "Medicine")
    assert med["parent_name"] == "Health"
    nested = client.post("/finance/categories", headers=headers, json={
        "name": "Too deep", "parent_id": body["id"],
    })
    assert nested.status_code == 400


def test_emi_setup_auto_post_and_complete():
    from app.emi import installment_dates
    dates = installment_dates("2026-01-05", "2026-04-05", 5)
    assert [d.isoformat() for d in dates] == [
        "2026-01-05", "2026-02-05", "2026-03-05", "2026-04-05",
    ]
    r = client.post("/auth/register", json={
        "email": "emi@example.com", "password": "password123", "full_name": "Emi User",
    })
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    accounts = client.get("/finance/accounts", headers=headers).json()
    bank = next(a for a in accounts if a["account_type"] == "bank")
    created = client.post("/finance/emis", headers=headers, json={
        "name": "Bike EMI",
        "kind": "emi",
        "account_id": bank["id"],
        "amount": 4500,
        "start_date": "2026-08-13",
        "end_date": "2026-10-13",
        "day_of_month": 13,
        "notify_days": 2,
        "auto_post": True,
    })
    assert created.status_code == 200, created.text
    emi = created.json()
    assert emi["kind"] == "emi"
    assert emi["kind_label"] == "EMI"
    assert emi["total_installments"] == 3
    assert emi["paid_count"] == 0
    assert emi["status"] == "pending"
    assert emi["next_due"] == "2026-08-13"
    posted = client.post(f"/finance/emis/{emi['id']}/post", headers=headers)
    assert posted.status_code == 200, posted.text
    body = posted.json()
    assert body["paid_count"] == 1
    assert body["remaining"] == 2
    assert body["next_due"] == "2026-09-13"
    txns = client.get("/finance/transactions", headers=headers, params={"year_month": "2026-08"}).json()
    assert any(t["payee"] == "Bike EMI" and t["source"] == "emi" for t in txns)
    pending = client.get("/finance/emis", headers=headers, params={"status": "pending"}).json()
    assert any(e["id"] == emi["id"] for e in pending)
    chitty = client.post("/finance/emis", headers=headers, json={
        "name": "Office chitty",
        "kind": "chitty",
        "account_id": bank["id"],
        "amount": 2000,
        "start_date": "2026-09-01",
        "end_date": "2027-08-01",
        "day_of_month": 1,
    })
    assert chitty.status_code == 200, chitty.text
    assert chitty.json()["kind"] == "chitty"
    assert chitty.json()["kind_label"] == "Chitty"
    tagged = client.get("/finance/emis", headers=headers, params={"kind": "chitty"}).json()
    assert any(e["name"] == "Office chitty" for e in tagged)
    one = client.post("/finance/emis", headers=headers, json={
        "name": "Short EMI",
        "kind": "loan",
        "account_id": bank["id"],
        "amount": 100,
        "start_date": "2026-08-13",
        "end_date": "2026-08-13",
        "day_of_month": 13,
    }).json()
    assert one["kind"] == "loan"
    client.post(f"/finance/emis/{one['id']}/post", headers=headers)
    done = client.get("/finance/emis", headers=headers, params={"status": "completed"}).json()
    assert any(e["id"] == one["id"] for e in done)


def test_admin_finance_daily_and_monthly_view():
    r = client.post("/auth/register", json={
        "email": "monthly@example.com", "password": "password123", "full_name": "Monthly User",
    })
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    accounts = client.get("/finance/accounts", headers=headers).json()
    bank = next(a for a in accounts if a["account_type"] == "bank")
    client.post("/finance/transactions", headers=headers, json={
        "account_id": bank["id"], "txn_type": "expense",
        "amount": 75, "txn_date": "2026-08-13", "payee": "Tea stall",
    })
    r = client.post(
        "/admin/login",
        data={"email": "monthly@example.com", "password": "password123"},
        follow_redirects=False,
    )
    assert r.status_code in (200, 302), r.text
    r = client.get("/admin/finance")
    assert r.status_code == 200, r.text
    assert "Internal Server Error" not in r.text
    assert "Tea stall" in r.text
    r = client.get("/admin/finance?month=2026-08&view=monthly")
    assert r.status_code == 200, r.text
    assert "Internal Server Error" not in r.text
    assert "Monthly" in r.text
    assert "Tea stall" in r.text


def test_admin_account_statement_and_recurring_pages():
    r = client.post("/auth/register", json={
        "email": "webmm@example.com", "password": "password123", "full_name": "Web MM",
    })
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    accounts = client.get("/finance/accounts", headers=headers).json()
    bank = next(a for a in accounts if a["account_type"] == "bank")
    client.post("/finance/transactions", headers=headers, json={
        "account_id": bank["id"], "txn_type": "expense",
        "amount": 40, "txn_date": "2026-08-13", "payee": "Bus",
    })
    client.post("/finance/emis", headers=headers, json={
        "name": "Office chitty", "kind": "chitty", "account_id": bank["id"],
        "amount": 1000, "start_date": "2026-09-01", "end_date": "2027-08-01", "day_of_month": 1,
    })
    client.post(
        "/admin/login",
        data={"email": "webmm@example.com", "password": "password123"},
        follow_redirects=False,
    )
    r = client.get(f"/admin/finance/accounts/{bank['id']}?month=2026-08")
    assert r.status_code == 200, r.text
    assert "Internal Server Error" not in r.text
    assert "Bus" in r.text
    assert "Statement" in r.text
    r = client.get("/admin/finance/recurring")
    assert r.status_code == 200, r.text
    assert "Internal Server Error" not in r.text
    assert "Office chitty" in r.text
    assert "Chitty" in r.text
    r = client.get("/admin/finance/add")
    assert r.status_code == 200, r.text
    assert "Internal Server Error" not in r.text
    assert "Category" in r.text
    r = client.get("/admin/finance/more")
    assert r.status_code == 200, r.text
    assert "Recurring" in r.text
    r = client.get("/admin/finance/trash")
    assert r.status_code == 200, r.text
    assert "Trash" in r.text
    r = client.get("/admin/finance/charts?month=2026-08")
    assert r.status_code == 200, r.text
    assert "Internal Server Error" not in r.text
    assert "Daily flow" in r.text
    assert "Spend heatmap" in r.text
    assert "Amount histogram" in r.text


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
