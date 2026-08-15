"""Create tables on first run, and add any missing columns on upgrade.

SQLAlchemy create_all() only creates *new* tables. An existing SQLite file from
an older Health Vault install would keep the old users/documents shape and then
crash on the new viewer/OCR/version fields. This module is idempotent: safe on
a brand-new empty DB and on a Pi that has been running for months.
"""
from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.database import Base
from app import models  # noqa: F401 — register every table on Base.metadata

# column name -> SQL type fragment used by ALTER TABLE ... ADD COLUMN
_EXTRA_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "users": [
        ("role", "VARCHAR(20) NOT NULL DEFAULT 'owner'"),
        ("vault_owner_id", "VARCHAR(32)"),
        ("totp_secret_enc", "TEXT"),
        ("totp_enabled", "BOOLEAN NOT NULL DEFAULT 0"),
        ("app_approve", "BOOLEAN NOT NULL DEFAULT 0"),
        ("blocked", "BOOLEAN NOT NULL DEFAULT 0"),
        ("enabled_modules", "TEXT"),
        ("last_seen_at", "DATETIME"),
    ],
    "people": [
        ("allergies", "TEXT"),
        ("conditions", "TEXT"),
        ("emergency_name", "VARCHAR(255)"),
        ("emergency_phone", "VARCHAR(40)"),
        ("abha_id", "VARCHAR(64)"),
        ("ayushman_id", "VARCHAR(64)"),
        ("ice_token", "VARCHAR(64)"),
    ],
    "documents": [
        ("custom_category", "VARCHAR(255)"),
        ("expiry_date", "VARCHAR(20)"),
        ("tags", "VARCHAR(500)"),
        ("version", "INTEGER NOT NULL DEFAULT 1"),
        ("extracted_text", "TEXT"),
        ("amount", "VARCHAR(20)"),
        ("pinned", "BOOLEAN NOT NULL DEFAULT 0"),
    ],
    "document_files": [
        ("content_hash", "VARCHAR(64)"),
    ],
    "share_links": [
        ("pin_hash", "VARCHAR(255)"),
        ("idle_days", "INTEGER NOT NULL DEFAULT 14"),
    ],
    "finance_accounts": [
        ("credit_limit", "NUMERIC(14,2)"),
    ],
    "finance_categories": [
        ("account_id", "VARCHAR(32)"),
        ("parent_id", "VARCHAR(32)"),
    ],
    "finance_transactions": [
        ("txn_time", "VARCHAR(8)"),
        ("description", "TEXT"),
        ("payment_method", "VARCHAR(30)"),
        ("image_path", "VARCHAR(500)"),
        ("image_mime", "VARCHAR(80)"),
        ("emi_id", "VARCHAR(32)"),
    ],
    "finance_messages": [
        ("payment_method", "VARCHAR(30)"),
    ],
    "finance_emis": [
        ("kind", "VARCHAR(30) NOT NULL DEFAULT 'emi'"),
    ],
    "login_challenges": [
        ("kind", "VARCHAR(20) NOT NULL DEFAULT 'app'"),
    ],
    "vault_send_requests": [
        ("viewed_at", "DATETIME"),
        ("video_status", "VARCHAR(20) NOT NULL DEFAULT 'none'"),
        ("face_path", "VARCHAR(500)"),
        ("face_mime", "VARCHAR(80)"),
        ("face_captured_at", "DATETIME"),
    ],
    "vault_send_accesses": [
        ("email", "VARCHAR(255)"),
        ("request_id", "VARCHAR(32)"),
    ],
    "expense_analyser_connections": [
        ("enabled", "BOOLEAN NOT NULL DEFAULT 0"),
        ("hour", "INTEGER NOT NULL DEFAULT 6"),
    ],
    "ai_usage_logs": [
        ("request_text", "TEXT"),
        ("response_text", "TEXT"),
    ],
    "shop_lists": [
        ("deleted_at", "DATETIME"),
        ("finance_txn_id", "VARCHAR(32)"),
        ("finance_category_id", "VARCHAR(32)"),
    ],
}

