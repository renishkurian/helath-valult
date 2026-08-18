from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def _headers(email="shop@example.com"):
    r = client.post("/auth/register", json={
        "email": email, "password": "password123", "full_name": "Shop User",
    })
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_tracker_list_item_toggle_and_share():
    headers = _headers()
    summary = client.get("/tracker/summary", headers=headers)
    assert summary.status_code == 200, summary.text
    assert summary.json()["lists"] == 0

    created = client.post("/tracker/lists", headers=headers, json={"name": "saturday market"})
    assert created.status_code == 201, created.text
    lst = created.json()
    assert lst["name"] == "Saturday Market"
    assert lst.get("owner_name") == "Shop User"
    assert lst.get("created_at")
    list_id = lst["id"]

    item = client.post(
        f"/tracker/lists/{list_id}/items",
        headers=headers,
        json={"name": "ulli"},
    )
    assert item.status_code == 201, item.text
    body = item.json()
    assert "Onion" in body["name"]
    assert "ഉള്ളി" in body["name"]
    assert body["emoji"]
    assert body.get("added_by_name") == "Shop User"
    item_id = body["id"]

    edited = client.patch(
        f"/tracker/lists/{list_id}/items/{item_id}",
        headers=headers,
        json={"quantity": 2, "unit": "kg"},
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["quantity"] == 2
    assert edited.json()["unit"] == "kg"

    toggled = client.post(f"/tracker/lists/{list_id}/items/{item_id}/toggle", headers=headers)
    assert toggled.status_code == 200
    assert toggled.json()["checked"] is True

    share = client.post(f"/tracker/lists/{list_id}/share", headers=headers)
    assert share.status_code == 200, share.text
    token = share.json()["token"]
    assert token

    public = client.get(f"/tracker/shared/{token}")
    assert public.status_code == 200
    assert public.json()["name"] == "Saturday Market"

    guest = client.post(
        f"/tracker/shared/{token}/items",
        json={"name": "Milk", "guest_name": "renish"},
    )
    assert guest.status_code == 201, guest.text
    assert guest.json()["status"] == "pending"
    assert guest.json()["added_by_name"] == "Renish"

    detail = client.get(f"/tracker/lists/{list_id}", headers=headers).json()
    assert detail["pending_count"] == 1
    pending_id = next(i["id"] for i in detail["items"] if i["status"] == "pending")
    approved = client.post(f"/tracker/lists/{list_id}/items/{pending_id}/approve", headers=headers)
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"


def test_tracker_recognize_and_friends_send():
    owner = _headers("owner-shop@example.com")
    other = _headers("friend-shop@example.com")

    rec = client.post("/tracker/recognize", headers=owner, json={"name": "paal"})
    assert rec.status_code == 200, rec.text
    assert rec.json()["english"] == "Milk"
    assert rec.json()["malayalam"]
    assert rec.json()["matched"] is True

    brinjal = client.post("/tracker/recognize", headers=owner, json={"name": "vazhuth"})
    assert brinjal.status_code == 200, brinjal.text
    assert brinjal.json()["english"] == "Brinjal"
    assert "വാഴുതന" in (brinjal.json()["malayalam"] or "")

    hits = client.get("/tracker/suggest", headers=owner, params={"q": "vazhuth"})
    assert hits.status_code == 200, hits.text
    assert any(row["english"] == "Brinjal" for row in hits.json())

    typo = client.post("/tracker/recognize", headers=owner, json={"name": "brinjl"})
    assert typo.status_code == 200, typo.text
    assert typo.json()["english"] == "Brinjal"
    assert typo.json()["matched"] is True

    groups = client.get("/tracker/quick-add", headers=owner)
    assert groups.status_code == 200
    payload = groups.json()["groups"]
    assert payload
    assert payload[0]["entries"]

    friend = client.post("/tracker/friends", headers=owner, json={
        "name": "Asha", "email": "friend-shop@example.com", "relation": "family",
    })
    assert friend.status_code == 201, friend.text

    lst = client.post("/tracker/lists", headers=owner, json={"name": "Fish run"}).json()
    client.post(f"/tracker/lists/{lst['id']}/items", headers=owner, json={"name": "meen"})
    sent = client.post(
        f"/tracker/lists/{lst['id']}/send",
        headers=owner,
        json={"email": "friend-shop@example.com", "message": "please pick up"},
    )
    assert sent.status_code == 200, sent.text
    send_id = sent.json()["id"]

    inbox = client.get("/tracker/inbox", headers=other).json()
    assert len(inbox) == 1
    assert inbox[0]["id"] == send_id

    accepted = client.post(f"/tracker/inbox/{send_id}/accept", headers=other)
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["item_count"] >= 1

    copied = client.get("/tracker/lists", headers=other).json()
    assert any(x["name"] == "Fish Run" for x in copied)


def test_tracker_pdf_password_roundtrip():
    headers = _headers("pdf-shop@example.com")
    saved = client.post("/tracker/passwords", headers=headers, json={
        "identifier": "SBI 4521", "password": "secret12", "account_type": "credit_card",
        "last_4_digits": "4521",
    })
    assert saved.status_code == 201, saved.text
    listed = client.get("/tracker/passwords", headers=headers).json()
    assert listed[0]["identifier"] == "SBI 4521"
    assert "password" not in listed[0]
    gone = client.delete(f"/tracker/passwords/{listed[0]['id']}", headers=headers)
    assert gone.status_code == 204
    assert client.get("/tracker/passwords", headers=headers).json() == []

    again = client.post("/tracker/passwords", headers=headers, json={
        "identifier": "HDFC", "password": "first", "account_type": "bank",
    })
    assert again.status_code == 201
    updated = client.post("/tracker/passwords", headers=headers, json={
        "identifier": "HDFC", "password": "second", "account_type": "credit_card",
        "last_4_digits": "8899",
    })
    assert updated.status_code == 201
    listed = client.get("/tracker/passwords", headers=headers).json()
    assert len(listed) == 1
    assert listed[0]["identifier"] == "HDFC"
    assert listed[0]["account_type"] == "credit_card"
    assert listed[0]["last_4_digits"] == "8899"


def test_admin_list_detail_renders_quick_add():
    email = "shop-admin@example.com"
    headers = _headers(email)
    created = client.post("/tracker/lists", headers=headers, json={"name": "Market"}).json()
    session = TestClient(app)
    login = session.post(
        "/admin/login",
        data={"email": email, "password": "password123"},
        follow_redirects=False,
    )
    assert login.status_code in (302, 303)
    page = session.get(f"/admin/tracker/lists/{created['id']}")
    assert page.status_code == 200, page.text[:500]
    assert "Market" in page.text
    assert "Quick add" in page.text
    assert "Potato" in page.text
    assert "ഉള്ളി" in page.text
    assert "Use AI (Malayalam" in page.text
    assert 'id="shop-catalog-data"' in page.text
    assert 'data-suggest="/admin/tracker/suggest"' in page.text
    assert "shop-list.js?v=7" in page.text
    assert "shop-chip-section" in page.text
    assert "shop-chip-heading" in page.text
    assert "Internal Server Error" not in page.text
    assert "Live" in page.text
    assert "app-tabbar" in page.text
    assert "has-composer" in page.text
    assert "Add bill copy" in page.text
    assert "Open statements" not in page.text
    assert "Family on this list" not in page.text

    suggest = session.get("/admin/tracker/suggest", params={"q": "vazhuth"})
    assert suggest.status_code == 200, suggest.text
    assert any(row.get("english") == "Brinjal" for row in suggest.json())


def test_admin_toggle_item_json_skips_redirect():
    email = "shop-toggle@example.com"
    headers = _headers(email)
    created = client.post("/tracker/lists", headers=headers, json={"name": "Market"}).json()
    item = client.post(
        f"/tracker/lists/{created['id']}/items",
        headers=headers,
        json={"name": "Milk"},
    ).json()
    session = TestClient(app)
    login = session.post(
        "/admin/login",
        data={"email": email, "password": "password123"},
        follow_redirects=False,
    )
    assert login.status_code in (302, 303)
    page = session.get(f"/admin/tracker/lists/{created['id']}")
    assert page.status_code == 200
    assert "js-shop-toggle" in page.text

    toggled = session.post(
        f"/admin/tracker/lists/{created['id']}/items/{item['id']}/toggle",
        headers={"Accept": "application/json", "X-Requested-With": "fetch"},
        follow_redirects=False,
    )
    assert toggled.status_code == 200, toggled.text
    body = toggled.json()
    assert body["ok"] is True
    assert body["checked"] is True
    assert body["checked_count"] == 1
    assert body["item_count"] >= 1
    assert body["revision"]

    fallback = session.post(
        f"/admin/tracker/lists/{created['id']}/items/{item['id']}/toggle",
        follow_redirects=False,
    )
    assert fallback.status_code in (302, 303)
    assert f"/admin/tracker/lists/{created['id']}" in fallback.headers.get("location", "")


def test_family_share_auto_approves_and_polls_revision():
    headers = _headers("fam-live@example.com")
    lst = client.post("/tracker/lists", headers=headers, json={"name": "Sunday market"}).json()
    share = client.post(f"/tracker/lists/{lst['id']}/share", headers=headers)
    assert share.status_code == 200, share.text
    token = share.json()["token"]

    family = client.post(
        f"/tracker/shared/{token}/items",
        json={"name": "Milk", "guest_name": "Shop User"},
    )
    assert family.status_code == 201, family.text
    assert family.json()["status"] == "approved"

    guest = client.post(
        f"/tracker/shared/{token}/items",
        json={"name": "Eggs", "guest_name": "Neighbour"},
    )
    assert guest.status_code == 201, guest.text
    assert guest.json()["status"] == "pending"

    live = client.get(f"/tracker/shared/{token}")
    assert live.status_code == 200, live.text
    body = live.json()
    assert body["revision"]
    assert "Shop User" in body["members"]
    names = [i["name"] for i in body["items"]]
    assert any("Milk" in n for n in names)

    page = client.get(f"/tracker/public/{token}/page")
    assert page.status_code == 200, page.text[:500]
    assert "Sunday Market" in page.text
    assert "public-app" in page.text
    assert "shop-composer" in page.text
    assert "shop-member-bar" not in page.text
    assert "js-shop-edit" in page.text
    assert "js-shop-toggle" in page.text
    assert "Internal Server Error" not in page.text

    milk = next(i for i in body["items"] if "Milk" in i["name"])
    toggled = client.post(
        f"/tracker/public/{token}/items/{milk['id']}/toggle",
        headers={"Accept": "application/json", "X-Requested-With": "fetch"},
        follow_redirects=False,
    )
    assert toggled.status_code == 200, toggled.text
    out = toggled.json()
    assert out["ok"] is True
    assert out["checked"] is True
    assert out["revision"]


def test_admin_statements_moved_to_expense_analyser():
    email = "pdf-move@example.com"
    _headers(email)
    session = TestClient(app)
    login = session.post(
        "/admin/login",
        data={"email": email, "password": "password123"},
        follow_redirects=False,
    )
    assert login.status_code in (302, 303)
    bounced = session.get("/admin/tracker/statements", follow_redirects=False)
    assert bounced.status_code in (302, 303)
    assert "/admin/expense-analyser/statements" in bounced.headers.get("location", "")
    page = session.get("/admin/expense-analyser/statements")
    assert page.status_code == 200, page.text[:500]
    assert "Bank statements" in page.text
    assert "Expense Analyser" in page.text
    assert "Bank PDF passwords" in page.text
    assert "Bank / label" in page.text
    assert "Load PDFs from Gmail" not in page.text  # Gmail not connected
    assert "Internal Server Error" not in page.text


def test_shop_list_bill_copy_upload():
    headers = _headers("bill-copy@example.com")
    lst = client.post("/tracker/lists", headers=headers, json={"name": "Market"}).json()
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"
        b"\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    up = client.post(
        f"/tracker/lists/{lst['id']}/receipts",
        headers=headers,
        files={"file": ("bill.png", png, "image/png")},
    )
    assert up.status_code == 201, up.text
    rec = up.json()
    assert rec["is_image"] is True
    detail = client.get(f"/tracker/lists/{lst['id']}", headers=headers).json()
    assert detail["receipt_count"] == 1
    img = client.get(f"/tracker/lists/{lst['id']}/receipts/{rec['id']}/image", headers=headers)
    assert img.status_code == 200
    assert img.content
    gone = client.delete(f"/tracker/lists/{lst['id']}/receipts/{rec['id']}", headers=headers)
    assert gone.status_code == 204
    assert client.get(f"/tracker/lists/{lst['id']}", headers=headers).json()["receipt_count"] == 0


