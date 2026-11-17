"""Dependencias compartidas: sesión de BD y autenticación."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .database import SessionLocal
from .models import Device, User
from .security import decode_access_token

_bearer = HTTPBearer(auto_error=False, description="JWT obtenido en /api/auth/login")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbSession = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbSession,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)] = None,
) -> User:
    auth_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Debes iniciar sesión",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise auth_error

    user_id = decode_access_token(credentials.credentials)
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise auth_error
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_device(
    db: DbSession,
    x_device_token: Annotated[str | None, Header(alias="X-Device-Token")] = None,
) -> Device:
    if not x_device_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falta el encabezado X-Device-Token",
        )

    device = db.scalar(
        select(Device)
        .options(selectinload(Device.geofence))
        .where(Device.token == x_device_token)
    )
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de dispositivo inválido",
        )
    if not device.active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El dispositivo está desactivado",
        )
    return device


CurrentDevice = Annotated[Device, Depends(get_current_device)]


def get_owned_device(db: Session, user: User, device_id: int) -> Device:
    """Obtiene un dispositivo del usuario o lanza 404 (no filtra existencia ajena)."""
    device = db.scalar(
        select(Device)
        .options(selectinload(Device.geofence))
        .where(Device.id == device_id, Device.owner_id == user.id)
    )
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dispositivo no encontrado",
        )
    return device