_INDEXES: list[tuple[str, str, str]] = [
    ("ix_users_vault_owner_id", "users", "vault_owner_id"),
    ("ix_documents_expiry_date", "documents", "expiry_date"),
    ("ix_documents_custom_category", "documents", "custom_category"),
    ("ix_documents_tags", "documents", "tags"),
    ("ix_people_ice_token", "people", "ice_token"),
    ("ix_document_files_content_hash", "document_files", "content_hash"),
    ("ix_vault_items_user_id", "vault_items", "user_id"),
    ("ix_vault_items_folder_id", "vault_items", "folder_id"),
    ("ix_vault_items_item_type", "vault_items", "item_type"),
    ("ix_vault_folders_user_id", "vault_folders", "user_id"),
    ("ix_vault_sends_user_id", "vault_sends", "user_id"),
    ("ix_vault_sends_token", "vault_sends", "token"),
    ("ix_users_last_seen_at", "users", "last_seen_at"),
    ("ix_login_attempts_email", "login_attempts", "email"),
    ("ix_login_attempts_ip", "login_attempts", "ip"),
    ("ix_login_attempts_created_at", "login_attempts", "created_at"),
    ("ix_login_challenges_user_id", "login_challenges", "user_id"),
    ("ix_login_challenges_status", "login_challenges", "status"),
    ("ix_login_challenges_expires_at", "login_challenges", "expires_at"),
    ("ix_login_challenges_kind", "login_challenges", "kind"),
    ("ix_ai_chat_threads_user_id", "ai_chat_threads", "user_id"),
    ("ix_ai_chat_threads_updated_at", "ai_chat_threads", "updated_at"),
    ("ix_ai_chat_messages_thread_id", "ai_chat_messages", "thread_id"),
    ("ix_ai_usage_logs_user_id", "ai_usage_logs", "user_id"),
    ("ix_ai_usage_logs_client", "ai_usage_logs", "client"),
    ("ix_ai_usage_logs_created_at", "ai_usage_logs", "created_at"),
    ("ix_shop_statement_pdfs_user_id", "shop_statement_pdfs", "user_id"),
    ("ix_shop_statement_pdfs_gmail_message_id", "shop_statement_pdfs", "gmail_message_id"),
    ("ix_shop_statement_pdfs_status", "shop_statement_pdfs", "status"),
    ("ix_shop_lists_deleted_at", "shop_lists", "deleted_at"),
    ("ix_shop_lists_finance_txn_id", "shop_lists", "finance_txn_id"),
    ("ix_shop_lists_finance_category_id", "shop_lists", "finance_category_id"),
    ("ix_vault_send_chat_messages_request_id", "vault_send_chat_messages", "request_id"),
    ("ix_vault_send_chat_messages_created_at", "vault_send_chat_messages", "created_at"),
]


def _table_columns(engine: Engine, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}


def ensure_schema(engine: Engine) -> None:
    """Create missing tables, then patch missing columns/indexes, then backfill."""
    Base.metadata.create_all(bind=engine)

    dialect = engine.dialect.name
    tables = set(inspect(engine).get_table_names())

    with engine.begin() as conn:
        for table, columns in _EXTRA_COLUMNS.items():
            if table not in tables:
                continue
            have = _table_columns(engine, table)
            for name, ddl in columns:
                if name in have:
                    continue
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))

        if "users" in tables:
            conn.execute(text(
                "UPDATE users SET vault_owner_id = id "
                "WHERE vault_owner_id IS NULL OR vault_owner_id = ''"
            ))
            conn.execute(text(
                "UPDATE users SET role = 'owner' "
                "WHERE role IS NULL OR role = ''"
            ))

        if dialect == "mysql" and "reminders" in tables:
            try:
                conn.execute(text(
                    "ALTER TABLE reminders MODIFY COLUMN repeat_rule "
                    "ENUM('none','daily','weekly','monthly','yearly') "
                    "NOT NULL DEFAULT 'none'"
                ))
            except Exception:
                pass

    tables = set(inspect(engine).get_table_names())
    with engine.begin() as conn:
        for index_name, table, column in _INDEXES:
            if table not in tables:
                continue
            have_cols = _table_columns(engine, table)
            if column not in have_cols:
                continue
            existing_idx = {i["name"] for i in inspect(engine).get_indexes(table)}
            if index_name in existing_idx:
                continue
            try:
                conn.execute(text(f"CREATE INDEX {index_name} ON {table} ({column})"))
            except Exception:
                pass

        # One-time copy: Money Manager AI keys → shared ai_providers
        if "finance_ai_providers" in tables and "ai_providers" in tables:
            try:
                conn.execute(text(
                    "INSERT INTO ai_providers "
                    "(id, user_id, name, kind, api_key_enc, base_url, model, is_default, enabled, created_at) "
                    "SELECT id, user_id, name, kind, api_key_enc, base_url, model, is_default, enabled, created_at "
                    "FROM finance_ai_providers "
                    "WHERE id NOT IN (SELECT id FROM ai_providers)"
                ))
            except Exception:
                pass
