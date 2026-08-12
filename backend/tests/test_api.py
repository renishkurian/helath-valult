from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def _register(email="nicky@example.com", password="password123", name="Nicky Kurian"):
    r = client.post("/auth/register", json={"email": email, "password": password, "full_name": name})
    assert r.status_code == 201, r.text
    return r.json()


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_register_and_login():
    data = _register("register_test@example.com", "password123", "Register Test")
    assert "access_token" in data
    assert "refresh_token" in data

    r = client.post("/auth/login", data={"username": "register_test@example.com", "password": "password123"})
    assert r.status_code == 200
    assert "access_token" in r.json()


def test_register_creates_self_person():
    data = _register("selfperson@example.com", "password123", "Self Person")
    headers = _auth_headers(data["access_token"])
    r = client.get("/people", headers=headers)
    assert r.status_code == 200
    people = r.json()
    assert len(people) == 1
    assert people[0]["relation"] == "self"
    assert people[0]["name"] == "Self Person"


def test_family_member_and_card_flow():
    data = _register("family@example.com", "password123", "Family Owner")
    headers = _auth_headers(data["access_token"])

    self_person_id = client.get("/people", headers=headers).json()[0]["id"]

    r = client.post("/people", json={"name": "Meera Kurian", "relation": "spouse"}, headers=headers)
    assert r.status_code == 201
    spouse_id = r.json()["id"]

    r = client.post(
        "/cards",
        json={
            "person_id": self_person_id,
            "hospital_name": "Apollo Hospitals",
            "patient_id": "PID-998877",
            "blood_group": "O+",
        },
        headers=headers,
    )
    assert r.status_code == 201
    card = r.json()
    # Patient ID should round-trip correctly through encryption.
    assert card["patient_id"] == "PID-998877"

    r = client.get(f"/cards?person_id={self_person_id}", headers=headers)
    assert len(r.json()) == 1

    r = client.get(f"/cards?person_id={spouse_id}", headers=headers)
    assert len(r.json()) == 0


def test_cross_account_isolation():
    """A user must never see another user's people/cards."""
    a = _register("accounta@example.com", "password123", "Account A")
    b = _register("accountb@example.com", "password123", "Account B")
    headers_a = _auth_headers(a["access_token"])
    headers_b = _auth_headers(b["access_token"])

    person_a = client.get("/people", headers=headers_a).json()[0]["id"]

    r = client.post(
        "/cards",
        json={"person_id": person_a, "hospital_name": "Private Hospital"},
        headers=headers_b,
    )
    # B should not be able to attach a card to A's person.
    assert r.status_code == 404


def test_document_upload_download_is_encrypted_on_disk():
    import glob

    data = _register("docs@example.com", "password123", "Docs User")
    headers = _auth_headers(data["access_token"])
    person_id = client.get("/people", headers=headers).json()[0]["id"]

    payload = b"confidential lab result data"
    files = {"file": ("report.txt", payload, "text/plain")}
    form = {"person_id": person_id, "category": "lab_report", "title": "CBC Report"}
    r = client.post("/documents", data=form, files=files, headers=headers)
    assert r.status_code == 201
    doc_id = r.json()["id"]

    # The file on disk must never contain the plaintext bytes.
    enc_files = glob.glob("test_ci_storage/**/*.enc", recursive=True)
    assert enc_files
    matching = [f for f in enc_files if doc_id in f]
    assert matching
    on_disk = open(matching[0], "rb").read()
    assert payload not in on_disk

    r = client.get(f"/documents/{doc_id}/download", headers=headers)
    assert r.status_code == 200
    assert r.content == payload


def test_search_by_hospital_name():
    data = _register("search@example.com", "password123", "Search User")
    headers = _auth_headers(data["access_token"])
    person_id = client.get("/people", headers=headers).json()[0]["id"]

    client.post("/cards", json={"person_id": person_id, "hospital_name": "Fortis Hospital"}, headers=headers)

    r = client.get("/search?q=Fortis", headers=headers)
    assert r.status_code == 200
    result = r.json()
    assert len(result["cards"]) == 1
    assert result["cards"][0]["hospital_name"] == "Fortis Hospital"

    r = client.get("/search?q=NoSuchHospital", headers=headers)
    assert r.json()["cards"] == []


def test_reminder_crud():
    data = _register("reminders@example.com", "password123", "Reminder User")
    headers = _auth_headers(data["access_token"])
    person_id = client.get("/people", headers=headers).json()[0]["id"]

    r = client.post(
        "/reminders",
        json={"person_id": person_id, "title": "Take BP medicine", "remind_at": "2026-08-15T09:00:00", "repeat_rule": "daily"},
        headers=headers,
    )
    assert r.status_code == 201
    reminder_id = r.json()["id"]

    r = client.get("/reminders", headers=headers)
    assert any(rem["id"] == reminder_id for rem in r.json())

    r = client.delete(f"/reminders/{reminder_id}", headers=headers)
    assert r.status_code == 204


def test_admin_ui_login_and_dashboard():
    _register("adminui@example.com", "password123", "Admin UI User")

    r = client.get("/admin/login")
    assert r.status_code == 200
    assert "Admin sign in" in r.text

    r = client.post(
        "/admin/login",
        data={"email": "adminui@example.com", "password": "password123"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "Hi, Admin" in r.text

    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 200  # already logged in this session


def test_health_endpoint():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
