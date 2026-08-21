"""Secret Share module + first-browser bind."""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def _register(email: str, password: str = "password123", name: str = "Secret User"):
    r = client.post("/auth/register", json={"email": email, "password": password, "full_name": name})
    assert r.status_code == 201, r.text
    return r.json()


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_secret_share_create_and_public_view():
    data = _register("secretshare@example.com")
    headers = _auth_headers(data["access_token"])

    created = client.post("/secrets/sends", json={
        "name": "Guest WiFi",
        "text": "wifi-pass-42",
        "expires_in_hours": 2,
    }, headers=headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["send_type"] == "secret"
    assert body["bind_first_browser"] is False
    token = body["token"]

    listed = client.get("/secrets/sends", headers=headers)
    assert listed.status_code == 200
    assert any(s["token"] == token for s in listed.json())

    page = client.get(f"/vault/public/{token}/page")
    assert page.status_code == 200
    assert b"wifi-pass-42" in page.content
    assert b"Secret Share" in page.content


def test_secret_share_first_browser_bind_blocks_other_client():
    data = _register("browserbind@example.com")
    headers = _auth_headers(data["access_token"])

    created = client.post("/secrets/sends", json={
        "name": "Bound secret",
        "text": "only-chrome",
        "expires_in_hours": 6,
        "bind_first_browser": True,
    }, headers=headers)
    assert created.status_code == 201, created.text
    assert created.json()["bind_first_browser"] is True
    token = created.json()["token"]

    chrome = TestClient(app)
    first = chrome.get(
        f"/vault/public/{token}/page",
        headers={"User-Agent": "Mozilla/5.0 Chrome/120"},
    )
    assert first.status_code == 200
    assert b"only-chrome" in first.content
    assert "vsbb_" in "".join(chrome.cookies.keys()) or any(
        k.startswith("vsbb_") for k in chrome.cookies.keys()
    )

    firefox = TestClient(app)
    second = firefox.get(
        f"/vault/public/{token}/page",
        headers={"User-Agent": "Mozilla/5.0 Firefox/121"},
    )
    assert second.status_code == 200
    assert b"only-chrome" not in second.content
    assert b"locked to another browser" in second.content

    again = chrome.get(
        f"/vault/public/{token}/page",
        headers={"User-Agent": "Mozilla/5.0 Chrome/120"},
    )
    assert again.status_code == 200
    assert b"only-chrome" in again.content

    reqs = client.get("/secrets/send-requests?status=all", headers=headers)
    assert reqs.status_code == 200
    blocked = [r for r in reqs.json() if r["status"] == "blocked"]
    assert len(blocked) >= 1
