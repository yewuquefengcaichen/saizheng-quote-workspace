from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text, false
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdentityPrimaryKeyMixin


class MatchFeedback(IdentityPrimaryKeyMixin, Base):
    __tablename__ = 'match_feedback'

    created_at: Mapped[str | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    template_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    template_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    action: Mapped[str | None] = mapped_column(String(50), nullable=True)
    original_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_spec: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    normalized_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_spec: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_unit: Mapped[str | None] = mapped_column(String(64), nullable=True)
    selected_product_code: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    selected_product_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    top_candidate_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    top_candidate_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    top_candidate_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    top_candidate_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selected_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    selected_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    with_product_image: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    ocr_confidence: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    query_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    feedback_weight: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    mapping_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    mapping_changed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
