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
        email="fam_request_owner@example.com",
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
    resp = client.post("/auth/login", data={"username": "fam_request_owner@example.com", "password": "password123"})
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
        data={"email": "fam_request_owner@example.com", "password": "password123"},
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



def test_invite_existing_standalone_account_flow():
    """Owner invites an ALREADY-INDEPENDENT account via the real
    /admin/family/profiles/{id}/invite endpoint. Deepthi must keep full
    access to her own pre-existing data throughout - a pending invite must
    never silently repoint her vault."""
    db = SessionLocal()

    # Pre-existing standalone user Deepthi Maria, with her own data.
    deepthi = models.User(
        email="deepthi@example.com",
        hashed_password=security.hash_password("password123"),
        full_name="DEEPTHI MARIA",
        role=models.UserRole.owner.value,
        family_status="accepted",
    )
    db.add(deepthi)
    db.commit()
    db.refresh(deepthi)
    deepthi.vault_owner_id = deepthi.id
    db.commit()
    deepthi_self = models.Person(
        user_id=deepthi.id, name="DEEPTHI MARIA", relation=models.Relation.self_,
        avatar_initials="DM",
    )
    db.add(deepthi_self)
    db.commit()
    db.refresh(deepthi_self)
    deepthi_self_person_id = deepthi_self.id

    resp = client.post("/auth/login", data={"username": "deepthi@example.com", "password": "password123"})
    assert resp.status_code == 200, resp.text
    deepthi_headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}
    resp = client.post(
        "/documents",
        headers=deepthi_headers,
        data={
            "person_id": deepthi_self_person_id,
            "category": "prescription",
            "title": "Deepthis Own Old Report",
            "hospital_name": "Her Own Hospital",
        },
        files=[("files", ("own.jpg", b"\xff\xd8\xfftest", "image/jpeg"))],
    )
    assert resp.status_code == 201, resp.text

    # Owner logs into the admin web UI (this feature is admin/HTML, not the JSON /family/invite API).
    web = TestClient(app)
    resp = web.post(
        "/admin/login",
        data={"email": "fam_request_owner@example.com", "password": "password123"},
        follow_redirects=False,
    )
    assert resp.status_code == 302

    # Owner creates a profile-only entry for the wife, then invites Deepthi's existing account to it.
    resp = web.post(
        "/admin/family/add",
        data={"name": "Deepthi Maria", "relation": "spouse", "email": "deepthi@example.com"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    owner = db.query(models.User).filter(models.User.email == "fam_request_owner@example.com").first()
    wife_person = (
        db.query(models.Person)
        .filter(models.Person.user_id == owner.id, models.Person.relation == models.Relation.spouse)
        .first()
    )
    assert wife_person is not None

    resp = web.post(
        f"/admin/family/profiles/{wife_person.id}/invite",
        data={"email": "deepthi@example.com"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "err=" not in resp.headers["location"]

    db.refresh(deepthi)
    assert deepthi.family_status == "pending"
    # Bug fix assertion: vault_owner_id must NOT change until Deepthi accepts.
    assert deepthi.vault_owner_id == deepthi.id
    assert deepthi.pending_vault_owner_id == owner.id

    # While pending, Deepthi must still see her own pre-existing document.
    resp = client.get("/documents", headers=deepthi_headers)
    assert resp.status_code == 200, resp.text
    assert any(d["title"] == "Deepthis Own Old Report" for d in resp.json())

    # Deepthi rejects the invite -> her own data must remain fully intact and accessible.
    resp = client.post("/family/request/reject", headers=deepthi_headers)
    assert resp.status_code == 200, resp.text
    db.refresh(deepthi)
    assert deepthi.family_status == "rejected"
    assert deepthi.vault_owner_id == deepthi.id
    assert deepthi.pending_vault_owner_id is None

    resp = client.get("/documents", headers=deepthi_headers)
    assert resp.status_code == 200, resp.text
    assert any(d["title"] == "Deepthis Own Old Report" for d in resp.json())

    # --- Re-invite and this time ACCEPT: only now should she join the owner's vault. ---
    db.refresh(wife_person)
    resp = web.post(
        f"/admin/family/profiles/{wife_person.id}/invite",
        data={"email": "deepthi@example.com"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    resp = client.post("/family/request/accept", headers=deepthi_headers)
    assert resp.status_code == 200, resp.text

    db.refresh(deepthi)
    assert deepthi.family_status == "accepted"
    assert deepthi.vault_owner_id == owner.id

    # Now Deepthi sees members of Husband Owner's vault.
    # NOTE: once she actually joins (accepts), vault_id() switches fully to the
    # owner's vault, same as any other member - so her pre-join documents are
    # no longer listed under /documents. That's the existing, unrelated
    # single-vault-per-login data model and is out of scope for this fix; the
    # bug this test guards against is the vault switch happening *before*
    # accept, which the assertions above cover.
    members = client.get("/family/members", headers=deepthi_headers).json()
    assert len(members) > 0

    db.close()

