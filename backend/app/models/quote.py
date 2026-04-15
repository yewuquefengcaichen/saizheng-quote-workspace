from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint, false
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdentityPrimaryKeyMixin, PublicIdMixin, TimestampMixin


class QuoteBatch(IdentityPrimaryKeyMixin, PublicIdMixin, TimestampMixin, Base):
    __tablename__ = 'quote_batches'

    source_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_file_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default='excel', server_default='excel')
    import_status: Mapped[str] = mapped_column(String(32), nullable=False, default='pending', server_default='pending')
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False, default='pending', server_default='pending')
    total_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    confirmed_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    unmatched_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    source_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list['QuoteItem']] = relationship(back_populates='batch', cascade='all, delete-orphan')


class QuoteItem(IdentityPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'quote_items'
    __table_args__ = (UniqueConstraint('batch_id', 'row_number', name='uq_quote_items_batch_row'),)

    batch_id: Mapped[int] = mapped_column(ForeignKey('quote_batches.id', ondelete='CASCADE'), nullable=False, index=True)
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_name: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_spec: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    raw_model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(14, 4), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default='CNY', server_default='CNY')
    normalized_name: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    normalized_spec: Mapped[str | None] = mapped_column(Text, nullable=True)
    selected_product_id: Mapped[int | None] = mapped_column(ForeignKey('products.id', ondelete='SET NULL'), nullable=True, index=True)
    selected_variant_id: Mapped[int | None] = mapped_column(ForeignKey('product_variants.id', ondelete='SET NULL'), nullable=True, index=True)
    match_status: Mapped[str] = mapped_column(String(32), nullable=False, default='pending', server_default='pending')
    quote_status: Mapped[str] = mapped_column(String(32), nullable=False, default='unconfirmed', server_default='unconfirmed')
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    batch: Mapped['QuoteBatch'] = relationship(back_populates='items')
    candidates: Mapped[list['QuoteItemCandidate']] = relationship(back_populates='item', cascade='all, delete-orphan')


class QuoteItemCandidate(IdentityPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'quote_item_candidates'
    __table_args__ = (UniqueConstraint('quote_item_id', 'candidate_rank', name='uq_quote_item_candidates_rank'),)

    quote_item_id: Mapped[int] = mapped_column(ForeignKey('quote_items.id', ondelete='CASCADE'), nullable=False, index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey('products.id', ondelete='SET NULL'), nullable=True, index=True)
    variant_id: Mapped[int | None] = mapped_column(ForeignKey('product_variants.id', ondelete='SET NULL'), nullable=True, index=True)
    candidate_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_breakdown: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    is_selected: Mapped[bool] = mapped_column(nullable=False, default=False, server_default=false())

    item: Mapped['QuoteItem'] = relationship(back_populates='candidates')
