"""Add is_default to finance_accounts (default account for new entries)

Revision ID: add_finance_account_default
Revises: add_pending_vault_owner
Create Date: 2026-09-04
"""
from alembic import op
import sqlalchemy as sa

revision = "add_finance_account_default"
down_revision = "add_pending_vault_owner"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "finance_accounts",
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("finance_accounts", "is_default")
