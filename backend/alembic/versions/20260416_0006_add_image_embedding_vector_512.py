"""add 512d image embedding vector column

Revision ID: 20260416_0006
Revises: 20260415_0005
Create Date: 2026-04-16 18:30:00
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = '20260416_0006'
down_revision = '20260415_0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.execute('ALTER TABLE image_embeddings ADD COLUMN IF NOT EXISTS embedding_vector_512 vector(512)')
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_image_embeddings_embedding_vector_512_hnsw '
        'ON image_embeddings USING hnsw (embedding_vector_512 vector_cosine_ops)'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS ix_image_embeddings_embedding_vector_512_hnsw')
    op.execute('ALTER TABLE image_embeddings DROP COLUMN IF EXISTS embedding_vector_512')
