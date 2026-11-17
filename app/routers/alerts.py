"""Consulta y reconocimiento de alertas."""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..deps import CurrentUser, DbSession
from ..models import Alert, Device
from ..schemas import AlertOut
from ..utils import utcnow

router = APIRouter(prefix="/api/alerts", tags=["Alertas"])


@router.get("", response_model=list[AlertOut], summary="Listar alertas")
def list_alerts(
    user: CurrentUser,
    db: DbSession,
    device_id: int | None = Query(default=None),
    state: Literal["open", "resolved", "all"] = Query(default="open"),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    stmt = (
        select(Alert)
        .join(Device)
        .options(selectinload(Alert.device))
        .where(Device.owner_id == user.id)
    )
    if device_id is not None:
        stmt = stmt.where(Alert.device_id == device_id)
    if state == "open":
        stmt = stmt.where(Alert.resolved_at.is_(None))
    elif state == "resolved":
        stmt = stmt.where(Alert.resolved_at.is_not(None))

    return db.scalars(
        stmt.order_by(Alert.created_at.desc(), Alert.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()


@router.post(
    "/{alert_id}/acknowledge",
    response_model=AlertOut,
    summary="Marcar una alerta como vista por el usuario",
)
def acknowledge_alert(alert_id: int, user: CurrentUser, db: DbSession):
    alert = db.scalar(
        select(Alert)
        .join(Device)
        .options(selectinload(Alert.device))
        .where(Alert.id == alert_id, Device.owner_id == user.id)
    )
    if alert is None:
        raise HTTPException(status_code=404, detail="Alerta no encontrada")

    if alert.acknowledged_at is None:
        alert.acknowledged_at = utcnow()
        db.commit()
        db.refresh(alert)
    return alert
