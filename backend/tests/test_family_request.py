import pytest
from fastapi.testclient import TestClient

from app.main import app
from app import models, security
from app.database import SessionLocal, engine
from app.schema import ensure_schema

client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    ensure_schema(engine)
    db = SessionLocal()
    db.query(models.FamilyShare).delete()
    db.query(models.Document).delete()
    db.query(models.Person).delete()
    db.query(models.User).delete()
    db.commit()

    # Owner (husband)
    owner = models.User(
        email="owner@example.com",
        hashed_password=security.hash_password("password123"),
        full_name="Husband Owner",
        role=models.UserRole.owner.value,
        family_status="accepted",
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)
    owner.vault_owner_id = owner.id
    db.commit()

    db.close()
    yield


def test_family_invite_request_flow_and_data_access():
    db = SessionLocal()

    # Owner logs in
    resp = client.post("/auth/login", data={"username": "owner@example.com", "password": "password123"})
    assert resp.status_code == 200, resp.text
    owner_token = resp.json()["access_token"]
    owner_headers = {"Authorization": f"Bearer {owner_token}"}

    # 1. Owner invites wife
    resp = client.post(
        "/family/invite",
        headers=owner_headers,
        json={
            "email": "wife@example.com",
            "password": "wifePassword123",
            "full_name": "Wife Member",
            "relation": "spouse",
        },
    )
    assert resp.status_code == 201, resp.text
    invited_data = resp.json()
    wife_person_id = invited_data["person_id"]

    wife_user = db.query(models.User).filter(models.User.email == "wife@example.com").first()
    assert wife_user is not None
    assert wife_user.family_status == "pending"

    # 2. Owner adds a document against wife's Person profile
    resp = client.post(
        "/documents",
        headers=owner_headers,
        data={
            "person_id": wife_person_id,
            "category": "prescription",
            "title": "Wife Prescription Document",
            "hospital_name": "City Hospital",
        },
        files=[("files", ("rx.jpg", b"\xff\xd8\xfftest", "image/jpeg"))],
    )
    assert resp.status_code == 201, resp.text
    doc_id = resp.json()["id"]

    # 3. Wife logs in while pending
    resp = client.post("/auth/login", data={"username": "wife@example.com", "password": "wifePassword123"})
    assert resp.status_code == 200, resp.text
    wife_token = resp.json()["access_token"]
    wife_headers = {"Authorization": f"Bearer {wife_token}"}

    # Verify request status endpoint
    resp = client.get("/family/request", headers=wife_headers)
    assert resp.status_code == 200, resp.text
    req_info = resp.json()
    assert req_info["status"] == "pending"
    assert req_info["manager_name"] == "Husband Owner"

    # While pending, wife cannot see family members or documents added for her profile
    resp = client.get("/family/members", headers=wife_headers)
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 0

    resp = client.get("/documents", headers=wife_headers)
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 0

    # 4. Wife accepts family request
    resp = client.post("/family/request/accept", headers=wife_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["family_status"] == "accepted"

    # Now accepted: wife can see family members & document added against her profile!
    resp = client.get("/family/members", headers=wife_headers)
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) > 0

    resp = client.get("/documents", headers=wife_headers)
    assert resp.status_code == 200, resp.text
    wife_docs = resp.json()
    assert len(wife_docs) == 1
    assert wife_docs[0]["id"] == doc_id
    assert wife_docs[0]["title"] == "Wife Prescription Document"

    # 5. Owner removes wife from family via admin route
    web = TestClient(app)
    resp = web.post(
        "/admin/login",
        data={"email": "owner@example.com", "password": "password123"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    resp = web.post(
        f"/admin/family/members/{wife_user.id}/remove",
        follow_redirects=False,
    )
    assert resp.status_code == 302

    db.refresh(wife_user)
    assert wife_user.family_status == "removed"

    # Once removed, wife can no longer view documents added for her profile
    resp = client.get("/documents", headers=wife_headers)
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == 0

    db.close()
