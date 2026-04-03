"""SQLAlchemy ORM models for the license server."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (Boolean, DateTime, Enum, ForeignKey,
                        Integer, String, Text)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class TierEnum(str, enum.Enum):
    free   = "free"
    pro    = "pro"
    studio = "studio"


class Customer(Base):
    __tablename__ = "customers"

    id:              Mapped[str]      = mapped_column(String(36), primary_key=True,
                                                     default=lambda: str(uuid.uuid4()))
    email:           Mapped[str]      = mapped_column(String(255), unique=True, index=True)
    stripe_customer: Mapped[str|None] = mapped_column(String(64), unique=True, nullable=True)
    created_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    licenses: Mapped[list["License"]] = relationship(back_populates="customer",
                                                     cascade="all, delete-orphan")


class License(Base):
    __tablename__ = "licenses"

    id:              Mapped[str]      = mapped_column(String(36), primary_key=True,
                                                     default=lambda: str(uuid.uuid4()))
    customer_id:     Mapped[str]      = mapped_column(ForeignKey("customers.id"), index=True)
    key:             Mapped[str]      = mapped_column(String(64), unique=True, index=True)
    tier:            Mapped[TierEnum] = mapped_column(Enum(TierEnum), default=TierEnum.free)
    stripe_sub_id:   Mapped[str|None] = mapped_column(String(64), nullable=True)
    active:          Mapped[bool]     = mapped_column(Boolean, default=True)
    created_at:      Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at:      Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_validated:  Mapped[datetime|None] = mapped_column(DateTime(timezone=True), nullable=True)
    activations:     Mapped[int]      = mapped_column(Integer, default=0)
    notes:           Mapped[str|None] = mapped_column(Text, nullable=True)

    customer: Mapped["Customer"] = relationship(back_populates="licenses")
