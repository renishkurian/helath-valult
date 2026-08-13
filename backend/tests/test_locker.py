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

    gone = client.delete(f"/locker/{item_id}", headers=headers)
    assert gone.status_code == 204
    empty = client.get("/locker", headers=headers).json()
    assert empty == []
