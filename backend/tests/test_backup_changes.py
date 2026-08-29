import io
import zipfile
from datetime import datetime
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal
from app import models, crypto
from app.deps import vault_id
from app.routers.backup import build_vault_backup, build_vault_backup_bundle
from app.drive_backup import run_backup

client = TestClient(app)


def _register(email: str, password: str = "password123", name: str = "Test User") -> dict:
    r = client.post("/auth/register", json={"email": email, "password": password, "full_name": name})
    assert r.status_code == 201, r.text
    return r.json()


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_backup_zip_deflated_compression():
    data = _register("backup_comp@example.com", "password123", "Compression User")
    headers = _auth_headers(data["access_token"])
    person_id = client.get("/people", headers=headers).json()[0]["id"]

    # Upload a document with repetitive compressible content
    large_text = b"HealthVault confidential report line.\n" * 200
    files = {"files": ("report.txt", large_text, "text/plain")}
    form = {"person_id": person_id, "category": "other", "title": "Report", "hospital_name": "Clinic"}
    res = client.post("/documents", data=form, files=files, headers=headers)
    assert res.status_code == 201

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == "backup_comp@example.com").first()
        zip_bytes, content_hash = build_vault_backup_bundle(db, user)

        # Ensure content is compressed
        assert len(zip_bytes) < len(large_text)
        assert len(content_hash) == 64

        # Read zip and verify compression type is ZIP_DEFLATED
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
        found_file = False
        for info in zf.infolist():
            if info.filename.endswith("report.txt"):
                found_file = True
                assert info.compress_type == zipfile.ZIP_DEFLATED
                assert info.compress_size < info.file_size
        assert found_file is True
    finally:
        db.close()


def test_vault_content_hash_deterministic_across_time():
    data = _register("backup_hash@example.com", "password123", "Hash User")
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == "backup_hash@example.com").first()
        zip1, hash1 = build_vault_backup_bundle(db, user)
        zip2, hash2 = build_vault_backup_bundle(db, user)

        # Content hash must be identical when no data has changed
        assert hash1 == hash2
        assert len(hash1) == 64
    finally:
        db.close()


def test_vault_content_hash_changes_on_data_mutation():
    data = _register("backup_mutate@example.com", "password123", "Mutate User")
    headers = _auth_headers(data["access_token"])
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == "backup_mutate@example.com").first()
        _, initial_hash = build_vault_backup_bundle(db, user)

        # Add a password item
        r = client.post("/vault/items", json={
            "name": "New Login",
            "item_type": "login",
            "username": "tester",
            "password": "secretpassword",
        }, headers=headers)
        assert r.status_code == 201

        _, mutated_hash = build_vault_backup_bundle(db, user)
        assert mutated_hash != initial_hash
    finally:
        db.close()


def test_drive_backup_skips_when_no_change_and_forces_when_requested(monkeypatch):
    data = _register("backup_gdrive@example.com", "password123", "GDrive User")
    headers = _auth_headers(data["access_token"])

    upload_count = 0

    def mock_refresh_access_token(cid, secret, refresh):
        return "mock-access-token"

    def mock_ensure_folder(token, folder_id):
        return "mock-folder-id"

    def mock_upload_bytes(token, folder_id, name, blob):
        nonlocal upload_count
        upload_count += 1
        return {"id": f"drive-file-{upload_count}", "name": name}

    def mock_list_backups(token, folder_id):
        return []

    from app import gdrive
    monkeypatch.setattr(gdrive, "refresh_access_token", mock_refresh_access_token)
    monkeypatch.setattr(gdrive, "ensure_folder", mock_ensure_folder)
    monkeypatch.setattr(gdrive, "upload_bytes", mock_upload_bytes)
    monkeypatch.setattr(gdrive, "list_backups", mock_list_backups)

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == "backup_gdrive@example.com").first()
        uid = vault_id(user)

        # Set up connected Drive backup
        drive_row = models.GoogleDriveBackup(
            user_id=uid,
            client_id="mock-client-id",
            client_secret_enc=crypto.encrypt_text("mock-secret"),
            refresh_token_enc=crypto.encrypt_text("mock-refresh"),
            password_enc=crypto.encrypt_text("backup-password-123"),
            enabled=True,
        )
        db.add(drive_row)
        db.commit()

        # 1. First run: must upload to Google Drive
        res1 = run_backup(db, user, force=False)
        assert res1["ok"] is True
        assert res1.get("skipped") is not True
        assert upload_count == 1
        assert drive_row.last_content_hash is not None

        # 2. Second run without changes: must skip upload
        res2 = run_backup(db, user, force=False)
        assert res2["ok"] is True
        assert res2.get("skipped") is True
        assert res2.get("reason") == "no_change"
        assert upload_count == 1  # No new upload

        # 3. Third run with force=True: must upload even though unchanged
        res3 = run_backup(db, user, force=True)
        assert res3["ok"] is True
        assert res3.get("skipped") is not True
        assert upload_count == 2

        # 4. Mutate vault data and run with force=False: must upload
        client.post("/reminders", json={
            "person_id": client.get("/people", headers=headers).json()[0]["id"],
            "title": "Checkup reminder",
            "remind_at": "2026-09-01T10:00:00",
        }, headers=headers)

        res4 = run_backup(db, user, force=False)
        assert res4["ok"] is True
        assert res4.get("skipped") is not True
        assert upload_count == 3
    finally:
        db.close()
