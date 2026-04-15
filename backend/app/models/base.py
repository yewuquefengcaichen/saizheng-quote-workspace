from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, Identity, Uuid, func, true
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(AsyncAttrs, DeclarativeBase):
    pass


class IdentityPrimaryKeyMixin:
    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)


class PublicIdMixin:
    public_id: Mapped[UUID] = mapped_column(Uuid(), nullable=False, unique=True, default=uuid4)


class ActiveFlagMixin:
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=true())


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