def test_tracker_add_duplicate_merges_quantity():
    import uuid

    headers = _headers(f"shop-merge-{uuid.uuid4().hex[:8]}@example.com")
    list_id = client.post("/tracker/lists", headers=headers, json={"name": "Merge test"}).json()["id"]
    first = client.post(
        f"/tracker/lists/{list_id}/items",
        headers=headers,
        json={"name": "ulli", "quantity": 1},
    )
    assert first.status_code == 201, first.text
    assert first.json().get("merged") is False
    item_id = first.json()["id"]
    qty1 = first.json()["quantity"]

    second = client.post(
        f"/tracker/lists/{list_id}/items",
        headers=headers,
        json={"name": "onion", "quantity": 2},
    )
    assert second.status_code == 201, second.text
    assert second.json()["id"] == item_id
    assert second.json().get("merged") is True
    assert second.json()["quantity"] == qty1 + 2

    again = client.post(
        f"/tracker/lists/{list_id}/items",
        headers=headers,
        json={"name": "ulli", "quantity": 1},
    )
    assert again.json()["id"] == item_id
    assert again.json()["merged"] is True

    detail = client.get(f"/tracker/lists/{list_id}", headers=headers).json()
    assert detail["item_count"] == 1
    assert detail["items"][0]["quantity"] == qty1 + 3

