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
    files = {"files": ("report.txt", payload, "text/plain")}
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
    assert "Welcome back" in r.text

    r = client.post(
        "/admin/login",
        data={"email": "adminui@example.com", "password": "password123"},
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert "Choose a module" in r.text
    assert "Password Vault" in r.text

    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 200  # already logged in this session
    assert "Hi, Admin" in r.text


def test_health_endpoint():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_viewer_role_is_read_only():
    owner = _register("owner@example.com", "password123", "Vault Owner")
    headers = _auth_headers(owner["access_token"])
    person_id = client.get("/people", headers=headers).json()[0]["id"]

    r = client.post(
        "/auth/invite",
        json={"email": "spouse@example.com", "password": "password123", "full_name": "Spouse Viewer"},
        headers=headers,
    )
    assert r.status_code == 201
    assert r.json()["role"] == "viewer"

    login = client.post("/auth/login", data={"username": "spouse@example.com", "password": "password123"})
    vheaders = _auth_headers(login.json()["access_token"])

    people = client.get("/people", headers=vheaders).json()
    assert any(p["id"] == person_id for p in people)

    r = client.post("/people", json={"name": "Should Fail", "relation": "child"}, headers=vheaders)
    assert r.status_code == 403


def test_ocr_text_is_searchable_and_labs_parse():
    data = _register("ocr@example.com", "password123", "Ocr User")
    headers = _auth_headers(data["access_token"])
    person_id = client.get("/people", headers=headers).json()[0]["id"]

    payload = b"Lab report\nGlucose 142 mg/dL\nHbA1c 6.4\nCholesterol 190\nBP 128/82\n"
    files = {"files": ("labs.txt", payload, "text/plain")}
    form = {"person_id": person_id, "category": "lab_report", "title": "Annual labs", "doc_date": "2026-08-01"}
    r = client.post("/documents", data=form, files=files, headers=headers)
    assert r.status_code == 201, r.text
    doc_id = r.json()["id"]

    r = client.get(f"/documents/{doc_id}", headers=headers)
    assert "Glucose 142" in (r.json().get("extracted_text") or "")

    r = client.get("/search?q=Glucose", headers=headers)
    assert any(d["id"] == doc_id for d in r.json()["documents"])

    r = client.get(f"/labs/trends?person_id={person_id}", headers=headers)
    assert r.status_code == 200
    metrics = {t["metric"] for t in r.json()}
    assert "glucose" in metrics
    assert "hba1c" in metrics
    assert "bp_sys" in metrics


def test_share_link_public_view():
    data = _register("share@example.com", "password123", "Share User")
    headers = _auth_headers(data["access_token"])
    person_id = client.get("/people", headers=headers).json()[0]["id"]
    files = {"files": ("card.txt", b"insurance card", "text/plain")}
    form = {"person_id": person_id, "category": "insurance", "title": "Star Health"}
    doc_id = client.post("/documents", data=form, files=files, headers=headers).json()["id"]

    r = client.post("/share", json={"document_id": doc_id, "expires_in_hours": 4}, headers=headers)
    assert r.status_code == 201
    token = r.json()["token"]

    public = client.get(f"/share/public/{token}", headers={"User-Agent": "pytest-client/1.0"})
    assert public.status_code == 200
    assert public.json()["title"] == "Star Health"

    page = client.get(f"/share/public/{token}/page")
    assert page.status_code == 200
    assert b"Star Health" in page.content

    listed = client.get("/share/mine", headers=headers)
    assert listed.status_code == 200
    assert listed.json()[0]["view_count"] >= 2
    link_id = listed.json()[0]["id"]

    detail = client.get(f"/share/{link_id}", headers=headers)
    assert detail.status_code == 200
    accesses = detail.json()["accesses"]
    assert len(accesses) >= 2
    assert all(a["action"] == "view" for a in accesses)
    assert any(a.get("ip") for a in accesses)
    assert any("pytest" in (a.get("user_agent") or "") for a in accesses)

    dl = client.get(f"/share/public/{token}/download")
    assert dl.status_code == 200
    assert dl.content == b"insurance card"

    detail = client.get(f"/share/{link_id}", headers=headers)
    assert any(a["action"] == "download" for a in detail.json()["accesses"])
    assert detail.json()["download_count"] >= 1

    revoke = client.delete(f"/share/{link_id}", headers=headers)
    assert revoke.status_code == 204
    assert client.get(f"/share/public/{token}").status_code == 404


def test_encrypted_backup_roundtrip():
    data = _register("backup@example.com", "password123", "Backup User")
    headers = _auth_headers(data["access_token"])
    person_id = client.get("/people", headers=headers).json()[0]["id"]
    files = {"files": ("note.txt", b"keep me", "text/plain")}
    form = {"person_id": person_id, "category": "other", "title": "Keep"}
    assert client.post("/documents", data=form, files=files, headers=headers).status_code == 201

    r = client.get("/backup/export?password=secret-pass", headers=headers)
    assert r.status_code == 200
    blob = r.content
    assert blob.startswith(b"HV1\0")

    r = client.post(
        "/backup/restore",
        headers=headers,
        files={"file": ("vault.hvbak", blob, "application/octet-stream")},
        data={"password": "secret-pass"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


def test_google_drive_status_disconnected():
    data = _register("gdrive@example.com", "password123", "Drive User")
    headers = _auth_headers(data["access_token"])
    r = client.get("/backup/google", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["connected"] is False
    assert body["enabled"] is False
    r = client.post("/backup/google/settings", headers=headers, json={"enabled": True})
    assert r.status_code == 400


def test_google_drive_should_run_now():
    from datetime import datetime
    from app.drive_backup import should_run_now
    from app.models import GoogleDriveBackup
    row = GoogleDriveBackup(
        user_id="x", enabled=True, hour=3, refresh_token_enc="enc", password_enc="enc",
        last_run_at=None, last_ok=None,
    )
    assert should_run_now(row, datetime(2026, 8, 13, 2, 0)) is False
    assert should_run_now(row, datetime(2026, 8, 13, 3, 5)) is True
    row.last_run_at = datetime(2026, 8, 13, 3, 10)
    row.last_ok = True
    assert should_run_now(row, datetime(2026, 8, 13, 15, 0)) is False
    assert should_run_now(row, datetime(2026, 8, 14, 3, 1)) is True


def test_medicines_vaccines_visits_and_ice():
    data = _register("care@example.com", "password123", "Care User")
    headers = _auth_headers(data["access_token"])
    person_id = client.get("/people", headers=headers).json()[0]["id"]
    assert client.get("/people", headers=headers).json()[0]["ice_token"]

    r = client.post("/medicines", json={"person_id": person_id, "name": "Metformin", "dose": "500mg", "remaining": 14}, headers=headers)
    assert r.status_code == 201, r.text
    assert client.get(f"/medicines?person_id={person_id}", headers=headers).json()[0]["name"] == "Metformin"

    r = client.post("/vaccinations", json={"person_id": person_id, "vaccine_name": "Tetanus", "next_due": "2099-01-01"}, headers=headers)
    assert r.status_code == 201
    assert client.get(f"/vaccinations?person_id={person_id}", headers=headers).json()[0]["overdue"] is False

    r = client.post("/visits", json={"person_id": person_id, "hospital_name": "Apollo", "reason": "Checkup"}, headers=headers)
    assert r.status_code == 201
    assert client.get(f"/timeline?person_id={person_id}", headers=headers).status_code == 200

    token = client.get("/people", headers=headers).json()[0]["ice_token"]
    ice = client.get(f"/ice/{token}")
    assert ice.status_code == 200
    assert b"Care User" in ice.content


def test_share_pack_and_pin():
    data = _register("pack@example.com", "password123", "Pack User")
    headers = _auth_headers(data["access_token"])
    person_id = client.get("/people", headers=headers).json()[0]["id"]
    files = {"files": ("id.txt", b"uhid-1", "text/plain")}
    form = {"person_id": person_id, "category": "hospital_card", "title": "ID"}
    doc_id = client.post("/documents", data=form, files=files, headers=headers).json()["id"]

    r = client.post("/share/packs", json={"title": "Front desk", "document_ids": [doc_id], "expires_in_hours": 4, "pin": "1234"}, headers=headers)
    assert r.status_code == 201, r.text
    token = r.json()["token"]
    assert r.json()["has_pin"] is True

    blocked = client.get(f"/share/public/pack/{token}/page")
    assert blocked.status_code == 200
    assert b"PIN" in blocked.content

    opened = client.get(f"/share/public/pack/{token}/page", params={"pin": "1234"})
    assert opened.status_code == 200
    assert b"Front desk" in opened.content or b"ID" in opened.content


def test_totp_setup_and_login_gate():
    data = _register("totp@example.com", "password123", "Totp User")
    headers = _auth_headers(data["access_token"])
    setup = client.post("/auth/totp/setup", headers=headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    from app.security import totp_code
    code = totp_code(secret)
    assert client.post("/auth/totp/enable", json={"code": code}, headers=headers).status_code == 204

    login = client.post("/auth/login", data={"username": "totp@example.com", "password": "password123"})
    assert login.status_code == 200
    body = login.json()
    assert body["totp_required"] is True
    assert body["access_token"] == ""

    verify = client.post("/auth/totp/verify", json={"totp_token": body["totp_token"], "code": totp_code(secret)})
    assert verify.status_code == 200
    assert verify.json()["access_token"]


def test_password_vault_login_totp_trash_send_health():
    data = _register("vault@example.com", "password123", "Vault User")
    headers = _auth_headers(data["access_token"])

    folder = client.post("/vault/folders", json={"name": "Banks"}, headers=headers)
    assert folder.status_code == 201, folder.text
    folder_id = folder.json()["id"]

    r = client.post("/vault/items", json={
        "name": "HDFC NetBanking",
        "item_type": "login",
        "folder_id": folder_id,
        "username": "nicky",
        "password": "password",
        "uris": ["https://netbanking.hdfcbank.com"],
        "totp_secret": None,
    }, headers=headers)
    assert r.status_code == 201, r.text
    item_id = r.json()["id"]
    assert r.json()["password"] == "password"

    listed = client.get("/vault/items?q=hdfc", headers=headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    gen = client.post("/vault/generate", json={"kind": "password", "length": 20}, headers=headers)
    assert gen.status_code == 200
    strong = gen.json()["value"]
    assert len(strong) == 20

    patched = client.patch(f"/vault/items/{item_id}", json={"password": strong, "totp_secret": "JBSWY3DPEHPK3PXP"}, headers=headers)
    assert patched.status_code == 200
    hist = client.get(f"/vault/items/{item_id}/history", headers=headers)
    assert len(hist.json()) == 1
    assert hist.json()[0]["password"] == "password"

    totp = client.get(f"/vault/items/{item_id}/totp", headers=headers)
    assert totp.status_code == 200
    assert len(totp.json()["code"]) == 6

    health = client.get("/vault/health", headers=headers)
    assert health.status_code == 200
    assert health.json()["total_logins"] == 1

    send = client.post("/vault/sends", json={
        "name": "Temp login", "send_type": "login", "item_id": item_id, "expires_in_hours": 2,
    }, headers=headers)
    assert send.status_code == 201, send.text
    token = send.json()["token"]
    page = client.get(f"/vault/public/{token}/page")
    assert page.status_code == 200
    assert b"HDFC" in page.content or b"nicky" in page.content
    short = client.get(f"/v/{token}", follow_redirects=False)
    assert short.status_code == 302

    assert client.delete(f"/vault/items/{item_id}", headers=headers).status_code == 204
    trash = client.get("/vault/trash", headers=headers)
    assert len(trash.json()) == 1
    assert client.post(f"/vault/items/{item_id}/restore", headers=headers).status_code == 200
    assert client.get("/vault/items", headers=headers).json()[0]["id"] == item_id

    other = _register("othervault@example.com", "password123", "Other")
    other_h = _auth_headers(other["access_token"])
    assert client.get(f"/vault/items/{item_id}", headers=other_h).status_code == 404
    assert client.get("/vault/items", headers=other_h).json() == []

