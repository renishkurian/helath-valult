from sqlalchemy import create_engine, inspect, text

from app.schema import ensure_schema


def test_ensure_schema_on_legacy_sqlite(tmp_path):
    """An old healthvault.db (no role / extracted_text / etc.) is upgraded in place."""
    db = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{db}", connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE users (
                id VARCHAR(32) PRIMARY KEY,
                email VARCHAR(255) NOT NULL,
                hashed_password VARCHAR(255) NOT NULL,
                full_name VARCHAR(255) NOT NULL,
                created_at DATETIME
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE documents (
                id VARCHAR(32) PRIMARY KEY,
                person_id VARCHAR(32) NOT NULL,
                category VARCHAR(50) NOT NULL,
                title VARCHAR(255) NOT NULL,
                created_at DATETIME
            )
            """
        ))
        conn.execute(text(
            "INSERT INTO users (id, email, hashed_password, full_name) "
            "VALUES ('owner1', 'old@example.com', 'x', 'Old User')"
        ))

    ensure_schema(engine)
    ensure_schema(engine)  # second start must be a no-op

    insp = inspect(engine)
    users = {c["name"] for c in insp.get_columns("users")}
    docs = {c["name"] for c in insp.get_columns("documents")}
    tables = set(insp.get_table_names())

    assert {"role", "vault_owner_id", "totp_enabled", "last_seen_at", "blocked", "app_approve"} <= users
    assert {"extracted_text", "expiry_date", "tags", "version", "custom_category", "amount"} <= docs
    assert {"lab_readings", "device_tokens", "share_links", "share_accesses", "audit_logs", "document_versions", "medicines", "vaccinations", "visits", "claims", "share_packs", "vault_folders", "vault_items", "vault_sends", "vault_password_history", "login_attempts", "login_challenges"} <= tables
    challenges = {c["name"] for c in insp.get_columns("login_challenges")}
    assert "kind" in challenges

    with engine.connect() as conn:
        row = conn.execute(text("SELECT role, vault_owner_id FROM users WHERE id='owner1'")).one()
    assert row[0] == "owner"
    assert row[1] == "owner1"
