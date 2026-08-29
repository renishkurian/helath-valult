from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db
from app import models
from app.routers.automation import record_automation_audit

engine = create_engine("sqlite:////tmp/test_auto.db", connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)


def test_record_automation_audit():
    db = TestingSessionLocal()
    try:
        log = record_automation_audit(
            action="shopping_add_item",
            resource_type="shopping",
            resource_id="123",
            details="Added 2L milk",
            actor="openclaw",
            status="success",
            db=db,
        )
        assert log.id is not None
        assert log.actor == "openclaw"
        assert log.action == "shopping_add_item"
        assert log.resource_type == "shopping"

        # Query back
        fetched = db.query(models.AutomationAuditLog).filter_by(id=log.id).first()
        assert fetched is not None
        assert fetched.details == "Added 2L milk"
    finally:
        db.close()


def test_user_api_token_generation_and_auth():
    import uuid
    from app import security
    db = TestingSessionLocal()
    try:
        u_id = uuid.uuid4().hex
        email = f"pat_{u_id[:8]}@test.com"
        # Create a test user
        user = models.User(
            id=u_id,
            email=email,
            hashed_password=security.hash_password("testpass123"),
            full_name="PAT Tester",
            role="owner",
        )
        db.add(user)
        db.commit()

        token, token_hash, prefix = security.generate_api_token()
        assert token.startswith("hv_pat_")
        assert prefix.startswith("hv_pat_")

        tok_id = uuid.uuid4().hex
        tok_obj = models.UserApiToken(
            id=tok_id,
            user_id=user.id,
            name="OpenClaw Test Token",
            token_hash=token_hash,
            prefix=prefix,
        )
        db.add(tok_obj)
        db.commit()

        # Lookup by hash
        found = db.query(models.UserApiToken).filter_by(token_hash=security.hash_api_token(token)).first()
        assert found is not None
        assert found.user_id == user.id
        assert found.name == "OpenClaw Test Token"

        # Test FastAPI endpoint authentication using the Bearer token with app db override
        app.dependency_overrides[get_db] = lambda: db
        try:
            client = TestClient(app)
            res = client.get("/automation/logs", headers={"Authorization": f"Bearer {token}"})
            assert res.status_code == 200
            assert isinstance(res.json(), list)
        finally:
            app.dependency_overrides.clear()
    finally:
        db.close()


def test_admin_automation_logs_pagination():
    import uuid
    from datetime import datetime, timedelta
    from app import security

    db = TestingSessionLocal()
    try:
        u_id = uuid.uuid4().hex
        email = f"auto_{u_id[:8]}@test.com"
        user = models.User(
            id=u_id,
            email=email,
            hashed_password=security.hash_password("testpass123"),
            full_name="Auto User",
            role="owner",
            enabled_modules=None,
        )
        db.add(user)
        db.commit()

        # Insert 45 audit logs
        base_time = datetime.utcnow()
        for i in range(45):
            db.add(models.AutomationAuditLog(
                user_id=u_id,
                action=f"action_{i}",
                resource_type="shopping",
                details=f"Item {i}",
                actor="openclaw",
                status="success",
                created_at=base_time - timedelta(minutes=i),
            ))
        db.commit()

        app.dependency_overrides[get_db] = lambda: db
        try:
            session = TestClient(app)
            login = session.post(
                "/admin/login",
                data={"email": email, "password": "testpass123"},
                follow_redirects=False,
            )
            assert login.status_code in (302, 303)

            # Page 1 (20 items per page)
            page1 = session.get("/admin/automation")
            assert page1.status_code == 200, page1.text[:500]
            assert "Showing 1" in page1.text and "45" in page1.text
            assert "Page 1 / 3" in page1.text
            assert "action_0" in page1.text

            # Page 2
            page2 = session.get("/admin/automation?page=2")
            assert page2.status_code == 200
            assert "Showing 21" in page2.text and "45" in page2.text
            assert "Page 2 / 3" in page2.text

            # Page 3
            page3 = session.get("/admin/automation?page=3")
            assert page3.status_code == 200
            assert "Showing 41" in page3.text and "45" in page3.text
            assert "Page 3 / 3" in page3.text
        finally:
            app.dependency_overrides.clear()
    finally:
        db.close()



