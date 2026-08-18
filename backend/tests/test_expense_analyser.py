"""Expense Analyser — separate from Money Manager."""
import urllib.error
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


def test_default_sync_query_includes_south_indian_bank():
    from app.gmail import DEFAULT_SYNC_QUERY
    from app.expense_analyser import _effective_sync_query, _looks_like_bank_alert

    assert "southindianbank.com" in DEFAULT_SYNC_QUERY
    assert "sib.bank.in" in DEFAULT_SYNC_QUERY
    assert "sibalerts" in DEFAULT_SYNC_QUERY
    assert "from:alerts@sib.co.in" in DEFAULT_SYNC_QUERY
    assert "Debit Alert" in DEFAULT_SYNC_QUERY
    class _Row:
        sync_query = (
            "("
            "from:(hdfcbank.net OR hdfcbank.com OR sbi.co.in) "
            "OR subject:(transaction OR spent)"
            ") newer_than:45d"
        )
    q = _effective_sync_query(_Row())
    assert "southindianbank.com" in q
    assert "sib.bank.in" in q
    assert "from:alerts@sib.co.in" in q
    assert ")) newer_than" not in q.replace(" ", "")
    assert _looks_like_bank_alert({
        "from_addr": "SIB Alerts <alerts@sib.bank.in>",
        "subject": "Transaction Alert!",
    })
    assert _looks_like_bank_alert({
        "from_addr": "SIB Alerts <alerts@southindianbank.com>",
        "subject": "Transaction Alert!",
    })


def test_list_items_filters_method_and_sorts_by_date():
    from app.expense_analyser import list_items

    headers, email = _headers()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        uid = vault_id(user)
        db.add(models.ExpenseAnalyserItem(
            user_id=uid, gmail_message_id="m-old", kind="alert",
            amount=Decimal("42.00"), payee="HDFC UPI", txn_date="2026-08-10",
            payment_method="upi", status="pending", direction="debit",
        ))
        db.add(models.ExpenseAnalyserItem(
            user_id=uid, gmail_message_id="m-sib", kind="alert",
            amount=Decimal("5775.00"), payee="Jibin S", txn_date="2026-08-17",
            payment_method="upi", status="pending", direction="debit",
        ))
        db.add(models.ExpenseAnalyserItem(
            user_id=uid, gmail_message_id="m-atm", kind="alert",
            amount=Decimal("2000.00"), payee="ATM", txn_date="2026-08-17",
            payment_method="atm", status="pending", direction="debit",
        ))
        db.add(models.ExpenseAnalyserItem(
            user_id=uid, gmail_message_id="m-cc", kind="alert",
            amount=Decimal("1500.00"), payee="Axis", txn_date="2026-08-16",
            payment_method="credit_card", status="pending", direction="debit",
        ))
        db.commit()
        dated = list_items(db, user, statuses=["pending"])
        assert [i.txn_date for i in dated] == ["2026-08-17", "2026-08-17", "2026-08-16", "2026-08-10"]
        upi = list_items(db, user, method="upi")
        assert [i.payee for i in upi] == ["Jibin S", "HDFC UPI"]
        found = list_items(db, user, q="5775")
        assert len(found) == 1 and found[0].payee == "Jibin S"
        day = list_items(db, user, date_from="2026-08-17", date_to="2026-08-17")
        assert {i.payee for i in day} == {"Jibin S", "ATM"}
        from app.expense_analyser import filter_totals
        tot = filter_totals(
            db, user, method="upi", date_from="2026-08-10", date_to="2026-08-17",
        )
        assert tot["debit"] == 5817.0
        assert tot["credit"] == 0
        db.add(models.ExpenseAnalyserItem(
            user_id=uid, gmail_message_id="m-cr", kind="alert",
            amount=Decimal("15000.00"), payee="Salary UPI", txn_date="2026-08-17",
            payment_method="upi", status="pending", direction="credit",
        ))
        db.commit()
        credits = list_items(db, user, method="upi", direction="credit")
        assert [i.payee for i in credits] == ["Salary UPI"]
        debits = list_items(db, user, method="upi", direction="debit")
        assert "Salary UPI" not in [i.payee for i in debits]
        api = client.get("/expense-analyser/items", headers=headers, params={"method": "upi"})
        assert api.status_code == 200
        assert any(abs(float(r["amount"]) - 5775) < 0.01 for r in api.json())
    finally:
        db.close()


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
        assert len(report["daily"]) >= 28
        assert len(report["weekday"]) == 7
        assert report["histogram"]

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