def test_tracker_list_moves_to_trash():
    import uuid

    email = f"shop-trash-{uuid.uuid4().hex[:8]}@example.com"
    headers = _headers(email)
    created = client.post("/tracker/lists", headers=headers, json={"name": "Dealer"}).json()
    list_id = created["id"]
    client.post(f"/tracker/lists/{list_id}/items", headers=headers, json={"name": "milk"})

    gone = client.delete(f"/tracker/lists/{list_id}", headers=headers)
    assert gone.status_code == 204
    assert client.get(f"/tracker/lists/{list_id}", headers=headers).status_code == 404
    assert all(x["id"] != list_id for x in client.get("/tracker/lists", headers=headers).json())

    trash = client.get("/tracker/trash", headers=headers)
    assert trash.status_code == 200, trash.text
    assert any(x["id"] == list_id for x in trash.json())
    assert trash.json()[0]["deleted_at"]

    restored = client.post(f"/tracker/lists/{list_id}/restore", headers=headers)
    assert restored.status_code == 200, restored.text
    assert restored.json()["deleted_at"] is None
    assert client.get(f"/tracker/lists/{list_id}", headers=headers).status_code == 200

    client.delete(f"/tracker/lists/{list_id}", headers=headers)
    perm = client.delete(f"/tracker/lists/{list_id}/permanent", headers=headers)
    assert perm.status_code == 204
    assert client.get("/tracker/trash", headers=headers).json() == []

    again = client.post("/tracker/lists", headers=headers, json={"name": "Again"}).json()
    client.delete(f"/tracker/lists/{again['id']}", headers=headers)
    session = TestClient(app)
    login = session.post(
        "/admin/login",
        data={"email": email, "password": "password123"},
        follow_redirects=False,
    )
    assert login.status_code in (302, 303)
    page = session.get("/admin/tracker")
    assert page.status_code == 200
    assert "Move to trash" in page.text or "bi-trash3" in page.text
    trash_page = session.get("/admin/tracker/trash")
    assert trash_page.status_code == 200
    assert "Again" in trash_page.text
    assert "Restore" in trash_page.text


