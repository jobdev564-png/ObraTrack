"""Pruebas de integración del flujo completo del MVP."""

CENTER = {"lat": 4.609710, "lon": -74.081750}
OUTSIDE = {"lat": 4.620000, "lon": -74.081750}  # ~1.1 km al norte


def _set_geofence(client, headers, device_id, radius=150):
    response = client.put(
        f"/api/devices/{device_id}/geofence",
        headers=headers,
        json={
            "name": "Patio de obra",
            "center_lat": CENTER["lat"],
            "center_lon": CENTER["lon"],
            "radius_m": radius,
            "enabled": True,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _post_telemetry(client, token, body):
    return client.post(
        "/api/telemetry",
        headers={"X-Device-Token": token},
        json=body,
    )


def test_register_login_and_me(client):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "Alice@Example.com",
            "name": "  Alice  ",
            "password": "secreto123",
        },
    )
    assert response.status_code == 201
    assert response.json()["email"] == "alice@example.com"
    assert response.json()["name"] == "Alice"

    response = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "secreto123"},
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert response.json()["user"]["email"] == "alice@example.com"

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["last_login_at"] is not None


def test_seed_demo_account_can_login(client):
    """Evita que las credenciales de demostración usen un dominio rechazado."""
    from app import seed

    seed.main()
    response = client.post(
        "/api/auth/login",
        json={"email": seed.DEMO_EMAIL, "password": seed.DEMO_PASSWORD},
    )
    assert response.status_code == 200, response.text
    assert response.json()["user"]["email"] == seed.DEMO_EMAIL


def test_registration_can_be_disabled(client, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "allow_registration", False)
    response = client.post(
        "/api/auth/register",
        json={"email": "nueva@example.com", "name": "Nueva", "password": "secreto123"},
    )
    assert response.status_code == 403


def test_auth_errors(client, auth_headers):
    duplicate = client.post(
        "/api/auth/register",
        json={
            "email": "alice@example.com",
            "name": "Otra",
            "password": "secreto123",
        },
    )
    assert duplicate.status_code == 409

    wrong = client.post(
        "/api/auth/login",
        json={"email": "alice@example.com", "password": "incorrecta"},
    )
    assert wrong.status_code == 401

    assert client.get("/api/devices").status_code == 401
    assert client.get("/api/devices", headers={"Authorization": "Bearer basura"}).status_code == 401


