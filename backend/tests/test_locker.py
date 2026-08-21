from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def _headers():
    r = client.post("/auth/register", json={
        "email": "locker@example.com", "password": "password123", "full_name": "Locker User",
    })
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def test_locker_upload_list_download_delete():
    headers = _headers()
    summary = client.get("/locker/summary", headers=headers)
    assert summary.status_code == 200, summary.text
    assert summary.json()["total"] == 0

    r = client.post(
        "/locker",
        headers=headers,
        data={
            "title": "Aadhaar card",
            "doc_type": "aadhaar",
            "holder_name": "Renish",
            "id_number": "1234-5678-9012",
            "expiry_date": "2030-12-31",
        },
        files=[("files", ("aadhaar.pdf", b"%PDF-1.4 fake", "application/pdf"))],
    )
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["title"] == "Aadhaar card"
    assert item["doc_type"] == "aadhaar"
    assert item["id_number"] == "1234-5678-9012"
    assert item["file_count"] == 1
    item_id = item["id"]

    listed = client.get("/locker", headers=headers).json()
    assert len(listed) == 1
    assert listed[0]["id"] == item_id

    by_type = client.get("/locker", headers=headers, params={"doc_type": "aadhaar"}).json()
    assert len(by_type) == 1

    got = client.get(f"/locker/{item_id}", headers=headers)
    assert got.status_code == 200
    assert got.json()["holder_name"] == "Renish"

    dl = client.get(f"/locker/{item_id}/download", headers=headers)
    assert dl.status_code == 200
    assert dl.content.startswith(b"%PDF-1.4")

    patch = client.patch(f"/locker/{item_id}", headers=headers, json={"title": "Aadhaar — Renish"})
    assert patch.status_code == 200
    assert patch.json()["title"] == "Aadhaar — Renish"

    view = client.get(f"/locker/{item_id}/view", headers=headers)
    assert view.status_code == 200
    assert view.content.startswith(b"%PDF-1.4")
    assert "inline" in (view.headers.get("content-disposition") or "")

    added = client.post(
        f"/locker/{item_id}/files",
        headers=headers,
        files=[("files", ("back.png", b"\x89PNG\r\nfake", "image/png"))],
    )
    assert added.status_code == 201, added.text
    assert len(added.json()) == 2
    file_id = next(f["id"] for f in added.json() if f["original_filename"] == "back.png")

    removed = client.delete(f"/locker/{item_id}/files/{file_id}", headers=headers)
    assert removed.status_code == 204
    left = client.get(f"/locker/{item_id}/files", headers=headers).json()
    assert len(left) == 1
    assert left[0]["original_filename"] == "aadhaar.pdf"

    gone = client.delete(f"/locker/{item_id}", headers=headers)
    assert gone.status_code == 204
    empty = client.get("/locker", headers=headers).json()
    assert empty == []
    trash = client.get("/locker/trash", headers=headers)
    assert trash.status_code == 200
    assert len(trash.json()) == 1
    assert trash.json()[0]["id"] == item_id
    assert client.get("/locker/summary", headers=headers).json()["trash"] == 1

    restored = client.post(f"/locker/{item_id}/restore", headers=headers)
    assert restored.status_code == 200, restored.text
    assert restored.json()["id"] == item_id
    assert client.get("/locker", headers=headers).json()[0]["id"] == item_id
    assert client.get("/locker/trash", headers=headers).json() == []

    client.delete(f"/locker/{item_id}", headers=headers)
    purged = client.delete(f"/locker/{item_id}/permanent", headers=headers)
    assert purged.status_code == 204
    assert client.get("/locker/trash", headers=headers).json() == []
    assert client.get(f"/locker/{item_id}", headers=headers).status_code == 404


