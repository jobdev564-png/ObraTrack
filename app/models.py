"""Modelos ORM (SQLAlchemy 2.0)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .utils import utcnow

_MYSQL_TABLE_ARGS = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}


class User(Base):
    __tablename__ = "users"
    __table_args__ = _MYSQL_TABLE_ARGS

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    devices: Mapped[list["Device"]] = relationship(
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Device(Base):
    __tablename__ = "devices"
    __table_args__ = _MYSQL_TABLE_ARGS

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Última posición conocida (desnormalizada para consultas rápidas del panel).
    last_lat: Mapped[Optional[Decimal]] = mapped_column(Numeric(9, 6), nullable=True)
    last_lon: Mapped[Optional[Decimal]] = mapped_column(Numeric(9, 6), nullable=True)
    last_speed_kmh: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    last_accuracy_m: Mapped[Optional[Decimal]] = mapped_column(Numeric(7, 2), nullable=True)
    last_altitude_m: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)
    last_battery_pct: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_satellites: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_fix_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # "inside" | "outside" | None (sin geocerca activa o sin fix todavía)
    geofence_state: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    owner: Mapped["User"] = relationship(back_populates="devices")
    positions: Mapped[list["Position"]] = relationship(
        back_populates="device",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    alerts: Mapped[list["Alert"]] = relationship(
        back_populates="device",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    geofence: Mapped[Optional["Geofence"]] = relationship(
        back_populates="device",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        Index("ix_positions_device_recorded", "device_id", "recorded_at"),
        _MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    lat: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    lon: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    speed_kmh: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), nullable=True)
    accuracy_m: Mapped[Optional[Decimal]] = mapped_column(Numeric(7, 2), nullable=True)
    altitude_m: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), nullable=True)
    battery_pct: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    satellites: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    inside_geofence: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # Hora del fix según el dispositivo y hora en que llegó al servidor (UTC naive).
    recorded_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    device: Mapped["Device"] = relationship(back_populates="positions")


class Geofence(Base):
    __tablename__ = "geofences"
    __table_args__ = _MYSQL_TABLE_ARGS

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False, default="Geocerca")
    center_lat: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    center_lon: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    radius_m: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    device: Mapped["Device"] = relationship(back_populates="geofence")


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_device_created", "device_id", "created_at"),
        _MYSQL_TABLE_ARGS,
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), nullable=False
    )
    geofence_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("geofences.id", ondelete="SET NULL"), nullable=True
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    device: Mapped["Device"] = relationship(back_populates="alerts")