def test_device_crud_and_isolation(client, auth_headers, other_auth_headers, device):
    assert device["token"].startswith("ot_")
    assert device["geofence"] is None

    listing = client.get("/api/devices", headers=auth_headers).json()
    assert [item["id"] for item in listing] == [device["id"]]

    # Otro usuario no puede ver el dispositivo.
    assert (
        client.get(f"/api/devices/{device['id']}", headers=other_auth_headers).status_code
        == 404
    )

    updated = client.patch(
        f"/api/devices/{device['id']}",
        headers=auth_headers,
        json={"name": "Taladro percutor", "active": False},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Taladro percutor"
    assert updated.json()["active"] is False

    # Un dispositivo desactivado no puede enviar telemetría.
    assert _post_telemetry(client, device["token"], CENTER).status_code == 403

    client.patch(
        f"/api/devices/{device['id']}",
        headers=auth_headers,
        json={"active": True},
    )


def test_geofence_crud(client, auth_headers, device):
    geofence = _set_geofence(client, auth_headers, device["id"])
    assert geofence["radius_m"] == 150
    assert geofence["center_lat"] == CENTER["lat"]

    fetched = client.get(
        f"/api/devices/{device['id']}/geofence", headers=auth_headers
    )
    assert fetched.status_code == 200
    assert fetched.json()["name"] == "Patio de obra"

    # Reemplazar la geocerca no duplica registros.
    updated = _set_geofence(client, auth_headers, device["id"], radius=300)
    assert updated["id"] == geofence["id"]
    assert updated["radius_m"] == 300

    assert (
        client.delete(f"/api/devices/{device['id']}/geofence", headers=auth_headers).status_code
        == 204
    )
    assert (
        client.get(f"/api/devices/{device['id']}/geofence", headers=auth_headers).status_code
        == 404
    )


def test_telemetry_requires_valid_token(client, device):
    assert client.post("/api/telemetry", json=CENTER).status_code == 401
    assert _post_telemetry(client, "ot_invalido", CENTER).status_code == 401


def test_telemetry_validates_coordinates(client, device):
    invalid = _post_telemetry(client, device["token"], {"lat": 95, "lon": 0})
    assert invalid.status_code == 422

    null_island = _post_telemetry(client, device["token"], {"lat": 0, "lon": 0})
    assert null_island.status_code == 422
    assert "0,0" in null_island.json()["detail"]


def test_geofence_alert_lifecycle(client, auth_headers, device):
    _set_geofence(client, auth_headers, device["id"])

    # Primer fix dentro: guarda estado, no alerta.
    first = _post_telemetry(client, device["token"], CENTER)
    assert first.status_code == 201, first.text
    assert first.json()["inside_geofence"] is True
    assert first.json()["alert_created"] is False
    assert first.json()["distance_to_center_m"] == 0

    # Segundo fix dentro: sigue sin alertas.
    again = _post_telemetry(
        client,
        device["token"],
        {**CENTER, "speed_kmh": 1.5, "battery_pct": 87, "satellites": 9},
    )
    assert again.json()["alert_created"] is False

    status = client.get(
        f"/api/devices/{device['id']}/status", headers=auth_headers
    ).json()
    assert status["inside_geofence"] is True
    assert status["open_alerts"] == 0
    assert status["last_battery_pct"] == 87

    # Sale de la geocerca: se crea la alerta.
    outside = _post_telemetry(client, device["token"], OUTSIDE)
    assert outside.status_code == 201
    assert outside.json()["inside_geofence"] is False
    assert outside.json()["alert_created"] is True
    assert outside.json()["distance_to_center_m"] > 150

    alerts = client.get("/api/alerts", headers=auth_headers).json()
    assert len(alerts) == 1
    assert alerts[0]["type"] == "geofence_exit"
    assert alerts[0]["device"]["name"] == "Taladro"
    assert alerts[0]["resolved_at"] is None

    status = client.get(
        f"/api/devices/{device['id']}/status", headers=auth_headers
    ).json()
    assert status["inside_geofence"] is False
    assert status["geofence_state"] == "outside"
    assert status["open_alerts"] == 1

    # Un segundo fix fuera no duplica la alerta.
    _post_telemetry(client, device["token"], OUTSIDE)
    assert len(client.get("/api/alerts?state=all", headers=auth_headers).json()) == 1

    # Vuelve al patio: la alerta se resuelve.
    back = _post_telemetry(client, device["token"], CENTER)
    assert back.json()["resolved_alerts"] == 1
    assert client.get("/api/alerts", headers=auth_headers).json() == []

    resolved = client.get("/api/alerts?state=resolved", headers=auth_headers).json()
    assert len(resolved) == 1
    assert resolved[0]["resolved_at"] is not None

    ack = client.post(
        f"/api/alerts/{resolved[0]['id']}/acknowledge", headers=auth_headers
    )
    assert ack.status_code == 200
    assert ack.json()["acknowledged_at"] is not None


def test_positions_history(client, auth_headers, device):
    _set_geofence(client, auth_headers, device["id"])
    _post_telemetry(client, device["token"], CENTER)
    _post_telemetry(client, device["token"], OUTSIDE)

    positions = client.get(
        f"/api/devices/{device['id']}/positions?limit=10", headers=auth_headers
    )
    assert positions.status_code == 200
    body = positions.json()
    assert len(body) == 2
    assert body[0]["lat"] == OUTSIDE["lat"]  # más reciente primero
    assert body[0]["inside_geofence"] is False
    assert body[1]["inside_geofence"] is True

    assert (
        client.get(
            f"/api/devices/{device['id']}/positions", headers=auth_headers
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/devices/{device['id']}/positions?limit=0", headers=auth_headers
        ).status_code
        == 422
    )


def test_overview(client, auth_headers, device):
    _set_geofence(client, auth_headers, device["id"])
    _post_telemetry(client, device["token"], CENTER)
    _post_telemetry(client, device["token"], OUTSIDE)

    overview = client.get("/api/overview", headers=auth_headers)
    assert overview.status_code == 200
    body = overview.json()
    assert body["devices_total"] == 1
    assert body["devices_active"] == 1
    assert body["devices_outside"] == 1
    assert body["alerts_open"] == 1
    assert body["alerts_unacknowledged"] == 1
    assert body["last_telemetry_at"] is not None


def test_rotate_token_and_delete(client, auth_headers, device):
    rotated = client.post(
        f"/api/devices/{device['id']}/rotate-token", headers=auth_headers
    )
    assert rotated.status_code == 200
    new_token = rotated.json()["token"]
    assert new_token != device["token"]
    assert _post_telemetry(client, device["token"], CENTER).status_code == 401
    assert _post_telemetry(client, new_token, CENTER).status_code == 201

    assert (
        client.delete(f"/api/devices/{device['id']}", headers=auth_headers).status_code
        == 204
    )
    assert (
        client.get(f"/api/devices/{device['id']}", headers=auth_headers).status_code
        == 404
    )


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["database"] == "ok"
