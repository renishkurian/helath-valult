"""Viewer role, OCR text, lab_readings, device_tokens

Revision ID: add_roles_ocr_labs
Revises: add_expiry_tags_share_audit
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa

revision = "add_roles_ocr_labs"
down_revision = "add_expiry_tags_share_audit"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    user_cols = {c['name'] for c in inspector.get_columns('users')}
    user_idx = {i['name'] for i in inspector.get_indexes('users')}

    if 'role' not in user_cols:
        op.add_column("users", sa.Column("role", sa.String(20), nullable=False, server_default="owner"))
    if 'vault_owner_id' not in user_cols:
        op.add_column("users", sa.Column("vault_owner_id", sa.String(32), sa.ForeignKey("users.id"), nullable=True))
    if op.f("ix_users_vault_owner_id") not in user_idx:
        op.create_index(op.f("ix_users_vault_owner_id"), "users", ["vault_owner_id"], unique=False)
    op.execute("UPDATE users SET vault_owner_id = id WHERE vault_owner_id IS NULL")

    doc_cols = {c['name'] for c in inspector.get_columns('documents')}
    if 'extracted_text' not in doc_cols:
        op.add_column("documents", sa.Column("extracted_text", sa.Text(), nullable=True))

    if 'lab_readings' not in existing_tables:
        op.create_table(
            "lab_readings",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("person_id", sa.String(32), sa.ForeignKey("people.id"), nullable=False, index=True),
            sa.Column("document_id", sa.String(32), sa.ForeignKey("documents.id"), nullable=True, index=True),
            sa.Column("metric", sa.String(40), nullable=False, index=True),
            sa.Column("value", sa.String(20), nullable=False),
            sa.Column("unit", sa.String(20), nullable=True),
            sa.Column("measured_at", sa.String(20), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )

    if 'device_tokens' not in existing_tables:
        op.create_table(
            "device_tokens",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False, index=True),
            sa.Column("token", sa.String(512), nullable=False, unique=True),
            sa.Column("platform", sa.String(20), nullable=False, server_default="android"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )


def downgrade():
    op.drop_table("device_tokens")
    op.drop_table("lab_readings")
    op.drop_column("documents", "extracted_text")
    op.drop_index(op.f("ix_users_vault_owner_id"), table_name="users")
    op.drop_column("users", "vault_owner_id")
    op.drop_column("users", "role")
