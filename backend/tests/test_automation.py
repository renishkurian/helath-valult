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
