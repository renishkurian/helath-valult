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
    list_id = lst["id"]

    item = client.post(
        f"/tracker/lists/{list_id}/items",
        headers=headers,
        json={"name": "ulli"},
    )
    assert item.status_code == 201, item.text
    body = item.json()
    assert body["name"]
    assert body["emoji"]
    item_id = body["id"]

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
        json={"name": "Milk", "guest_name": "Asha"},
    )
    assert guest.status_code == 201, guest.text
    assert guest.json()["status"] == "pending"

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

    groups = client.get("/tracker/quick-add", headers=owner)
    assert groups.status_code == 200
    assert groups.json()["groups"]

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