def test_should_run_now_uses_india_day_and_retries_failures():
    from datetime import datetime
    from app.expense_analyser import should_run_now

    row = models.ExpenseAnalyserConnection(
        user_id="sched-tz",
        refresh_token_enc="x",
        enabled=True,
        hour=6,
        last_ok=True,
        # 13:53 UTC 16 Aug = 19:23 IST same calendar day
        last_sync_at=datetime(2026, 8, 16, 13, 53, 0),
    )
    assert should_run_now(row, datetime(2026, 8, 16, 20, 0)) is False
    assert should_run_now(row, datetime(2026, 8, 17, 5, 59)) is False
    assert should_run_now(row, datetime(2026, 8, 17, 6, 1)) is True
    assert should_run_now(row, datetime(2026, 8, 18, 8, 12)) is True

    # UTC evening of 17th is already 18th in India — counts as today's sync
    row.last_sync_at = datetime(2026, 8, 17, 23, 30, 0)
    row.last_ok = True
    assert should_run_now(row, datetime(2026, 8, 18, 8, 12)) is False

    row.last_ok = False
    row.last_sync_at = datetime(2026, 8, 18, 2, 12, 0)  # 07:42 IST
    assert should_run_now(row, datetime(2026, 8, 18, 7, 50)) is False
    assert should_run_now(row, datetime(2026, 8, 18, 8, 15)) is True


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


def test_extract_message_uses_snippet_when_html_is_tiny():
    payload = {
        "id": "m-sib",
        "threadId": "t-sib",
        "snippet": "INR 5775 was spent from your SOUTH INDIAN BANK account XXXXX5835 Info - UPI/SBIN/1/JIBIN S/UPI",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "Debit Alert From SIB"},
                {"name": "From", "value": "SIB Alerts <alerts@sib.co.in>"},
            ],
            "mimeType": "text/html",
            "body": {
                "data": "U291dGggSW5kaWFuIEJhbms=",  # "South Indian Bank"
            },
        },
    }
    mail = extract_message(payload)
    assert "5775" in (mail["text"] or "")
    assert mail["subject"] == "Debit Alert From SIB"


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


