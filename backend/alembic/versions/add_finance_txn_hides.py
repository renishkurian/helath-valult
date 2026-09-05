"""Add finance_txn_hides table (per-member transaction hiding for family vault)

Revision ID: add_finance_txn_hides
Revises: add_finance_account_default
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = "add_finance_txn_hides"
down_revision = "add_finance_account_default"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "finance_txn_hides",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("vault_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("transaction_id", sa.String(32), sa.ForeignKey("finance_transactions.id"), nullable=False, index=True),
        sa.Column("to_user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("transaction_id", "to_user_id", name="uq_finance_txn_hide_target"),
    )


def downgrade():
    op.drop_table("finance_txn_hides")
