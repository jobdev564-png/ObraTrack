"""Recepción de telemetría enviada por la ESP32 y evaluación de geocercas."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import update

from ..config import get_settings
from ..deps import CurrentDevice, DbSession
from ..geo import haversine_m
from ..models import Alert, Position
from ..schemas import TelemetryAck, TelemetryIn
from ..utils import to_naive_utc, utcnow

router = APIRouter(prefix="/api", tags=["Telemetría"])
logger = logging.getLogger(__name__)

ALERT_GEOFENCE_EXIT = "geofence_exit"


@router.post(
    "/telemetry",
    response_model=TelemetryAck,
    status_code=status.HTTP_201_CREATED,
    summary="Recibir una posición GPS (autenticado con X-Device-Token)",
)
def ingest_telemetry(
    payload: TelemetryIn,
    device: CurrentDevice,
    db: DbSession,
):
    settings = get_settings()

    if (
        settings.telemetry_reject_null_island
        and payload.lat == 0.0
        and payload.lon == 0.0
    ):
        raise HTTPException(
            status_code=422,
            detail="Fix GPS inválido (0,0); espera a que el NEO-6M obtenga señal",
        )

    now = utcnow()
    recorded_at = to_naive_utc(payload.recorded_at) or now

    inside = None
    distance = None
    geofence = device.geofence
    alert_created = False
    resolved_alerts = 0

    if geofence is not None:
        distance = haversine_m(
            float(geofence.center_lat),
            float(geofence.center_lon),
            payload.lat,
            payload.lon,
        )
        inside = distance <= float(geofence.radius_m)

        if geofence.enabled:
            previous_state = device.geofence_state

            if previous_state == "inside" and not inside:
                db.add(
                    Alert(
                        device_id=device.id,
                        geofence_id=geofence.id,
                        type=ALERT_GEOFENCE_EXIT,
                        message=(
                            f"'{device.name}' salió de la geocerca '{geofence.name}' "
                            f"(a {distance:.0f} m del centro; radio "
                            f"{float(geofence.radius_m):.0f} m)."
                        ),
                    )
                )
                alert_created = True
                logger.warning(
                    "Geofence exit: device=%s distance=%.1fm", device.id, distance
                )
            elif previous_state == "outside" and inside:
                resolved_alerts = (
                    db.execute(
                        update(Alert)
                        .where(
                            Alert.device_id == device.id,
                            Alert.type == ALERT_GEOFENCE_EXIT,
                            Alert.resolved_at.is_(None),
                        )
                        .values(resolved_at=now)
                    ).rowcount
                    or 0
                )
                logger.info(
                    "Geofence re-entry: device=%s resolved_alerts=%s",
                    device.id,
                    resolved_alerts,
                )

            # Primera lectura: solo se guarda el estado, sin alertar.
            device.geofence_state = "inside" if inside else "outside"
        else:
            device.geofence_state = None

    position = Position(
        device_id=device.id,
        lat=payload.lat,
        lon=payload.lon,
        speed_kmh=payload.speed_kmh,
        accuracy_m=payload.accuracy_m,
        altitude_m=payload.altitude_m,
        battery_pct=payload.battery_pct,
        satellites=payload.satellites,
        inside_geofence=inside,
        recorded_at=recorded_at,
        received_at=now,
    )
    db.add(position)

    device.last_lat = payload.lat
    device.last_lon = payload.lon
    device.last_speed_kmh = payload.speed_kmh
    device.last_accuracy_m = payload.accuracy_m
    device.last_altitude_m = payload.altitude_m
    device.last_battery_pct = payload.battery_pct
    device.last_satellites = payload.satellites
    device.last_fix_at = recorded_at
    device.last_seen_at = now

    db.commit()
    db.refresh(position)

    return TelemetryAck(
        position_id=position.id,
        recorded_at=recorded_at,
        received_at=now,
        inside_geofence=inside,
        distance_to_center_m=round(distance, 1) if distance is not None else None,
        alert_created=alert_created,
        resolved_alerts=resolved_alerts,
    )