def test_post_empty_payee_uses_category_title():
    headers, email = _headers()
    accounts = client.get("/finance/accounts", headers=headers).json()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        uid = vault_id(user)
        item = models.ExpenseAnalyserItem(
            user_id=uid,
            gmail_message_id="g-empty-payee",
            kind="alert",
            subject="INR 90 Spent On Credit Card",
            direction="debit",
            amount=Decimal("90.00"),
            payee="INR 90 Spent On Credit Card",
            txn_date="2026-08-15",
            payment_method="credit_card",
            status="pending",
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        txn = post_to_finance(
            db, user, item.id,
            account_id=accounts[0]["id"],
            new_category="Rent",
            payee="",  # cleared title
        )
        assert txn.payee == "Rent"
        db.refresh(item)
        assert item.payee == "Rent"
    finally:
        db.close()


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


def test_post_custom_payee_overrides_email_title():
    headers, email = _headers()
    accounts = client.get("/finance/accounts", headers=headers).json()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        uid = vault_id(user)
        item = models.ExpenseAnalyserItem(
            user_id=uid,
            gmail_message_id="g-custom-payee",
            kind="alert",
            subject="Email Id Registered With SBI To",
            direction="debit",
            amount=Decimal("500.00"),
            payee="Email Id Registered With SBI To",
            txn_date="2026-08-16",
            payment_method="debit_card",
            status="pending",
        )
        db.add(item)
        db.commit()
        db.refresh(item)
        txn = post_to_finance(
            db, user, item.id,
            account_id=accounts[0]["id"],
            payee="FED ATM",
        )
        assert txn.payee == "FED ATM"
        db.refresh(item)
        assert item.payee == "FED ATM"
        assert item.status == "posted"
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
    assert r.json().get("pending_pdfs") == 0


def _encrypted_pdf(password: str = "secret12") -> bytes:
    from io import BytesIO
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.encrypt(password)
    buf = BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_extract_pdf_parts_from_gmail_payload():
    from app.gmail import extract_pdf_parts

    payload = {
        "id": "m-pdf",
        "payload": {
            "mimeType": "multipart/mixed",
            "parts": [
                {"mimeType": "text/plain", "body": {"data": "SGVsbG8="}},
                {
                    "mimeType": "application/pdf",
                    "filename": "HDFC_eStatement.pdf",
                    "body": {"attachmentId": "att-9", "size": 1200},
                },
            ],
        },
    }
    parts = extract_pdf_parts(payload)
    assert len(parts) == 1
    assert parts[0]["filename"] == "HDFC_eStatement.pdf"
    assert parts[0]["attachment_id"] == "att-9"


def test_gmail_pdf_import_unlocks_with_saved_bank_password(monkeypatch):
    from app import expense_analyser as ea
    from app.database import SessionLocal

    headers, email = _headers()
    saved = client.post("/tracker/passwords", headers=headers, json={
        "identifier": "HDFC", "password": "dob1960", "account_type": "bank",
    })
    assert saved.status_code == 201, saved.text
    raw_pdf = _encrypted_pdf("dob1960")
    payload = {
        "id": "m-pdf-1",
        "threadId": "t-pdf",
        "snippet": "Your e-statement",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "HDFC Bank e-Statement"},
                {"name": "From", "value": "statements@hdfcbank.com"},
            ],
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "application/pdf",
                    "filename": "HDFC_eStatement.pdf",
                    "body": {"attachmentId": "att-pdf", "size": len(raw_pdf)},
                },
            ],
        },
    }

    monkeypatch.setattr("app.gmail.list_message_ids_paged", lambda *a, **k: ["m-pdf-1"])
    monkeypatch.setattr("app.gmail.get_message", lambda *a, **k: payload)
    monkeypatch.setattr("app.gmail.get_attachment_bytes", lambda *a, **k: raw_pdf)

    def fake_parse(file_bytes, filename, password=None):
        assert password == "dob1960"
        return {
            "transactions": [{
                "date": "2026-08-01", "description": "UPI SWIGGY", "amount": 120,
                "type": "debit", "category": "food", "bank_name": "HDFC",
                "account_number": "4521", "account_type": "bank",
                "transaction_id": "gmail-pdf-tx1", "reference_number": None,
            }],
            "parser_used": "FakeParser",
            "account_info": {},
            "summary": {},
        }

    monkeypatch.setattr("app.statement_parsers.parse_statement_file", fake_parse)

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        row = ea.get_or_create(db, user)
        row.refresh_token_enc = "x"
        db.commit()
        result = ea.import_gmail_pdfs(db, user, token="tok")
        assert result["parsed"] == 1
        assert result["created_rows"] == 1
        assert result["needs_password"] == 0
        pdfs = ea.list_mail_pdfs(db, user)
        assert pdfs[0].status == "parsed"
        rows = (
            db.query(models.ShopStatementTxn)
            .filter(models.ShopStatementTxn.user_id == vault_id(user))
            .all()
        )
        assert len(rows) == 1
        assert rows[0].source_file.startswith("mail ·")
        assert rows[0].description == "UPI SWIGGY"
    finally:
        db.close()


