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
    # Make file_path nullable on documents (legacy column)
    with op.batch_alter_table('documents') as batch_op:
        batch_op.alter_column('file_path', existing_type=sa.String(500), nullable=True)

    # Create the new document_files table
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

    # Migrate existing documents: create a DocumentFile row for each document that has a file_path
    conn = op.get_bind()
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
