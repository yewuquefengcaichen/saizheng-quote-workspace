"""enable pgvector and add embedding vector

Revision ID: 20260415_0005
Revises: 20260415_0004
Create Date: 2026-04-15 22:20:00
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


# revision identifiers, used by Alembic.
revision = '20260415_0005'
down_revision = '20260415_0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.add_column('image_embeddings', sa.Column('embedding_vector', Vector(dim=128), nullable=True))
    op.execute(
        'CREATE INDEX IF NOT EXISTS ix_image_embeddings_embedding_vector_hnsw '
        'ON image_embeddings USING hnsw (embedding_vector vector_cosine_ops)'
    )


def downgrade() -> None:
    op.execute('DROP INDEX IF EXISTS ix_image_embeddings_embedding_vector_hnsw')
    op.drop_column('image_embeddings', 'embedding_vector')