def test_gmail_pdf_import_marks_needs_password(monkeypatch):
    from app import expense_analyser as ea
    from app.database import SessionLocal

    headers, email = _headers()
    raw_pdf = _encrypted_pdf("unknown")
    payload = {
        "id": "m-pdf-2",
        "threadId": "t-pdf",
        "snippet": "statement",
        "payload": {
            "headers": [
                {"name": "Subject", "value": "SBI e-Statement"},
                {"name": "From", "value": "estatement@sbi.co.in"},
            ],
            "mimeType": "multipart/mixed",
            "parts": [
                {
                    "mimeType": "application/pdf",
                    "filename": "SBI.pdf",
                    "body": {"attachmentId": "att-2", "size": len(raw_pdf)},
                },
            ],
        },
    }
    monkeypatch.setattr("app.gmail.list_message_ids_paged", lambda *a, **k: ["m-pdf-2"])
    monkeypatch.setattr("app.gmail.get_message", lambda *a, **k: payload)
    monkeypatch.setattr("app.gmail.get_attachment_bytes", lambda *a, **k: raw_pdf)

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        row = ea.get_or_create(db, user)
        row.refresh_token_enc = "x"
        db.commit()
        result = ea.import_gmail_pdfs(db, user, token="tok")
        assert result["needs_password"] == 1
        pdfs = ea.list_mail_pdfs(db, user)
        assert pdfs[0].status == "needs_password"
        st = client.get("/expense-analyser/status", headers=headers).json()
        assert st["pending_pdfs"] == 1

        client.post("/tracker/passwords", headers=headers, json={
            "identifier": "SBI", "password": "unknown", "account_type": "bank",
        })

        def fake_parse(file_bytes, filename, password=None):
            assert password == "unknown"
            return {
                "transactions": [{
                    "date": "2026-08-02", "description": "ATM WDL", "amount": 500,
                    "type": "debit", "category": "cash", "bank_name": "SBI",
                    "account_number": "1001", "account_type": "bank",
                    "transaction_id": "gmail-pdf-tx2", "reference_number": None,
                }],
                "parser_used": "FakeParser",
                "account_info": {},
                "summary": {},
            }

        monkeypatch.setattr("app.statement_parsers.parse_statement_file", fake_parse)
        monkeypatch.setattr("app.expense_analyser._access_token", lambda *a, **k: "tok")
        retried = ea.retry_locked_pdfs(db, user)
        assert retried["parsed"] == 1
        db.refresh(pdfs[0])
        assert pdfs[0].status == "parsed"
    finally:
        db.close()


def test_mail_pdf_download_and_view(monkeypatch):
    from app import expense_analyser as ea
    from app.database import SessionLocal

    headers, email = _headers()
    raw_pdf = b"%PDF-1.4 fake-statement"
    monkeypatch.setattr("app.gmail.get_attachment_bytes", lambda *a, **k: raw_pdf)
    monkeypatch.setattr("app.expense_analyser._access_token", lambda *a, **k: "tok")

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        row = ea.get_or_create(db, user)
        row.refresh_token_enc = "x"
        pdf = models.ShopStatementPdf(
            user_id=user.id,
            gmail_message_id="m-dl-1",
            gmail_attachment_id="att-dl-1",
            filename="HDFC.pdf",
            status="needs_password",
            error="Password-protected PDF",
            bank_hint="HDFC",
        )
        db.add(pdf)
        db.commit()
        db.refresh(pdf)
        pdf_id = pdf.id

        data, name = ea.fetch_mail_pdf_bytes(db, user, pdf_id)
        assert data == raw_pdf
        assert name == "HDFC.pdf"
    finally:
        db.close()

    dl = client.get(f"/expense-analyser/mail-pdfs/{pdf_id}/download", headers=headers)
    assert dl.status_code == 200, dl.text
    assert dl.content == raw_pdf
    assert "attachment" in dl.headers.get("content-disposition", "")
    assert "application/pdf" in dl.headers.get("content-type", "")

    view = client.get(f"/expense-analyser/mail-pdfs/{pdf_id}/view", headers=headers)
    assert view.status_code == 200
    assert "inline" in view.headers.get("content-disposition", "")

    session = TestClient(app)
    login = session.post(
        "/admin/login",
        data={"email": email, "password": "password123"},
        follow_redirects=False,
    )
    assert login.status_code in (302, 303)
    page = session.get("/admin/expense-analyser/statements")
    assert page.status_code == 200
    assert f"/admin/expense-analyser/mail-pdfs/{pdf_id}/view" in page.text
    assert f"/admin/expense-analyser/mail-pdfs/{pdf_id}/download" in page.text
    assert "View" in page.text
    assert "Download" in page.text

    admin_dl = session.get(f"/admin/expense-analyser/mail-pdfs/{pdf_id}/download")
    assert admin_dl.status_code == 200
    assert admin_dl.content == raw_pdf


