from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, false
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.models.base import ActiveFlagMixin, Base, IdentityPrimaryKeyMixin, TimestampMixin


class Brand(IdentityPrimaryKeyMixin, ActiveFlagMixin, TimestampMixin, Base):
    __tablename__ = 'brands'

    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    normalized_name: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    products: Mapped[list['Product']] = relationship(back_populates='brand')


class Category(IdentityPrimaryKeyMixin, ActiveFlagMixin, TimestampMixin, Base):
    __tablename__ = 'categories'

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_name: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey('categories.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    parent: Mapped['Category | None'] = relationship(remote_side=lambda: [Category.id], back_populates='children')
    children: Mapped[list['Category']] = relationship(back_populates='parent')
    products: Mapped[list['Product']] = relationship(back_populates='category')


class Supplier(IdentityPrimaryKeyMixin, ActiveFlagMixin, TimestampMixin, Base):
    __tablename__ = 'suppliers'

    name: Mapped[str] = mapped_column(String(160), unique=True, nullable=False)
    normalized_name: Mapped[str | None] = mapped_column(String(160), index=True, nullable=True)
    external_ref: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    products: Mapped[list['Product']] = relationship(back_populates='supplier')


class Product(IdentityPrimaryKeyMixin, ActiveFlagMixin, TimestampMixin, Base):
    __tablename__ = 'products'

    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default='manual_import', server_default='manual_import')
    external_product_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    product_code: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    brand_id: Mapped[int | None] = mapped_column(ForeignKey('brands.id', ondelete='SET NULL'), nullable=True, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey('categories.id', ondelete='SET NULL'), nullable=True, index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey('suppliers.id', ondelete='SET NULL'), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='active', server_default='active')
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default='CNY', server_default='CNY')
    reference_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    primary_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    search_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    brand: Mapped['Brand | None'] = relationship(back_populates='products')
    category: Mapped['Category | None'] = relationship(back_populates='products')
    supplier: Mapped['Supplier | None'] = relationship(back_populates='products')
    variants: Mapped[list['ProductVariant']] = relationship(back_populates='product', cascade='all, delete-orphan')
    images: Mapped[list['ProductImage']] = relationship(back_populates='product', cascade='all, delete-orphan')
    attributes: Mapped[list['ProductAttribute']] = relationship(back_populates='product', cascade='all, delete-orphan')


class ProductVariant(IdentityPrimaryKeyMixin, ActiveFlagMixin, TimestampMixin, Base):
    __tablename__ = 'product_variants'

    product_id: Mapped[int] = mapped_column(ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)
    external_variant_id: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    sku_code: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    variant_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    spec_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_spec: Mapped[str | None] = mapped_column(Text, nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(64), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default='CNY', server_default='CNY')
    sale_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    cost_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    stock_qty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='active', server_default='active')
    attributes_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    source_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    product: Mapped['Product'] = relationship(back_populates='variants')
    images: Mapped[list['ProductImage']] = relationship(back_populates='variant')
    attributes: Mapped[list['ProductAttribute']] = relationship(back_populates='variant')


class ProductImage(IdentityPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'product_images'

    product_id: Mapped[int | None] = mapped_column(ForeignKey('products.id', ondelete='CASCADE'), nullable=True, index=True)
    variant_id: Mapped[int | None] = mapped_column(ForeignKey('product_variants.id', ondelete='CASCADE'), nullable=True, index=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey('image_assets.id', ondelete='SET NULL'), nullable=True, index=True)
    image_role: Mapped[str] = mapped_column(String(32), nullable=False, default='gallery', server_default='gallery')
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    phash: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    dhash: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    is_primary: Mapped[bool] = mapped_column(nullable=False, default=False, server_default=false())
    sync_status: Mapped[str] = mapped_column(String(32), nullable=False, default='pending', server_default='pending')
    download_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    last_downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sync_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    product: Mapped['Product | None'] = relationship(back_populates='images')
    variant: Mapped['ProductVariant | None'] = relationship(back_populates='images')
    asset: Mapped['ImageAsset | None'] = relationship(back_populates='product_images')


class ImageAsset(IdentityPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'image_assets'

    sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    storage_backend: Mapped[str] = mapped_column(String(32), nullable=False, default='local_fs', server_default='local_fs')
    storage_bucket: Mapped[str | None] = mapped_column(String(120), nullable=True)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    file_ext: Mapped[str | None] = mapped_column(String(16), nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    phash: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    dhash: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    archive_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default='ready',
        server_default='ready',
        index=True,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    product_images: Mapped[list['ProductImage']] = relationship(back_populates='asset')
    embeddings: Mapped[list['ImageEmbedding']] = relationship(back_populates='asset', cascade='all, delete-orphan')


class ImageEmbedding(IdentityPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'image_embeddings'
    __table_args__ = (
        UniqueConstraint('asset_id', 'provider', 'model_name', name='uq_image_embeddings_asset_provider_model'),
    )

    asset_id: Mapped[int] = mapped_column(ForeignKey('image_assets.id', ondelete='CASCADE'), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default='pending', server_default='pending')
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    vector_dim: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vector_status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default='pending',
        server_default='pending',
        index=True,
    )
    embedding_vector: Mapped[list[float] | None] = mapped_column(Vector(128), nullable=True)
    embedding_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    source_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    asset: Mapped['ImageAsset'] = relationship(back_populates='embeddings')


class ProductAttribute(IdentityPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'product_attributes'

    product_id: Mapped[int] = mapped_column(ForeignKey('products.id', ondelete='CASCADE'), nullable=False, index=True)
    variant_id: Mapped[int | None] = mapped_column(ForeignKey('product_variants.id', ondelete='CASCADE'), nullable=True, index=True)
    attr_name: Mapped[str] = mapped_column(String(120), nullable=False)
    attr_value: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')

    product: Mapped['Product'] = relationship(back_populates='attributes')
    variant: Mapped['ProductVariant | None'] = relationship(back_populates='attributes')
