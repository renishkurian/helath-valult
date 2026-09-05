"""Add category icon override + superadmin-managed global icon defaults

Revision ID: add_category_icons
Revises: add_finance_txn_family_member
Create Date: 2026-09-05
"""
from alembic import op
import sqlalchemy as sa

revision = "add_category_icons"
down_revision = "add_finance_txn_family_member"
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    cols = {c["name"] for c in inspector.get_columns("finance_categories")}
    if "icon" not in cols:
        with op.batch_alter_table("finance_categories") as batch_op:
            batch_op.add_column(sa.Column("icon", sa.String(16), nullable=True))

    if "finance_category_icon_defaults" not in inspector.get_table_names():
        op.create_table(
            "finance_category_icon_defaults",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("name_key", sa.String(120), nullable=False, unique=True),
            sa.Column("name_label", sa.String(120), nullable=False),
            sa.Column("icon", sa.String(16), nullable=False),
            sa.Column("updated_by", sa.String(32), sa.ForeignKey("users.id"), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index(
            "ix_finance_category_icon_defaults_name_key",
            "finance_category_icon_defaults", ["name_key"], unique=True,
        )


def downgrade():
    op.drop_index("ix_finance_category_icon_defaults_name_key", table_name="finance_category_icon_defaults")
    op.drop_table("finance_category_icon_defaults")
    with op.batch_alter_table("finance_categories") as batch_op:
        batch_op.drop_column("icon")
