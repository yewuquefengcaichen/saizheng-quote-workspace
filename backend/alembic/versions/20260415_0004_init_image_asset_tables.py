"""init image asset tables

Revision ID: 20260415_0004
Revises: 20260415_0003
Create Date: 2026-04-15 23:58:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260415_0004'
down_revision = '20260415_0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'image_assets',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('storage_backend', sa.String(length=32), server_default='local_fs', nullable=False),
        sa.Column('storage_bucket', sa.String(length=120), nullable=True),
        sa.Column('storage_key', sa.String(length=255), nullable=False),
        sa.Column('file_ext', sa.String(length=16), nullable=True),
        sa.Column('mime_type', sa.String(length=64), nullable=True),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('file_size', sa.BigInteger(), nullable=True),
        sa.Column('phash', sa.String(length=32), nullable=True),
        sa.Column('dhash', sa.String(length=32), nullable=True),
        sa.Column('source_url', sa.Text(), nullable=True),
        sa.Column('resolved_url', sa.Text(), nullable=True),
        sa.Column('archive_status', sa.String(length=32), server_default='ready', nullable=False),
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sha256'),
        sa.UniqueConstraint('storage_key'),
    )
    op.create_index(op.f('ix_image_assets_archive_status'), 'image_assets', ['archive_status'], unique=False)
    op.create_index(op.f('ix_image_assets_dhash'), 'image_assets', ['dhash'], unique=False)
    op.create_index(op.f('ix_image_assets_phash'), 'image_assets', ['phash'], unique=False)
    op.create_index(op.f('ix_image_assets_sha256'), 'image_assets', ['sha256'], unique=True)

    op.create_table(
        'image_embeddings',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column('asset_id', sa.BigInteger(), nullable=False),
        sa.Column('provider', sa.String(length=64), server_default='pending', nullable=False),
        sa.Column('model_name', sa.String(length=128), nullable=False),
        sa.Column('vector_dim', sa.Integer(), nullable=True),
        sa.Column('vector_status', sa.String(length=32), server_default='pending', nullable=False),
        sa.Column('embedding_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('source_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['image_assets.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('asset_id', 'provider', 'model_name', name='uq_image_embeddings_asset_provider_model'),
    )
    op.create_index(op.f('ix_image_embeddings_asset_id'), 'image_embeddings', ['asset_id'], unique=False)
    op.create_index(op.f('ix_image_embeddings_vector_status'), 'image_embeddings', ['vector_status'], unique=False)

    op.add_column('product_images', sa.Column('asset_id', sa.BigInteger(), nullable=True))
    op.add_column('product_images', sa.Column('resolved_url', sa.Text(), nullable=True))
    op.add_column('product_images', sa.Column('download_attempts', sa.Integer(), server_default='0', nullable=False))
    op.add_column('product_images', sa.Column('last_downloaded_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('product_images', sa.Column('sync_message', sa.Text(), nullable=True))
    op.create_index(op.f('ix_product_images_asset_id'), 'product_images', ['asset_id'], unique=False)
    op.create_foreign_key(
        'fk_product_images_asset_id_image_assets',
        'product_images',
        'image_assets',
        ['asset_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_product_images_asset_id_image_assets', 'product_images', type_='foreignkey')
    op.drop_index(op.f('ix_product_images_asset_id'), table_name='product_images')
    op.drop_column('product_images', 'sync_message')
    op.drop_column('product_images', 'last_downloaded_at')
    op.drop_column('product_images', 'download_attempts')
    op.drop_column('product_images', 'resolved_url')
    op.drop_column('product_images', 'asset_id')

    op.drop_index(op.f('ix_image_embeddings_vector_status'), table_name='image_embeddings')
    op.drop_index(op.f('ix_image_embeddings_asset_id'), table_name='image_embeddings')
    op.drop_table('image_embeddings')

    op.drop_index(op.f('ix_image_assets_sha256'), table_name='image_assets')
    op.drop_index(op.f('ix_image_assets_phash'), table_name='image_assets')
    op.drop_index(op.f('ix_image_assets_dhash'), table_name='image_assets')
    op.drop_index(op.f('ix_image_assets_archive_status'), table_name='image_assets')
    op.drop_table('image_assets')
