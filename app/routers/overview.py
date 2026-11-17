"""Resumen agregado para el panel principal."""

from fastapi import APIRouter
from sqlalchemy import func, select

from ..deps import CurrentUser, DbSession
from ..models import Alert, Device
from ..schemas import OverviewOut

router = APIRouter(prefix="/api", tags=["Panel"])


@router.get("/overview", response_model=OverviewOut, summary="Indicadores del panel")
def overview(user: CurrentUser, db: DbSession):
    def count_devices(*conditions) -> int:
        return (
            db.scalar(
                select(func.count(Device.id)).where(
                    Device.owner_id == user.id, *conditions
                )
            )
            or 0
        )

    alerts_open = (
        db.scalar(
            select(func.count(Alert.id))
            .join(Device)
            .where(Device.owner_id == user.id, Alert.resolved_at.is_(None))
        )
        or 0
    )
    alerts_unacknowledged = (
        db.scalar(
            select(func.count(Alert.id))
            .join(Device)
            .where(
                Device.owner_id == user.id,
                Alert.resolved_at.is_(None),
                Alert.acknowledged_at.is_(None),
            )
        )
        or 0
    )
    last_telemetry_at = db.scalar(
        select(func.max(Device.last_seen_at)).where(Device.owner_id == user.id)
    )

    return OverviewOut(
        devices_total=count_devices(),
        devices_active=count_devices(Device.active.is_(True)),
        devices_outside=count_devices(Device.geofence_state == "outside"),
        alerts_open=alerts_open,
        alerts_unacknowledged=alerts_unacknowledged,
        last_telemetry_at=last_telemetry_at,
    )
