"""Add document expiry/tags/version, document_versions, share_links, audit_logs

Revision ID: add_expiry_tags_share_audit
Create Date: 2026-08-12
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_expiry_tags_share_audit'
down_revision = 'add_custom_category'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    doc_cols = {c['name'] for c in inspector.get_columns('documents')}
    doc_idx = {i['name'] for i in inspector.get_indexes('documents')}

    if 'expiry_date' not in doc_cols:
        op.add_column('documents', sa.Column('expiry_date', sa.String(20), nullable=True))
    if op.f('ix_documents_expiry_date') not in doc_idx:
        op.create_index(op.f('ix_documents_expiry_date'), 'documents', ['expiry_date'], unique=False)
    if 'tags' not in doc_cols:
        op.add_column('documents', sa.Column('tags', sa.String(500), nullable=True))
    if 'version' not in doc_cols:
        op.add_column('documents', sa.Column('version', sa.Integer(), nullable=False, server_default='1'))

    if 'document_versions' not in existing_tables:
        op.create_table(
            'document_versions',
            sa.Column('id', sa.String(32), primary_key=True),
            sa.Column('document_id', sa.String(32), sa.ForeignKey('documents.id'), nullable=False, index=True),
            sa.Column('version', sa.Integer(), nullable=False),
            sa.Column('title', sa.String(255), nullable=False),
            sa.Column('notes_enc', sa.Text(), nullable=True),
            sa.Column('files_json', sa.Text(), nullable=False),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )

    if 'share_links' not in existing_tables:
        op.create_table(
            'share_links',
            sa.Column('id', sa.String(32), primary_key=True),
            sa.Column('token', sa.String(64), unique=True, index=True, nullable=False),
            sa.Column('document_id', sa.String(32), sa.ForeignKey('documents.id'), nullable=False, index=True),
            sa.Column('created_by', sa.String(32), sa.ForeignKey('users.id'), nullable=False),
            sa.Column('expires_at', sa.DateTime(), nullable=False),
            sa.Column('max_views', sa.Integer(), nullable=True),
            sa.Column('view_count', sa.Integer(), nullable=False, server_default='0'),
            sa.Column('revoked', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )

    if 'audit_logs' not in existing_tables:
        op.create_table(
            'audit_logs',
            sa.Column('id', sa.String(32), primary_key=True),
            sa.Column('user_id', sa.String(32), sa.ForeignKey('users.id'), nullable=True, index=True),
            sa.Column('document_id', sa.String(32), sa.ForeignKey('documents.id'), nullable=True, index=True),
            sa.Column('action', sa.Enum('view', 'download', 'share_create', 'share_view', name='auditaction'), nullable=False),
            sa.Column('detail', sa.String(255), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True, index=True),
        )

    # RepeatRule enum gains 'yearly' — MySQL enum column needs to be altered explicitly.
    # SQLite doesn't enforce column-level enum constraints, so this is a no-op there;
    # wrap in try/except so a rerun (or a db that already has the wider enum) can't fail it.
    try:
        op.alter_column(
            'reminders', 'repeat_rule',
            existing_type=sa.Enum('none', 'daily', 'weekly', 'monthly', name='repeatrule'),
            type_=sa.Enum('none', 'daily', 'weekly', 'monthly', 'yearly', name='repeatrule'),
        )
    except Exception:
        pass


def downgrade():
    op.alter_column(
        'reminders', 'repeat_rule',
        existing_type=sa.Enum('none', 'daily', 'weekly', 'monthly', 'yearly', name='repeatrule'),
        type_=sa.Enum('none', 'daily', 'weekly', 'monthly', name='repeatrule'),
    )
    op.drop_table('audit_logs')
    op.drop_table('share_links')
    op.drop_table('document_versions')
    op.drop_column('documents', 'version')
    op.drop_column('documents', 'tags')
    op.drop_index(op.f('ix_documents_expiry_date'), table_name='documents')
    op.drop_column('documents', 'expiry_date')