def test_locker_family_profiles_and_search_all():
    import uuid
    email = f"locker-fam-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/auth/register", json={
        "email": email, "password": "password123", "full_name": "Family Locker",
    })
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    people = client.get("/people", headers=headers)
    assert people.status_code == 200, people.text
    self_id = people.json()[0]["id"]
    child = client.post("/people", headers=headers, json={
        "name": "Appu", "relation": "child",
    })
    assert child.status_code == 201, child.text
    child_id = child.json()["id"]

    r1 = client.post(
        "/locker", headers=headers,
        data={"title": "PAN card", "doc_type": "pan", "person_id": self_id},
        files=[("files", ("pan.pdf", b"%PDF-1.4 a", "application/pdf"))],
    )
    assert r1.status_code == 201, r1.text
    assert r1.json()["person_id"] == self_id
    assert r1.json()["person_name"]

    r2 = client.post(
        "/locker", headers=headers,
        data={
            "title": "School ID", "doc_type": "other", "custom_type": "School ID",
            "person_id": child_id,
        },
        files=[("files", ("id.pdf", b"%PDF-1.4 b", "application/pdf"))],
    )
    assert r2.status_code == 201, r2.text
    assert r2.json()["person_id"] == child_id

    only_child = client.get("/locker", headers=headers, params={"person_id": child_id})
    assert only_child.status_code == 200
    assert len(only_child.json()) == 1
    assert only_child.json()[0]["title"] == "School ID"

    # Search spans every profile even if a person filter would otherwise apply.
    search = client.get("/locker", headers=headers, params={"q": "PAN", "person_id": child_id})
    assert search.status_code == 200
    titles = {row["title"] for row in search.json()}
    assert "PAN card" in titles

    by_name = client.get("/locker", headers=headers, params={"q": "Appu"})
    assert by_name.status_code == 200
    assert any(row["title"] == "School ID" for row in by_name.json())

    summary = client.get("/locker/summary", headers=headers).json()
    assert summary["total"] == 2
    assert any(p["id"] == child_id and p["count"] == 1 for p in summary["people"])
    assert summary["unassigned"] == 0


def test_locker_custom_folders():
    import uuid
    email = f"locker-folder-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/auth/register", json={
        "email": email, "password": "password123", "full_name": "Folder Locker",
    })
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    folder = client.post("/locker/folders", headers=headers, json={"name": "Gas book"})
    assert folder.status_code == 201, folder.text
    folder_id = folder.json()["id"]
    assert folder.json()["name"] == "Gas Book"

    lower = client.post("/locker/folders", headers=headers, json={"name": "bank"})
    assert lower.status_code == 201, lower.text
    assert lower.json()["name"] == "Bank"

    listed = client.get("/locker/folders", headers=headers).json()
    assert any(f["id"] == folder_id for f in listed)

    r = client.post(
        "/locker",
        headers=headers,
        data={
            "title": "Indane book",
            "doc_type": "other",
            "folder_id": folder_id,
        },
        files=[("files", ("gas.pdf", b"%PDF-1.4 g", "application/pdf"))],
    )
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["folder_id"] == folder_id
    assert item["folder_name"] == "Gas Book"
    assert item["type_label"] == "Gas Book"

    by_folder = client.get("/locker", headers=headers, params={"folder_id": folder_id}).json()
    assert len(by_folder) == 1
    assert by_folder[0]["title"] == "Indane book"

    summary = client.get("/locker/summary", headers=headers).json()
    assert any(f["id"] == folder_id and f["count"] == 1 for f in summary["folders"])
    assert any(t.get("custom") and t["id"] == f"folder:{folder_id}" for t in summary["types"])

    gone = client.delete(f"/locker/folders/{folder_id}", headers=headers)
    assert gone.status_code == 204
    item_after = client.get(f"/locker/{item['id']}", headers=headers).json()
    assert item_after["folder_id"] is None