def test_post_completed_list_to_finance():
    import uuid
    email = f"shop-mm-{uuid.uuid4().hex[:8]}@example.com"
    headers = _headers(email)

    accounts = client.get("/finance/accounts", headers=headers)
    assert accounts.status_code == 200, accounts.text
    rows = accounts.json()
    if rows:
        account_id = rows[0]["id"]
    else:
        acc = client.post("/finance/accounts", headers=headers, json={
            "name": "Home", "account_type": "cash", "opening_balance": 0,
        })
        assert acc.status_code in (200, 201), acc.text
        account_id = acc.json()["id"]

    cats = client.get("/finance/categories", headers=headers).json()
    groceries = next(c for c in cats if c["name"] == "Groceries" and c["kind"] == "expense")

    lst = client.post("/tracker/lists", headers=headers, json={
        "name": "Sunday market",
        "finance_category_id": groceries["id"],
    }).json()
    assert lst["finance_category_id"] == groceries["id"]
    assert lst["finance_category_name"] == "Groceries"
    list_id = lst["id"]
    item = client.post(
        f"/tracker/lists/{list_id}/items",
        headers=headers,
        json={"name": "Onion", "quantity": 2, "unit": "kg", "price": 30},
    ).json()
    client.post(f"/tracker/lists/{list_id}/items/{item['id']}/toggle", headers=headers)
    client.patch(f"/tracker/lists/{list_id}", headers=headers, json={"completed": True})

    posted = client.post(
        f"/tracker/lists/{list_id}/post-finance",
        headers=headers,
        json={"account_id": account_id, "category_id": groceries["id"]},
    )
    assert posted.status_code == 200, posted.text
    body = posted.json()
    assert body["ok"] is True
    assert body["amount"] == 60.0
    assert body["category_id"] == groceries["id"]

    detail = client.get(f"/tracker/lists/{list_id}", headers=headers).json()
    assert detail["finance_txn_id"] == body["finance_txn_id"]
    assert detail["completed"] is True

    again = client.post(
        f"/tracker/lists/{list_id}/post-finance",
        headers=headers,
        json={"account_id": account_id},
    )
    assert again.status_code == 400

    txns = client.get("/finance/transactions", headers=headers)
    assert txns.status_code == 200
    match = next(t for t in txns.json() if t["id"] == body["finance_txn_id"])
    assert match["category_id"] == groceries["id"]
    assert match["account_id"] == account_id
