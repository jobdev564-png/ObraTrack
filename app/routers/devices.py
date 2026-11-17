"""CRUD de dispositivos, historial de posiciones y estado en vivo."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ..deps import CurrentUser, DbSession, get_owned_device
from ..geo import haversine_m
from ..models import Alert, Device, Position
from ..schemas import (
    DeviceCreate,
    DeviceOut,
    DeviceStatusOut,
    DeviceUpdate,
    PositionOut,
)
from ..security import generate_device_token
from ..utils import to_naive_utc

router = APIRouter(prefix="/api/devices", tags=["Dispositivos"])


def _unique_token(db: DbSession) -> str:
    for _ in range(5):
        token = generate_device_token()
        if db.scalar(select(Device.id).where(Device.token == token)) is None:
            return token
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="No se pudo generar un token de dispositivo",
    )


def _load(db: DbSession, user_id: int, device_id: int) -> Device:
    device = db.scalar(
        select(Device)
        .options(selectinload(Device.geofence))
        .where(Device.id == device_id, Device.owner_id == user_id)
    )
    if device is None:
        raise HTTPException(status_code=404, detail="Dispositivo no encontrado")
    return device


@router.post(
    "",
    response_model=DeviceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un dispositivo (el token se usa en la ESP32)",
)
def create_device(payload: DeviceCreate, user: CurrentUser, db: DbSession):
    device = Device(
        owner_id=user.id,
        name=payload.name,
        description=payload.description,
        token=_unique_token(db),
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return _load(db, user.id, device.id)


@router.get("", response_model=list[DeviceOut], summary="Listar mis dispositivos")
def list_devices(user: CurrentUser, db: DbSession):
    return db.scalars(
        select(Device)
        .options(selectinload(Device.geofence))
        .where(Device.owner_id == user.id)
        .order_by(Device.created_at.desc(), Device.id.desc())
    ).all()


@router.get("/{device_id}", response_model=DeviceOut, summary="Detalle de un dispositivo")
def get_device(device_id: int, user: CurrentUser, db: DbSession):
    return _load(db, user.id, device_id)


@router.patch("/{device_id}", response_model=DeviceOut, summary="Editar un dispositivo")
def update_device(device_id: int, payload: DeviceUpdate, user: CurrentUser, db: DbSession):
    device = get_owned_device(db, user, device_id)
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(device, field, value)
    db.commit()
    return _load(db, user.id, device.id)


@router.delete(
    "/{device_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar un dispositivo y su historial",
)
def delete_device(device_id: int, user: CurrentUser, db: DbSession):
    device = get_owned_device(db, user, device_id)
    db.delete(device)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{device_id}/rotate-token",
    response_model=DeviceOut,
    summary="Generar un token nuevo (invalida el anterior)",
)
def rotate_token(device_id: int, user: CurrentUser, db: DbSession):
    device = get_owned_device(db, user, device_id)
    device.token = _unique_token(db)
    db.commit()
    return _load(db, user.id, device.id)


@router.get(
    "/{device_id}/positions",
    response_model=list[PositionOut],
    summary="Historial de posiciones (más recientes primero)",
)
def list_positions(
    device_id: int,
    user: CurrentUser,
    db: DbSession,
    limit: int = Query(default=200, ge=1, le=1000, description="Máximo de puntos"),
    since: datetime | None = Query(default=None, description="Desde (ISO 8601)"),
    until: datetime | None = Query(default=None, description="Hasta (ISO 8601)"),
):
    get_owned_device(db, user, device_id)

    stmt = select(Position).where(Position.device_id == device_id)
    since_utc = to_naive_utc(since)
    until_utc = to_naive_utc(until)
    if since_utc is not None:
        stmt = stmt.where(Position.recorded_at >= since_utc)
    if until_utc is not None:
        stmt = stmt.where(Position.recorded_at <= until_utc)

    return db.scalars(
        stmt.order_by(Position.recorded_at.desc(), Position.id.desc()).limit(limit)
    ).all()


@router.get(
    "/{device_id}/status",
    response_model=DeviceStatusOut,
    summary="Estado actual: última posición, geocerca y alertas abiertas",
)
def device_status(device_id: int, user: CurrentUser, db: DbSession):
    device = _load(db, user.id, device_id)

    distance = None
    inside = None
    if (
        device.geofence is not None
        and device.last_lat is not None
        and device.last_lon is not None
    ):
        distance = haversine_m(
            float(device.geofence.center_lat),
            float(device.geofence.center_lon),
            float(device.last_lat),
            float(device.last_lon),
        )
        inside = distance <= float(device.geofence.radius_m)

    open_alerts = (
        db.scalar(
            select(func.count(Alert.id)).where(
                Alert.device_id == device.id,
                Alert.resolved_at.is_(None),
            )
        )
        or 0
    )

    base = DeviceOut.model_validate(device)
    return DeviceStatusOut(
        **base.model_dump(),
        distance_to_center_m=round(distance, 1) if distance is not None else None,
        inside_geofence=inside,
        open_alerts=open_alerts,
    )
