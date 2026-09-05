"""Seed superadmin global default emojis for the built-in category names

Populates finance_category_icon_defaults with sensible emoji for the
EXPENSE_CATEGORIES / INCOME_CATEGORIES names (see app/finance_ai.py) so
already-existing categories on every vault start showing an icon via the
existing _resolve_icon() fallback, without requiring a manual visit to
/admin/sa/category-icons. Only inserts a row when name_key is not already
present, so it never clobbers an icon a superadmin already set (or already
cleared) for that name, and is safe to re-run.

Revision ID: seed_category_icon_defaults
Revises: add_category_icons
Create Date: 2026-09-05
"""
import uuid
from alembic import op
import sqlalchemy as sa

revision = "seed_category_icon_defaults"
down_revision = "add_category_icons"
branch_labels = None
depends_on = None

DEFAULT_ICONS = {
    # expense
    "Food & dining": "🍽️",
    "Groceries": "🛒",
    "Transport": "🚌",
    "Fuel": "⛽",
    "Shopping": "🛍️",
    "Bills & utilities": "💡",
    "Rent": "🏠",
    "Health": "💊",
    "Education": "🎓",
    "Entertainment": "🎬",
    "Travel": "✈️",
    "Subscriptions": "🔁",
    "UPI / transfers": "🔄",
    "ATM / cash": "💵",
    "EMI / loans": "🏦",
    "Insurance": "🛡️",
    "Family": "👨‍👩‍👧",
    "Other": "🏷️",
    # income
    "Salary": "💰",
    "Freelance": "💻",
    "Business": "🏢",
    "Interest": "📈",
    "Refund": "↩️",
    "Gift": "🎁",
    "Other income": "🪙",
}


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "finance_category_icon_defaults" not in inspector.get_table_names():
        # Table not present yet (add_category_icons hasn't run for some reason) -- nothing to seed.
        return

    existing = {
        row[0]
        for row in conn.execute(sa.text("SELECT name_key FROM finance_category_icon_defaults")).fetchall()
    }
    for name, icon in DEFAULT_ICONS.items():
        key = name.strip().lower()
        if key in existing:
            continue
        conn.execute(
            sa.text(
                """
                INSERT INTO finance_category_icon_defaults (id, name_key, name_label, icon, updated_by, updated_at)
                VALUES (:id, :key, :label, :icon, NULL, datetime('now'))
                """
            ),
            {"id": uuid.uuid4().hex, "key": key, "label": name, "icon": icon},
        )


def downgrade():
    conn = op.get_bind()
    names = tuple(k.strip().lower() for k in DEFAULT_ICONS.keys())
    conn.execute(
        sa.text("DELETE FROM finance_category_icon_defaults WHERE name_key IN :keys").bindparams(
            sa.bindparam("keys", expanding=True)
        ),
        {"keys": names},
    )
