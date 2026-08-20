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
    assert folder.json()["name"] == "Gas book"

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
    assert item["folder_name"] == "Gas book"
    assert item["type_label"] == "Gas book"

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
