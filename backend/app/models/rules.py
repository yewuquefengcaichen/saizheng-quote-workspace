from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, false, true
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdentityPrimaryKeyMixin, TimestampMixin


class Synonym(IdentityPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'synonyms'
    __table_args__ = (UniqueConstraint('canonical_term', 'synonym_term', name='uq_synonyms_pair'),)

    canonical_term: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    synonym_term: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default='legacy_json', server_default='legacy_json')
    is_bidirectional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    weight: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class NormalizationRule(IdentityPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'normalization_rules'

    rule_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    rule_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    rule_value_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_value_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSONB, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default='legacy_json', server_default='legacy_json')
    source_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class ParseTemplate(IdentityPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'parse_templates'

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default='excel', server_default='excel')
    header_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    column_mapping: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    last_confirmed_mapping: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    identifiers: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    header_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    identifier_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    confirm_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    manual_save_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    template_hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    mapping_change_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    mapping_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_mapping_changed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
