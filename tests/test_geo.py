"""Pruebas de la lógica geográfica."""

import pytest

from app.geo import haversine_m, point_in_circle


def test_haversine_one_degree_of_latitude():
    # Un grado de latitud equivale a ~111.2 km.
    distance = haversine_m(4.0, -74.0, 5.0, -74.0)
    assert distance == pytest.approx(111_195, rel=0.001)


def test_haversine_same_point_is_zero():
    assert haversine_m(4.60971, -74.08175, 4.60971, -74.08175) == 0


def test_point_in_circle_uses_radius():
    center = (4.60971, -74.08175)
    assert point_in_circle(*center, 100, 4.60971, -74.08175)
    # ~111 m al norte: fuera de un radio de 100 m.
    assert not point_in_circle(*center, 100, 4.61071, -74.08175)
