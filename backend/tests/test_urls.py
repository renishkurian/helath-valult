from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def _headers(email="urls@example.com"):
    r = client.post("/auth/register", json={
        "email": email, "password": "password123", "full_name": "URL User",
    })
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_url_crud_search_categories_tags_and_share():
    headers = _headers()

    summary = client.get("/urls/summary", headers=headers)
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["total"] == 0
    names = [c["name"] for c in body["categories"]]
    assert "Instagram" in names and "News" in names and "Songs" in names and "Adult" in names
    news_id = next(c["id"] for c in body["categories"] if c["name"] == "News")
    music_id = next(t["id"] for t in body["tags"] if t["name"] == "music")

    created_cat = client.post("/urls/categories", headers=headers, json={"name": "Dev", "color": "#22D3EE"})
    assert created_cat.status_code == 201, created_cat.text
    dev_id = created_cat.json()["id"]

    created_tag = client.post("/urls/tags", headers=headers, json={"name": "tutorial"})
    assert created_tag.status_code == 201, created_tag.text
    tutorial_id = created_tag.json()["id"]

    r = client.post("/urls", headers=headers, json={
        "url": "example.com/article",
        "title": "Example news",
        "category_id": news_id,
        "tag_ids": [music_id, tutorial_id],
        "notes": "read later",
        "fetch_preview": False,
    })
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["title"] == "Example news"
    assert item["url"] == "https://example.com/article"
    assert item["category_name"] == "News"
    assert item["notes"] == "read later"
    assert {t["name"] for t in item["tags"]} == {"music", "tutorial"}
    item_id = item["id"]

    listed = client.get("/urls", headers=headers).json()
    assert len(listed) == 1
    by_cat = client.get("/urls", headers=headers, params={"category_id": news_id}).json()
    assert len(by_cat) == 1
    by_tag = client.get("/urls", headers=headers, params={"tag_id": tutorial_id}).json()
    assert len(by_tag) == 1
    search = client.get("/urls", headers=headers, params={"q": "example"}).json()
    assert len(search) == 1
    miss = client.get("/urls", headers=headers, params={"q": "nope"}).json()
    assert miss == []

    patch = client.patch(f"/urls/{item_id}", headers=headers, json={
        "title": "Renamed", "category_id": dev_id, "favorite": True, "fetch_preview": False,
    })
    assert patch.status_code == 200, patch.text
    assert patch.json()["title"] == "Renamed"
    assert patch.json()["category_name"] == "Dev"
    assert patch.json()["favorite"] is True

    fav = client.get("/urls", headers=headers, params={"favorite": True}).json()
    assert len(fav) == 1

    share = client.post(f"/urls/{item_id}/share", headers=headers, json={"expires_in_hours": 24})
    assert share.status_code == 201, share.text
    token = share.json()["token"]
    public = client.get(f"/urls/public/{token}")
    assert public.status_code == 200
    assert public.json()["title"] == "Renamed"
    page = client.get(f"/u/{token}", follow_redirects=True)
    assert page.status_code == 200
    assert b"Renamed" in page.content

    client.post(f"/urls/shares/{share.json()['id']}/revoke", headers=headers)
    gone_share = client.get(f"/urls/public/{token}")
    assert gone_share.status_code == 404

    renamed = client.patch(f"/urls/categories/{dev_id}", headers=headers, json={"name": "Engineering"})
    assert renamed.json()["name"] == "Engineering"

    client.delete(f"/urls/tags/{tutorial_id}", headers=headers)
    after_tag = client.get(f"/urls/{item_id}", headers=headers).json()
    assert {t["name"] for t in after_tag["tags"]} == {"music"}

    gone = client.delete(f"/urls/{item_id}", headers=headers)
    assert gone.status_code == 204
    assert client.get("/urls", headers=headers).json() == []


def test_url_vault_is_isolated_between_users():
    a = _headers("urls-a@example.com")
    b = _headers("urls-b@example.com")
    r = client.post("/urls", headers=a, json={"url": "https://a.example", "title": "A only", "fetch_preview": False})
    assert r.status_code == 201
    item_id = r.json()["id"]
    assert client.get("/urls", headers=b).json() == []
    assert client.get(f"/urls/{item_id}", headers=b).status_code == 404
    assert client.delete(f"/urls/{item_id}", headers=b).status_code == 404
