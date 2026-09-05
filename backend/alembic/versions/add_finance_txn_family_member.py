"""Add family_member_id to finance_transactions (optional per-member tagging)

Revision ID: add_finance_txn_family_member
Revises: add_finance_txn_hides
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = "add_finance_txn_family_member"
down_revision = "add_finance_txn_hides"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("finance_transactions") as batch_op:
        batch_op.add_column(
            sa.Column("family_member_id", sa.String(32), sa.ForeignKey("users.id"), nullable=True),
        )
        batch_op.create_index(
            "ix_finance_transactions_family_member_id", ["family_member_id"],
        )


def downgrade():
    with op.batch_alter_table("finance_transactions") as batch_op:
        batch_op.drop_index("ix_finance_transactions_family_member_id")
        batch_op.drop_column("family_member_id")
