"""Add custom_category to documents

Revision ID: add_custom_category
Create Date: 2026-08-12
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_custom_category'
down_revision = 'add_document_files'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('documents', sa.Column('custom_category', sa.String(255), nullable=True))
    op.create_index(op.f('ix_documents_custom_category'), 'documents', ['custom_category'], unique=False)

def downgrade():
    op.drop_index(op.f('ix_documents_custom_category'), table_name='documents')
    op.drop_column('documents', 'custom_category')
