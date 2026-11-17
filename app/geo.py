"""Cálculos geográficos para las geocercas circulares."""

from math import asin, cos, radians, sin, sqrt

EARTH_RADIUS_M = 6_371_008.8


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distancia en metros entre dos coordenadas (fórmula de Haversine)."""
    phi1, phi2 = radians(lat1), radians(lat2)
    delta_phi = phi2 - phi1
    delta_lambda = radians(lon2 - lon1)

    a = sin(delta_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(delta_lambda / 2) ** 2
    # min(1.0, ...) evita errores de dominio por redondeo en puntos casi idénticos.
    return 2 * EARTH_RADIUS_M * asin(sqrt(min(1.0, a)))


def point_in_circle(
    center_lat: float,
    center_lon: float,
    radius_m: float,
    lat: float,
    lon: float,
) -> bool:
    """Indica si un punto cae dentro de una geocerca circular."""
    return haversine_m(center_lat, center_lon, lat, lon) <= radius_m
