"""Geocercas circulares: una por dispositivo en el MVP."""

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy.orm import selectinload

from ..deps import CurrentUser, DbSession, get_owned_device
from ..geo import point_in_circle
from ..models import Device, Geofence
from ..schemas import GeofenceIn, GeofenceOut

router = APIRouter(prefix="/api/devices", tags=["Geocercas"])


def _recompute_state(device: Device) -> None:
    """Recalcula el estado sin generar alertas (evita falsos positivos)."""
    geofence = device.geofence
    if (
        geofence is not None
        and geofence.enabled
        and device.last_lat is not None
        and device.last_lon is not None
    ):
        inside = point_in_circle(
            float(geofence.center_lat),
            float(geofence.center_lon),
            float(geofence.radius_m),
            float(device.last_lat),
            float(device.last_lon),
        )
        device.geofence_state = "inside" if inside else "outside"
    elif geofence is None or not geofence.enabled:
        device.geofence_state = None


@router.get(
    "/{device_id}/geofence",
    response_model=GeofenceOut,
    summary="Consultar la geocerca del dispositivo",
)
def get_geofence(device_id: int, user: CurrentUser, db: DbSession):
    device = get_owned_device(db, user, device_id)
    if device.geofence is None:
        raise HTTPException(status_code=404, detail="El dispositivo no tiene geocerca")
    return device.geofence


@router.put(
    "/{device_id}/geofence",
    response_model=GeofenceOut,
    summary="Crear o reemplazar la geocerca circular",
)
def upsert_geofence(device_id: int, payload: GeofenceIn, user: CurrentUser, db: DbSession):
    device = get_owned_device(db, user, device_id)

    geofence = device.geofence
    if geofence is None:
        geofence = Geofence(device_id=device.id)
        db.add(geofence)
        device.geofence = geofence

    geofence.name = payload.name
    geofence.center_lat = payload.center_lat
    geofence.center_lon = payload.center_lon
    geofence.radius_m = payload.radius_m
    geofence.enabled = payload.enabled

    _recompute_state(device)
    db.commit()
    db.refresh(geofence)
    return geofence


@router.delete(
    "/{device_id}/geofence",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Eliminar la geocerca",
)
def delete_geofence(device_id: int, user: CurrentUser, db: DbSession):
    device = get_owned_device(db, user, device_id)
    if device.geofence is not None:
        db.delete(device.geofence)
    device.geofence_state = None
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
