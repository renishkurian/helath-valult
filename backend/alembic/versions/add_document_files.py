"""Add document_files table

Revision ID: add_document_files
Create Date: 2026-08-12
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_document_files'
down_revision = None  # set this to your latest revision if you have one
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = sa.inspect(conn)

    # Make file_path nullable on documents (legacy column) -- skip if already nullable
    doc_cols = {c['name']: c for c in inspector.get_columns('documents')}
    if doc_cols.get('file_path') is not None and not doc_cols['file_path']['nullable']:
        with op.batch_alter_table('documents') as batch_op:
            batch_op.alter_column('file_path', existing_type=sa.String(500), nullable=True)

    # Create the new document_files table -- skip if it already exists (e.g. db was
    # bootstrapped via create_all on an older schema before alembic tracked it)
    table_existed = 'document_files' in inspector.get_table_names()
    if not table_existed:
        op.create_table(
            'document_files',
            sa.Column('id', sa.String(32), primary_key=True),
            sa.Column('document_id', sa.String(32), sa.ForeignKey('documents.id'), nullable=False, index=True),
            sa.Column('original_filename', sa.String(255), nullable=False),
            sa.Column('file_path', sa.String(500), nullable=False),
            sa.Column('file_type', sa.String(100), nullable=True),
            sa.Column('file_size', sa.Integer(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
        )

    # Migrate existing documents: create a DocumentFile row for each document that has a
    # file_path, but only if document_files is empty (avoid duplicating rows on rerun/
    # partially-applied databases).
    existing_count = conn.execute(sa.text("SELECT COUNT(*) FROM document_files")).scalar()
    if not existing_count:
        import uuid
        rows = conn.execute(sa.text("SELECT id, file_path, file_type, file_size FROM documents WHERE file_path IS NOT NULL AND file_path != ''")).fetchall()
        for row in rows:
            conn.execute(sa.text("""
                INSERT INTO document_files (id, document_id, original_filename, file_path, file_type, file_size, created_at)
                VALUES (:id, :doc_id, :fname, :fpath, :ftype, :fsize, datetime('now'))
            """), {
                "id": uuid.uuid4().hex,
                "doc_id": row[0],
                "fname": "document",
                "fpath": row[1],
                "ftype": row[2],
                "fsize": row[3],
            })


def downgrade():
    op.drop_table('document_files')
