"""Datos de demostración para probar el MVP sin hardware.

Uso:
    python -m app.seed

Variables opcionales: DEMO_EMAIL, DEMO_PASSWORD, DEMO_LAT, DEMO_LON.
"""

import os

from sqlalchemy import select

from .database import Base, SessionLocal, engine
from .models import Device, Geofence, User
from .security import generate_device_token, hash_password

DEMO_EMAIL = os.getenv("DEMO_EMAIL", "demo@example.com")
DEMO_PASSWORD = os.getenv("DEMO_PASSWORD", "demo1234")
DEMO_LAT = float(os.getenv("DEMO_LAT", "4.609710"))
DEMO_LON = float(os.getenv("DEMO_LON", "-74.081750"))


def main() -> None:
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == DEMO_EMAIL))
        if user is None:
            user = User(
                email=DEMO_EMAIL,
                name="Usuario de demostración",
                password_hash=hash_password(DEMO_PASSWORD),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"Usuario creado: {DEMO_EMAIL} / {DEMO_PASSWORD}")

        device = db.scalar(
            select(Device).where(
                Device.owner_id == user.id,
                Device.name == "Taladro de demostración",
            )
        )
        if device is None:
            device = Device(
                owner_id=user.id,
                name="Taladro de demostración",
                description="Dispositivo de prueba con geocerca de 150 m",
                token=generate_device_token(),
            )
            db.add(device)
            db.commit()
            db.refresh(device)

            db.add(
                Geofence(
                    device_id=device.id,
                    name="Patio de obra",
                    center_lat=DEMO_LAT,
                    center_lon=DEMO_LON,
                    radius_m=150,
                    enabled=True,
                )
            )
            db.commit()
            print("Dispositivo y geocerca creados.")

        print()
        print(f"Dispositivo: {device.name} (id={device.id})")
        print(f"Token ESP32: {device.token}")
        print(f"Geocerca: centro {DEMO_LAT}, {DEMO_LON} · radio 150 m")
        print()
        print("Prueba la telemetría con:")
        print(
            "  curl -X POST http://127.0.0.1:8000/api/telemetry \\\n"
            f"    -H 'X-Device-Token: {device.token}' \\\n"
            "    -H 'Content-Type: application/json' \\\n"
            f"    -d '{{\"lat\": {DEMO_LAT}, \"lon\": {DEMO_LON}}}'"
        )


if __name__ == "__main__":
    main()
