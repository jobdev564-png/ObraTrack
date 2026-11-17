"""Esquemas Pydantic de entrada y salida de la API."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    PlainSerializer,
    field_validator,
)


def _iso_utc(value: datetime) -> str:
    """Serializa datetimes (guardados como UTC naive) con sufijo Z."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


UtcDateTime = Annotated[
    datetime,
    PlainSerializer(_iso_utc, return_type=str, when_used="json"),
]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --------------------------------------------------------------------------- #
# Autenticación
# --------------------------------------------------------------------------- #
class RegisterIn(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=8, max_length=128)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El nombre no puede estar vacío")
        return value


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserOut(ORMModel):
    id: int
    email: EmailStr
    name: str
    is_active: bool
    created_at: UtcDateTime
    last_login_at: UtcDateTime | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


# --------------------------------------------------------------------------- #
# Dispositivos
# --------------------------------------------------------------------------- #
class DeviceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=255)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("El nombre no puede estar vacío")
        return value


class DeviceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=255)
    active: bool | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("El nombre no puede estar vacío")
        return value


class GeofenceOut(ORMModel):
    id: int
    device_id: int
    name: str
    center_lat: float
    center_lon: float
    radius_m: float
    enabled: bool
    created_at: UtcDateTime
    updated_at: UtcDateTime


class DeviceOut(ORMModel):
    id: int
    name: str
    description: str | None
    token: str
    active: bool
    created_at: UtcDateTime

    last_lat: float | None = None
    last_lon: float | None = None
    last_speed_kmh: float | None = None
    last_accuracy_m: float | None = None
    last_altitude_m: float | None = None
    last_battery_pct: int | None = None
    last_satellites: int | None = None
    last_fix_at: UtcDateTime | None = None
    last_seen_at: UtcDateTime | None = None
    geofence_state: str | None = None

    geofence: GeofenceOut | None = None


class DeviceStatusOut(DeviceOut):
    distance_to_center_m: float | None = None
    inside_geofence: bool | None = None
    open_alerts: int = 0


class DeviceSummary(ORMModel):
    id: int
    name: str


# --------------------------------------------------------------------------- #
# Telemetría
# --------------------------------------------------------------------------- #
class TelemetryIn(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    recorded_at: datetime | None = None
    speed_kmh: float | None = Field(default=None, ge=0, le=400)
    accuracy_m: float | None = Field(default=None, ge=0, le=10000)
    altitude_m: float | None = Field(default=None, ge=-500, le=10000)
    battery_pct: int | None = Field(default=None, ge=0, le=100)
    satellites: int | None = Field(default=None, ge=0, le=64)


class TelemetryAck(BaseModel):
    position_id: int
    recorded_at: UtcDateTime
    received_at: UtcDateTime
    inside_geofence: bool | None
    distance_to_center_m: float | None
    alert_created: bool
    resolved_alerts: int


class PositionOut(ORMModel):
    id: int
    device_id: int
    lat: float
    lon: float
    speed_kmh: float | None
    accuracy_m: float | None
    altitude_m: float | None
    battery_pct: int | None
    satellites: int | None
    inside_geofence: bool | None
    recorded_at: UtcDateTime
    received_at: UtcDateTime


# --------------------------------------------------------------------------- #
# Geocercas
# --------------------------------------------------------------------------- #
class GeofenceIn(BaseModel):
    name: str = Field(default="Geocerca", min_length=1, max_length=80)
    center_lat: float = Field(ge=-90, le=90)
    center_lon: float = Field(ge=-180, le=180)
    radius_m: float = Field(gt=0, le=50000)
    enabled: bool = True


# --------------------------------------------------------------------------- #
# Alertas
# --------------------------------------------------------------------------- #
class AlertOut(ORMModel):
    id: int
    device_id: int
    geofence_id: int | None
    type: str
    message: str
    created_at: UtcDateTime
    acknowledged_at: UtcDateTime | None
    resolved_at: UtcDateTime | None
    device: DeviceSummary


class OverviewOut(BaseModel):
    devices_total: int
    devices_active: int
    devices_outside: int
    alerts_open: int
    alerts_unacknowledged: int
    last_telemetry_at: UtcDateTime | None