def test_mail_pdf_fetch_recovers_truncated_attachment_id(monkeypatch):
    from app import expense_analyser as ea
    from app.database import SessionLocal

    full_aid = "A" * 300
    truncated = full_aid[:255]
    raw_pdf = b"%PDF-1.4 recovered"
    calls: list[str] = []

    def fake_get_attachment(_token, _mid, aid):
        calls.append(aid)
        if aid == truncated:
            raise urllib.error.HTTPError(
                url="https://gmail.googleapis.com/x",
                code=400,
                msg="Bad Request",
                hdrs=None,
                fp=None,
            )
        if aid == full_aid:
            return raw_pdf
        raise AssertionError(f"unexpected aid {aid!r}")

    def fake_get_message(_token, mid):
        assert mid == "m-trunc-1"
        return {
            "id": mid,
            "payload": {
                "parts": [{
                    "filename": "SBI.pdf",
                    "mimeType": "application/pdf",
                    "body": {"attachmentId": full_aid, "size": len(raw_pdf)},
                }],
            },
        }

    monkeypatch.setattr("app.gmail.get_attachment_bytes", fake_get_attachment)
    monkeypatch.setattr("app.gmail.get_message", fake_get_message)
    monkeypatch.setattr("app.expense_analyser._access_token", lambda *a, **k: "tok")

    db = SessionLocal()
    try:
        _, email = _headers("ea-trunc-aid@example.com")
        user = db.query(models.User).filter(models.User.email == email).first()
        row = ea.get_or_create(db, user)
        row.refresh_token_enc = "x"
        pdf = models.ShopStatementPdf(
            user_id=user.id,
            gmail_message_id="m-trunc-1",
            gmail_attachment_id=truncated,
            filename="SBI.pdf",
            status="needs_password",
        )
        db.add(pdf)
        db.commit()
        db.refresh(pdf)

        data, name = ea.fetch_mail_pdf_bytes(db, user, pdf.id)
        assert data == raw_pdf
        assert name == "SBI.pdf"
        db.refresh(pdf)
        assert pdf.gmail_attachment_id == full_aid
        assert calls[0] == truncated
        assert full_aid in calls
    finally:
        db.close()


def test_admin_settings_shows_bank_passwords():
    email = "ea-settings-pdf@example.com"
    _headers(email)
    session = TestClient(app)
    login = session.post(
        "/admin/login",
        data={"email": email, "password": "password123"},
        follow_redirects=False,
    )
    assert login.status_code in (302, 303)
    page = session.get("/admin/expense-analyser/settings")
    assert page.status_code == 200, page.text[:500]
    assert "Bank PDF passwords" in page.text
    assert "Bank / label" in page.text
    assert "Internal Server Error" not in page.text


def test_import_pdfs_requires_gmail():
    headers, _ = _headers()
    r = client.post("/expense-analyser/import-pdfs", headers=headers)
    assert r.status_code == 400
    empty = client.get("/expense-analyser/mail-pdfs", headers=headers)
    assert empty.status_code == 200
    assert empty.json() == []
