"""Utilidades compartidas de fecha y hora."""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Hora actual en UTC como datetime naive (formato que almacena MySQL)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_naive_utc(value: datetime | None) -> datetime | None:
    """Convierte un datetime con zona horaria a UTC naive; deja los naive igual."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)