def test_locker_nested_folders():
    import uuid
    email = f"locker-nest-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/auth/register", json={
        "email": email, "password": "password123", "full_name": "Nest User",
    })
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

    root = client.post("/locker/folders", headers=headers, json={"name": "bank"})
    assert root.status_code == 201, root.text
    root_id = root.json()["id"]
    assert root.json()["name"] == "Bank"
    assert root.json().get("parent_id") in (None, "")

    child = client.post("/locker/folders", headers=headers, json={"name": "statements", "parent_id": root_id})
    assert child.status_code == 201, child.text
    child_id = child.json()["id"]
    assert child.json()["parent_id"] == root_id
    assert child.json()["name"] == "Statements"

    tree = client.get("/locker/folders/tree", headers=headers)
    assert tree.status_code == 200
    names = [(n["name"], n["depth"], n.get("parent_id")) for n in tree.json()]
    assert ("Bank", 0, None) in [(a, b, c or None) for a, b, c in names] or any(
        a == "Bank" and b == 0 for a, b, _ in names
    )
    assert any(a == "Statements" and b == 1 and c == root_id for a, b, c in names)

    kids = client.get("/locker/folders", headers=headers, params={"parent_id": root_id})
    assert kids.status_code == 200
    assert len(kids.json()) == 1
    assert kids.json()[0]["id"] == child_id


def test_locker_document_share():
    import uuid
    email = f"locker-share-{uuid.uuid4().hex[:8]}@example.com"
    r = client.post("/auth/register", json={
        "email": email, "password": "password123", "full_name": "Share User",
    })
    assert r.status_code == 201, r.text
    headers = {"Authorization": f"Bearer {r.json()['access_token']}"}
    created = client.post(
        "/locker",
        headers=headers,
        data={
            "title": "Passport scan",
            "doc_type": "passport",
            "holder_name": "Renish",
        },
        files=[("files", ("passport.pdf", b"%PDF-1.4 share-me", "application/pdf"))],
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["id"]

    send = client.post(
        f"/locker/{item_id}/sends",
        headers=headers,
        json={
            "name": "Passport share",
            "send_type": "locker",
            "item_id": item_id,
            "pin": "4242",
            "expires_in_hours": 6,
            "max_views": 2,
            "require_grant": False,
            "files_only": True,
        },
    )
    assert send.status_code == 201, send.text
    body = send.json()
    assert body["send_type"] == "locker"
    assert body["item_id"] == item_id
    assert body["has_pin"] is True
    token = body["token"]

    listed = client.get(f"/locker/{item_id}/sends", headers=headers)
    assert listed.status_code == 200
    assert any(s["token"] == token for s in listed.json())

    locked = client.get(f"/vault/public/{token}/page")
    assert locked.status_code == 200
    assert b"Access code" in locked.content or b"PIN" in locked.content or b"code" in locked.content.lower()

    unlocked = client.get(f"/vault/public/{token}/page", params={"pin": "4242"})
    assert unlocked.status_code == 200
    assert b"passport.pdf" in unlocked.content
    assert b"Print" in unlocked.content
    assert b"locker-print-sheet" in unlocked.content or b"js-locker-print-one" in unlocked.content
    # Files-only mode must not expose document metadata
    assert b"Renish" not in unlocked.content
    assert b"Passport scan" not in unlocked.content

    view = client.get(f"/vault/public/{token}/locker/view", params={"pin": "4242"})
    assert view.status_code == 200
    assert view.content.startswith(b"%PDF-1.4")
    assert "inline" in (view.headers.get("content-disposition") or "")

    dl = client.get(f"/vault/public/{token}/locker/download", params={"pin": "4242"})
    assert dl.status_code == 200
    assert dl.content.startswith(b"%PDF-1.4")

    pub = client.get(f"/vault/public/{token}", params={"pin": "4242"})
    assert pub.status_code == 200
    data = pub.json()
    assert data["send_type"] == "locker"
    assert data.get("locker_title") == "Passport scan" or data.get("name") == "Passport share"

    revoked = client.delete(f"/locker/sends/{body['id']}", headers=headers)
    assert revoked.status_code == 204
    gone = client.get(f"/vault/public/{token}/page", params={"pin": "4242"})
    assert gone.status_code in (404, 410) or b"no longer" in gone.content.lower() or b"unavailable" in gone.content.lower()
