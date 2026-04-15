from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdentityPrimaryKeyMixin, PublicIdMixin, TimestampMixin


class SyncJob(IdentityPrimaryKeyMixin, PublicIdMixin, TimestampMixin, Base):
    __tablename__ = 'sync_jobs'

    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_name: Mapped[str] = mapped_column(String(64), nullable=False, default='mall', server_default='mall')
    trigger_mode: Mapped[str] = mapped_column(String(32), nullable=False, default='manual', server_default='manual')
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='pending', server_default='pending')
    requested_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    total_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    completed_steps: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    stats_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    logs: Mapped[list['SyncJobLog']] = relationship(back_populates='job', cascade='all, delete-orphan')


class SyncJobLog(IdentityPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = 'sync_job_logs'

    job_id: Mapped[int] = mapped_column(ForeignKey('sync_jobs.id', ondelete='CASCADE'), nullable=False, index=True)
    level: Mapped[str] = mapped_column(String(16), nullable=False, default='info', server_default='info')
    event_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    job: Mapped['SyncJob'] = relationship(back_populates='logs')
