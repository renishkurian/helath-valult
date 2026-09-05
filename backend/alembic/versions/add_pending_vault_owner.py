"""Add pending_vault_owner_id (defer vault join until invite accepted)

Revision ID: add_pending_vault_owner
Revises: add_roles_ocr_labs
Create Date: 2026-09-04
"""
from alembic import op
import sqlalchemy as sa

revision = "add_pending_vault_owner"
down_revision = "add_roles_ocr_labs"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    user_cols = {c['name'] for c in inspector.get_columns('users')}
    user_idx = {i['name'] for i in inspector.get_indexes('users')}

    if 'pending_vault_owner_id' not in user_cols:
        op.add_column(
            "users",
            sa.Column("pending_vault_owner_id", sa.String(32), sa.ForeignKey("users.id"), nullable=True),
        )
    if op.f("ix_users_pending_vault_owner_id") not in user_idx:
        op.create_index(
            op.f("ix_users_pending_vault_owner_id"), "users", ["pending_vault_owner_id"], unique=False
        )
    # Repair any accounts that were already hijacked by the pre-fix invite flow:
    # a user with family_status == 'pending' whose vault_owner_id != own id
    # got repointed at invite-send time. Move that back into pending_vault_owner_id
    # and restore self-ownership so pre-existing pending invitees regain access
    # to their own data immediately after migration (they still see the invite
    # and can accept/reject normally).
    op.execute(
        """
        UPDATE users
        SET pending_vault_owner_id = vault_owner_id,
            vault_owner_id = id
        WHERE family_status = 'pending' AND vault_owner_id IS NOT NULL AND vault_owner_id != id
        """
    )


def downgrade():
    op.drop_index(op.f("ix_users_pending_vault_owner_id"), table_name="users")
    op.drop_column("users", "pending_vault_owner_id")
