"""Simula la ESP32 enviando posiciones GPS a la API.

Útil para demostrar el MVP sin hardware. Recorre una trayectoria que entra y
sale de la geocerca para disparar alertas.

Ejemplo:
    python scripts/simulate_device.py \
        --token ot_xxx \
        --lat 4.609710 --lon -74.081750 --radius 150 \
        --interval 2 --count 40
"""

import argparse
import math
import sys
import time

import httpx


def offset_meters(lat: float, lon: float, north_m: float, east_m: float) -> tuple[float, float]:
    """Desplaza una coordenada una distancia aproximada en metros."""
    dlat = north_m / 111_320.0
    dlon = east_m / (111_320.0 * math.cos(math.radians(lat)))
    return lat + dlat, lon + dlon


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulador de telemetría ObraTrack")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--token", required=True, help="Token del dispositivo (ot_...)")
    parser.add_argument("--lat", type=float, default=4.609710, help="Centro de la geocerca")
    parser.add_argument("--lon", type=float, default=-74.081750)
    parser.add_argument("--radius", type=float, default=150.0, help="Radio de la geocerca (m)")
    parser.add_argument("--interval", type=float, default=2.0, help="Segundos entre envíos")
    parser.add_argument(
        "--count", type=int, default=0, help="Número de envíos (0 = infinito)"
    )
    args = parser.parse_args()

    url = f"{args.base_url.rstrip('/')}/api/telemetry"
    headers = {"X-Device-Token": args.token}
    print(f"Enviando a {url} cada {args.interval}s (Ctrl+C para salir)")

    sent = 0
    try:
        with httpx.Client(timeout=10) as client:
            while args.count == 0 or sent < args.count:
                # Órbita elíptica: cruza el radio de la geocerca dos veces por vuelta.
                angle = 2 * math.pi * sent / 24
                east = args.radius * 1.7 * math.sin(angle)
                north = args.radius * 0.45 * math.cos(angle)

                lat, lon = offset_meters(args.lat, args.lon, north, east)
                payload = {
                    "lat": round(lat, 6),
                    "lon": round(lon, 6),
                    "speed_kmh": round(abs(math.cos(angle)) * 8, 1),
                    "accuracy_m": 4.5,
                    "satellites": 9,
                    "battery_pct": max(20, 95 - sent // 10),
                }

                try:
                    response = client.post(url, json=payload, headers=headers)
                    if response.status_code == 201:
                        data = response.json()
                        flags = []
                        if data.get("alert_created"):
                            flags.append("ALERTA CREADA")
                        if data.get("resolved_alerts"):
                            flags.append(f"{data['resolved_alerts']} alerta(s) resuelta(s)")
                        suffix = f"  <-- {', '.join(flags)}" if flags else ""
                        print(
                            f"[{sent:03d}] {lat:.6f}, {lon:.6f} "
                            f"dentro={data.get('inside_geofence')} "
                            f"dist={data.get('distance_to_center_m')}m{suffix}"
                        )
                    else:
                        print(f"[{sent:03d}] ERROR {response.status_code}: {response.text}")
                except httpx.HTTPError as exc:
                    print(f"[{sent:03d}] Sin conexión con la API: {exc}")

                sent += 1
                time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nSimulación detenida.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
