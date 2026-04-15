"""init core domain tables

Revision ID: 20260415_0002
Revises: 20260415_0001
Create Date: 2026-04-15 20:10:00
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260415_0002'
down_revision = '20260415_0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'brands',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('normalized_name', sa.String(length=120), nullable=True),
        sa.Column('code', sa.String(length=64), nullable=True),
        sa.Column('source_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_index(op.f('ix_brands_normalized_name'), 'brands', ['normalized_name'], unique=False)

    op.create_table(
        'categories',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('normalized_name', sa.String(length=120), nullable=True),
        sa.Column('parent_id', sa.BigInteger(), nullable=True),
        sa.Column('level', sa.Integer(), server_default='1', nullable=False),
        sa.Column('path', sa.String(length=500), nullable=True),
        sa.Column('source_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['parent_id'], ['categories.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_categories_normalized_name'), 'categories', ['normalized_name'], unique=False)
    op.create_index(op.f('ix_categories_parent_id'), 'categories', ['parent_id'], unique=False)

    op.create_table(
        'suppliers',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('normalized_name', sa.String(length=160), nullable=True),
        sa.Column('external_ref', sa.String(length=120), nullable=True),
        sa.Column('contact_name', sa.String(length=120), nullable=True),
        sa.Column('contact_phone', sa.String(length=64), nullable=True),
        sa.Column('source_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_index(op.f('ix_suppliers_external_ref'), 'suppliers', ['external_ref'], unique=False)
    op.create_index(op.f('ix_suppliers_normalized_name'), 'suppliers', ['normalized_name'], unique=False)

    op.create_table(
        'products',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column('source_type', sa.String(length=50), server_default='manual_import', nullable=False),
        sa.Column('external_product_id', sa.String(length=120), nullable=True),
        sa.Column('product_code', sa.String(length=120), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('normalized_name', sa.String(length=255), nullable=True),
        sa.Column('brand_id', sa.BigInteger(), nullable=True),
        sa.Column('category_id', sa.BigInteger(), nullable=True),
        sa.Column('supplier_id', sa.BigInteger(), nullable=True),
        sa.Column('status', sa.String(length=32), server_default='active', nullable=False),
        sa.Column('unit', sa.String(length=32), nullable=True),
        sa.Column('currency', sa.String(length=8), server_default='CNY', nullable=False),
        sa.Column('reference_price', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('primary_image_url', sa.Text(), nullable=True),
        sa.Column('search_text', sa.Text(), nullable=True),
        sa.Column('source_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['supplier_id'], ['suppliers.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source_type', 'external_product_id', name='uq_products_source_external_product'),
    )
    op.create_index(op.f('ix_products_brand_id'), 'products', ['brand_id'], unique=False)
    op.create_index(op.f('ix_products_category_id'), 'products', ['category_id'], unique=False)
    op.create_index(op.f('ix_products_external_product_id'), 'products', ['external_product_id'], unique=False)
    op.create_index(op.f('ix_products_normalized_name'), 'products', ['normalized_name'], unique=False)
    op.create_index(op.f('ix_products_product_code'), 'products', ['product_code'], unique=False)
    op.create_index(op.f('ix_products_supplier_id'), 'products', ['supplier_id'], unique=False)

    op.create_table(
        'product_variants',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column('product_id', sa.BigInteger(), nullable=False),
        sa.Column('external_variant_id', sa.String(length=120), nullable=True),
        sa.Column('sku_code', sa.String(length=120), nullable=True),
        sa.Column('variant_name', sa.String(length=255), nullable=True),
        sa.Column('spec_text', sa.Text(), nullable=True),
        sa.Column('normalized_spec', sa.Text(), nullable=True),
        sa.Column('barcode', sa.String(length=64), nullable=True),
        sa.Column('currency', sa.String(length=8), server_default='CNY', nullable=False),
        sa.Column('sale_price', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('cost_price', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('stock_qty', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(length=32), server_default='active', nullable=False),
        sa.Column('attributes_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('source_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('product_id', 'external_variant_id', name='uq_product_variants_product_external_variant'),
    )
    op.create_index(op.f('ix_product_variants_external_variant_id'), 'product_variants', ['external_variant_id'], unique=False)
    op.create_index(op.f('ix_product_variants_product_id'), 'product_variants', ['product_id'], unique=False)
    op.create_index(op.f('ix_product_variants_sku_code'), 'product_variants', ['sku_code'], unique=False)

    op.create_table(
        'product_images',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column('product_id', sa.BigInteger(), nullable=True),
        sa.Column('variant_id', sa.BigInteger(), nullable=True),
        sa.Column('image_role', sa.String(length=32), server_default='gallery', nullable=False),
        sa.Column('source_url', sa.Text(), nullable=False),
        sa.Column('storage_key', sa.String(length=255), nullable=True),
        sa.Column('mime_type', sa.String(length=64), nullable=True),
        sa.Column('width', sa.Integer(), nullable=True),
        sa.Column('height', sa.Integer(), nullable=True),
        sa.Column('file_size', sa.BigInteger(), nullable=True),
        sa.Column('sha256', sa.String(length=64), nullable=True),
        sa.Column('phash', sa.String(length=32), nullable=True),
        sa.Column('dhash', sa.String(length=32), nullable=True),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_primary', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('sync_status', sa.String(length=32), server_default='pending', nullable=False),
        sa.Column('source_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('product_id IS NOT NULL OR variant_id IS NOT NULL', name='ck_product_images_has_owner'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['variant_id'], ['product_variants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_product_images_dhash'), 'product_images', ['dhash'], unique=False)
    op.create_index(op.f('ix_product_images_phash'), 'product_images', ['phash'], unique=False)
    op.create_index(op.f('ix_product_images_product_id'), 'product_images', ['product_id'], unique=False)
    op.create_index(op.f('ix_product_images_sha256'), 'product_images', ['sha256'], unique=False)
    op.create_index(op.f('ix_product_images_variant_id'), 'product_images', ['variant_id'], unique=False)

    op.create_table(
        'product_attributes',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column('product_id', sa.BigInteger(), nullable=False),
        sa.Column('variant_id', sa.BigInteger(), nullable=True),
        sa.Column('attr_name', sa.String(length=120), nullable=False),
        sa.Column('attr_value', sa.String(length=255), nullable=False),
        sa.Column('normalized_value', sa.String(length=255), nullable=True),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['variant_id'], ['product_variants.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_product_attributes_product_id'), 'product_attributes', ['product_id'], unique=False)
    op.create_index(op.f('ix_product_attributes_variant_id'), 'product_attributes', ['variant_id'], unique=False)

    op.create_table(
        'quote_batches',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column('public_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_filename', sa.String(length=255), nullable=True),
        sa.Column('source_file_sha256', sa.String(length=64), nullable=True),
        sa.Column('source_type', sa.String(length=50), server_default='excel', nullable=False),
        sa.Column('import_status', sa.String(length=32), server_default='pending', nullable=False),
        sa.Column('parse_status', sa.String(length=32), server_default='pending', nullable=False),
        sa.Column('total_items', sa.Integer(), server_default='0', nullable=False),
        sa.Column('confirmed_items', sa.Integer(), server_default='0', nullable=False),
        sa.Column('unmatched_items', sa.Integer(), server_default='0', nullable=False),
        sa.Column('source_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('imported_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('parsed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('public_id'),
    )

    op.create_table(
        'quote_items',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column('batch_id', sa.BigInteger(), nullable=False),
        sa.Column('row_number', sa.Integer(), nullable=False),
        sa.Column('raw_name', sa.String(length=255), nullable=False),
        sa.Column('raw_spec', sa.Text(), nullable=True),
        sa.Column('raw_brand', sa.String(length=120), nullable=True),
        sa.Column('raw_model', sa.String(length=120), nullable=True),
        sa.Column('quantity', sa.Numeric(precision=14, scale=4), nullable=True),
        sa.Column('unit', sa.String(length=32), nullable=True),
        sa.Column('target_price', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('currency', sa.String(length=8), server_default='CNY', nullable=False),
        sa.Column('normalized_name', sa.String(length=255), nullable=True),
        sa.Column('normalized_spec', sa.Text(), nullable=True),
        sa.Column('selected_product_id', sa.BigInteger(), nullable=True),
        sa.Column('selected_variant_id', sa.BigInteger(), nullable=True),
        sa.Column('match_status', sa.String(length=32), server_default='pending', nullable=False),
        sa.Column('quote_status', sa.String(length=32), server_default='unconfirmed', nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('source_payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['batch_id'], ['quote_batches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['selected_product_id'], ['products.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['selected_variant_id'], ['product_variants.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('batch_id', 'row_number', name='uq_quote_items_batch_row'),
    )
    op.create_index(op.f('ix_quote_items_batch_id'), 'quote_items', ['batch_id'], unique=False)
    op.create_index(op.f('ix_quote_items_normalized_name'), 'quote_items', ['normalized_name'], unique=False)
    op.create_index(op.f('ix_quote_items_selected_product_id'), 'quote_items', ['selected_product_id'], unique=False)
    op.create_index(op.f('ix_quote_items_selected_variant_id'), 'quote_items', ['selected_variant_id'], unique=False)

    op.create_table(
        'quote_item_candidates',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column('quote_item_id', sa.BigInteger(), nullable=False),
        sa.Column('product_id', sa.BigInteger(), nullable=True),
        sa.Column('variant_id', sa.BigInteger(), nullable=True),
        sa.Column('candidate_rank', sa.Integer(), nullable=False),
        sa.Column('score', sa.Numeric(precision=8, scale=4), nullable=True),
        sa.Column('source', sa.String(length=50), nullable=True),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('score_breakdown', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_selected', sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['quote_item_id'], ['quote_items.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['variant_id'], ['product_variants.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('quote_item_id', 'candidate_rank', name='uq_quote_item_candidates_rank'),
    )
    op.create_index(op.f('ix_quote_item_candidates_product_id'), 'quote_item_candidates', ['product_id'], unique=False)
    op.create_index(op.f('ix_quote_item_candidates_quote_item_id'), 'quote_item_candidates', ['quote_item_id'], unique=False)
    op.create_index(op.f('ix_quote_item_candidates_variant_id'), 'quote_item_candidates', ['variant_id'], unique=False)

    op.create_table(
        'sync_jobs',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column('public_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('job_type', sa.String(length=50), nullable=False),
        sa.Column('source_name', sa.String(length=64), server_default='mall', nullable=False),
        sa.Column('trigger_mode', sa.String(length=32), server_default='manual', nullable=False),
        sa.Column('status', sa.String(length=32), server_default='pending', nullable=False),
        sa.Column('requested_by', sa.String(length=120), nullable=True),
        sa.Column('total_steps', sa.Integer(), server_default='0', nullable=False),
        sa.Column('completed_steps', sa.Integer(), server_default='0', nullable=False),
        sa.Column('stats_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('public_id'),
    )

    op.create_table(
        'sync_job_logs',
        sa.Column('id', sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column('job_id', sa.BigInteger(), nullable=False),
        sa.Column('level', sa.String(length=16), server_default='info', nullable=False),
        sa.Column('event_type', sa.String(length=64), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('context_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['job_id'], ['sync_jobs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_sync_job_logs_job_id'), 'sync_job_logs', ['job_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_sync_job_logs_job_id'), table_name='sync_job_logs')
    op.drop_table('sync_job_logs')
    op.drop_table('sync_jobs')

    op.drop_index(op.f('ix_quote_item_candidates_variant_id'), table_name='quote_item_candidates')
    op.drop_index(op.f('ix_quote_item_candidates_quote_item_id'), table_name='quote_item_candidates')
    op.drop_index(op.f('ix_quote_item_candidates_product_id'), table_name='quote_item_candidates')
    op.drop_table('quote_item_candidates')

    op.drop_index(op.f('ix_quote_items_selected_variant_id'), table_name='quote_items')
    op.drop_index(op.f('ix_quote_items_selected_product_id'), table_name='quote_items')
    op.drop_index(op.f('ix_quote_items_normalized_name'), table_name='quote_items')
    op.drop_index(op.f('ix_quote_items_batch_id'), table_name='quote_items')
    op.drop_table('quote_items')
    op.drop_table('quote_batches')

    op.drop_index(op.f('ix_product_attributes_variant_id'), table_name='product_attributes')
    op.drop_index(op.f('ix_product_attributes_product_id'), table_name='product_attributes')
    op.drop_table('product_attributes')

    op.drop_index(op.f('ix_product_images_variant_id'), table_name='product_images')
    op.drop_index(op.f('ix_product_images_sha256'), table_name='product_images')
    op.drop_index(op.f('ix_product_images_product_id'), table_name='product_images')
    op.drop_index(op.f('ix_product_images_phash'), table_name='product_images')
    op.drop_index(op.f('ix_product_images_dhash'), table_name='product_images')
    op.drop_table('product_images')

    op.drop_index(op.f('ix_product_variants_sku_code'), table_name='product_variants')
    op.drop_index(op.f('ix_product_variants_product_id'), table_name='product_variants')
    op.drop_index(op.f('ix_product_variants_external_variant_id'), table_name='product_variants')
    op.drop_table('product_variants')

    op.drop_index(op.f('ix_products_supplier_id'), table_name='products')
    op.drop_index(op.f('ix_products_product_code'), table_name='products')
    op.drop_index(op.f('ix_products_normalized_name'), table_name='products')
    op.drop_index(op.f('ix_products_external_product_id'), table_name='products')
    op.drop_index(op.f('ix_products_category_id'), table_name='products')
    op.drop_index(op.f('ix_products_brand_id'), table_name='products')
    op.drop_table('products')

    op.drop_index(op.f('ix_suppliers_normalized_name'), table_name='suppliers')
    op.drop_index(op.f('ix_suppliers_external_ref'), table_name='suppliers')
    op.drop_table('suppliers')

    op.drop_index(op.f('ix_categories_parent_id'), table_name='categories')
    op.drop_index(op.f('ix_categories_normalized_name'), table_name='categories')
    op.drop_table('categories')

    op.drop_index(op.f('ix_brands_normalized_name'), table_name='brands')
    op.drop_table('brands')
