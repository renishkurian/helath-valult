"""Expense Analyser — separate from Money Manager."""
import uuid
from decimal import Decimal

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app import models
from app.expense_analyser import _parse_bill_lines, _find_ledger_match, post_to_finance
from app.gmail import html_to_text, looks_like_statement, extract_message
from app.main import app
from app.deps import vault_id

client = TestClient(app)


def _headers(email: str | None = None):
    email = email or f"analyser-{uuid.uuid4().hex[:10]}@example.com"
    r = client.post("/auth/register", json={
        "email": email, "password": "password123", "full_name": "Analyser User",
    })
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, email


def test_status_endpoint_unconnected():
    headers, _ = _headers()
    r = client.get("/expense-analyser/status", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["connected"] is False
    assert body["pending"] == 0
    assert "sync_query" in body
    assert body["enabled"] is False
    assert body["hour"] == 6


def test_schedule_and_insights():
    from app.expense_analyser import should_run_now, insights
    from datetime import datetime

    headers, email = _headers()
    r = client.put("/expense-analyser/schedule", headers=headers, json={"enabled": True, "hour": 7})
    assert r.status_code == 200, r.text
    # Without Gmail connected, enabled stays false
    assert r.json()["enabled"] is False
    assert r.json()["hour"] == 7

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        uid = vault_id(user)
        db.add(models.ExpenseAnalyserItem(
            user_id=uid, gmail_message_id="g-ins", kind="alert",
            direction="debit", amount=Decimal("250.00"), payee="SWIGGY",
            txn_date=datetime.utcnow().strftime("%Y-%m-%d"),
            payment_method="upi", suggested_category="Food & dining",
            status="pending",
        ))
        db.commit()
        report = insights(db, user)
        assert report["debit_total"] >= 250
        assert any(s["name"] == "Food & dining" for s in report["by_category"])

        row = models.ExpenseAnalyserConnection(
            user_id=uid, refresh_token_enc="x", enabled=True, hour=0,
            last_sync_at=None, last_ok=None,
        )
        # may already exist from schedule call
        existing = db.query(models.ExpenseAnalyserConnection).filter_by(user_id=uid).first()
        if existing:
            existing.refresh_token_enc = "x"
            existing.enabled = True
            existing.hour = 0
            existing.last_sync_at = None
            existing.last_ok = None
            db.commit()
            row = existing
        else:
            db.add(row)
            db.commit()
        assert should_run_now(row, datetime.now()) is True
    finally:
        db.close()

    r = client.get("/expense-analyser/insights", headers=headers)
    assert r.status_code == 200
    assert "debit_total" in r.json()


def test_html_to_text_and_statement_detect():
    html = "<html><body><p>Your <b>credit card statement</b> is ready<br>Rs.120.00</p></body></html>"
    text = html_to_text(html)
    assert "credit card statement" in text.lower()
    assert looks_like_statement("HDFC e-Statement", text)
    # Alert footers mentioning "statement" must NOT force the bill path.
    assert not looks_like_statement(
        "You have done a UPI txn. Check details!",
        "View your credit card statement online. Available Credit Limit Rs.50000",
    )


def test_extract_message_pending_attachment():
    payload = {
        "id": "m2",
        "threadId": "t2",
        "snippet": "You have done a UPI txn",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "You have done a UPI txn. Check details!"},
                {"name": "From", "value": "alerts@hdfcbank.com"},
            ],
            "mimeType": "text/html",
            "body": {"attachmentId": "att-1", "size": 120},
        },
    }
    mail = extract_message(payload)
    assert mail["pending_attachments"] == [("text/html", "att-1")]
    assert "UPI txn" in (mail["snippet"] or "")


def test_best_txn_date_prefers_gmail_when_body_is_stale():
    from datetime import datetime
    from app.expense_analyser import _best_txn_date

    mail = {"received_at": datetime(2026, 8, 14, 17, 40)}
    assert _best_txn_date({"date": "2026-08-05"}, mail, kind="alert") == "2026-08-14"
    assert _best_txn_date({"date": "2026-08-14"}, mail, kind="alert") == "2026-08-14"
    assert _best_txn_date({"txn_date": "2026-08-05"}, mail, kind="bill_line") == "2026-08-05"


def test_extract_message_plain():
    payload = {
        "id": "m1",
        "threadId": "t1",
        "snippet": "debited",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "UPI alert"},
                {"name": "From", "value": "alerts@hdfcbank.net"},
            ],
            "mimeType": "text/plain",
            "body": {
                # base64url of "Dear Customer, Rs.100.00 debited"
                "data": "RGVhciBDdXN0b21lciwgUnMuMTAwLjAwIGRlYml0ZWQ",
            },
        },
    }
    mail = extract_message(payload)
    assert mail["id"] == "m1"
    assert mail["subject"] == "UPI alert"
    assert "100" in mail["text"]


def test_bill_line_parse_and_post_bridge():
    text = (
        "Credit Card Statement\n"
        "12-08-2026  Rs.450.00  SWIGGY BANGALORE\n"
        "13-08-2026  Rs.1,200.50  AMAZON PAY\n"
    )
    lines = _parse_bill_lines(text)
    assert len(lines) >= 2
    assert lines[0]["amount"] == 450
    assert lines[0]["kind"] == "bill_line"

    headers, email = _headers()
    accounts = client.get("/finance/accounts", headers=headers).json()
    assert accounts

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        acc = accounts[0]
        client.post("/finance/transactions", headers=headers, json={
            "account_id": acc["id"],
            "txn_type": "expense",
            "amount": 450,
            "txn_date": "2026-08-12",
            "payee": "SWIGGY",
        })
        uid = vault_id(user)
        match = _find_ledger_match(db, uid, amount=450, txn_date="2026-08-12", payee="SWIGGY")
        assert match is not None

        item = models.ExpenseAnalyserItem(
            user_id=uid,
            gmail_message_id="g1",
            kind="bill_line",
            subject="Statement",
            direction="debit",
            amount=Decimal("1200.50"),
            payee="AMAZON PAY",
            txn_date="2026-08-13",
            payment_method="credit_card",
            suggested_category="Shopping",
            status="missed",
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        txn = post_to_finance(db, user, item.id, account_id=acc["id"])
        assert txn.id
        db.refresh(item)
        assert item.status == "posted"
        assert item.finance_txn_id == txn.id
    finally:
        db.close()

    r = client.get("/expense-analyser/items?status=posted", headers=headers)
    assert r.status_code == 200
    assert any(i["payee"] == "AMAZON PAY" for i in r.json())
