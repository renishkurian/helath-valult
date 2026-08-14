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
    assert body.get("syncing") is False


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
        shop = db.query(models.FinanceCategory).filter_by(id=txn.category_id).first()
        assert shop is None or shop.name == "Shopping"
    finally:
        db.close()

    r = client.get("/expense-analyser/items?status=posted", headers=headers)
    assert r.status_code == 200
    assert any(i["payee"] == "AMAZON PAY" for i in r.json())
    r = client.get("/expense-analyser/items?statuses=posted,pending", headers=headers)
    assert r.status_code == 200
    assert any(i["payee"] == "AMAZON PAY" for i in r.json())


def test_post_creates_category_and_subcategory():
    headers, email = _headers()
    accounts = client.get("/finance/accounts", headers=headers).json()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        uid = vault_id(user)
        item = models.ExpenseAnalyserItem(
            user_id=uid,
            gmail_message_id="g-newcat",
            kind="alert",
            direction="debit",
            amount=Decimal("99.00"),
            payee="LOCAL CAFE",
            txn_date="2026-08-14",
            payment_method="upi",
            suggested_category="Food & dining",
            status="pending",
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        txn = post_to_finance(
            db, user, item.id,
            account_id=accounts[0]["id"],
            new_category="Eating out",
            new_subcategory="Cafe",
        )
        cat = db.query(models.FinanceCategory).filter_by(id=txn.category_id).first()
        assert cat is not None
        assert cat.name == "Cafe"
        parent = db.query(models.FinanceCategory).filter_by(id=cat.parent_id).first()
        assert parent is not None
        assert parent.name == "Eating out"
        db.refresh(item)
        assert item.suggested_category == "Eating out / Cafe"
    finally:
        db.close()


def test_clear_inbox_removes_all_items():
    headers, email = _headers()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        uid = vault_id(user)
        for i, status in enumerate(("pending", "corrected", "posted", "ignored")):
            db.add(models.ExpenseAnalyserItem(
                user_id=uid,
                gmail_message_id=f"clear-{i}",
                kind="alert",
                direction="debit",
                amount=Decimal("10.00"),
                payee=f"Payee {i}",
                txn_date="2026-08-14",
                status=status,
            ))
        db.commit()
        assert db.query(models.ExpenseAnalyserItem).filter_by(user_id=uid).count() == 4
    finally:
        db.close()

    r = client.post("/expense-analyser/clear", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] == 4
    assert client.get("/expense-analyser/items", headers=headers).json() == []
    assert client.get("/expense-analyser/status", headers=headers).json()["pending"] == 0


def test_paginate_helper():
    from app.paging import paginate
    p = paginate(page=2, per_page=25, total=124)
    assert p["page"] == 2
    assert p["pages"] == 5
    assert p["offset"] == 25
    assert p["start"] == 26
    assert p["end"] == 50
    assert p["has_prev"] and p["has_next"]
    p = paginate(page=99, per_page=25, total=10)
    assert p["page"] == 1
    assert p["has_prev"] is False
    assert p["has_next"] is False


def test_known_gmail_ids_and_sync_busy_flag():
    from app.expense_analyser import (
        _known_gmail_ids, _is_syncing, _mark_syncing, start_sync_background,
        _is_retagging, _mark_retagging, start_retag_background,
    )

    headers, email = _headers()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        uid = vault_id(user)
        db.add(models.ExpenseAnalyserItem(
            user_id=uid, gmail_message_id="already-there", kind="alert",
            direction="debit", status="pending",
        ))
        db.commit()
        assert "already-there" in _known_gmail_ids(db, uid)
        _mark_syncing(uid, True)
        assert _is_syncing(uid) is True
        assert start_sync_background(uid) is False
        assert start_retag_background(uid) is False
        _mark_syncing(uid, False)
        assert _is_syncing(uid) is False

        _mark_retagging(uid, True)
        assert _is_retagging(uid) is True
        assert start_retag_background(uid) is False
        assert start_sync_background(uid) is False
        _mark_retagging(uid, False)
        assert _is_retagging(uid) is False
    finally:
        db.close()


def test_retag_accepts_item_ids():
    from app.expense_analyser import retag_pending_items
    from decimal import Decimal

    headers, email = _headers()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        uid = vault_id(user)
        keep = models.ExpenseAnalyserItem(
            user_id=uid, gmail_message_id="retag-keep", kind="alert",
            direction="debit", amount=Decimal("30.00"), payee="VJ BIJI",
            suggested_category="Insurance", status="pending",
            raw_snippet="Rs.30.00 debited towards VPA sviji795@oksbi (VJ BIJI). Please click here.",
        )
        skip = models.ExpenseAnalyserItem(
            user_id=uid, gmail_message_id="retag-skip", kind="alert",
            direction="debit", amount=Decimal("99.00"), payee="OTHER",
            suggested_category="Insurance", status="pending",
            raw_snippet="Rs.99.00 debited towards VPA otherperson@oksbi (OTHER). click here.",
        )
        db.add_all([keep, skip])
        db.commit()
        db.refresh(keep)
        db.refresh(skip)
        result = retag_pending_items(db, user, use_ai=False, item_ids=[keep.id])
        assert result["scanned"] == 1
        db.refresh(keep)
        db.refresh(skip)
        assert keep.suggested_category == "UPI / transfers"
        assert skip.suggested_category == "Insurance"
    finally:
        db.close()


def test_retag_skips_corrected_unless_forced():
    from app.expense_analyser import retag_pending_items
    from decimal import Decimal

    headers, email = _headers()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        uid = vault_id(user)
        pending = models.ExpenseAnalyserItem(
            user_id=uid, gmail_message_id="retag-new", kind="alert",
            direction="debit", amount=Decimal("30.00"), payee="VJ BIJI",
            suggested_category="Insurance", status="pending",
            raw_snippet="Rs.30.00 debited towards VPA sviji795@oksbi (VJ BIJI). Please click here.",
        )
        already = models.ExpenseAnalyserItem(
            user_id=uid, gmail_message_id="retag-done", kind="alert",
            direction="debit", amount=Decimal("30.00"), payee="VJ BIJI",
            suggested_category="UPI / transfers", status="corrected",
            raw_snippet="Rs.30.00 debited towards VPA sviji795@oksbi (VJ BIJI). Please click here.",
        )
        db.add_all([pending, already])
        db.commit()
        db.refresh(pending)
        db.refresh(already)

        skipped = retag_pending_items(db, user, use_ai=False, force=False)
        assert skipped["scanned"] == 1
        db.refresh(already)
        assert already.status == "corrected"
        assert already.suggested_category == "UPI / transfers"

        forced = retag_pending_items(db, user, use_ai=False, force=True)
        assert forced["scanned"] == 2
    finally:
        db.close()


def test_status_includes_retagging_flag():
    headers, _ = _headers()
    r = client.get("/expense-analyser/status", headers=headers)
    assert r.status_code == 200
    assert r.json().get("retagging") is False
