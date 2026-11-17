"""Configuración de pytest: base SQLite aislada para no tocar MySQL."""

import os
import tempfile
from pathlib import Path

_TEST_DIR = Path(tempfile.mkdtemp(prefix="obratrack-tests-"))
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{_TEST_DIR / 'test.db'}"
os.environ["JWT_SECRET"] = "test-secret-con-al-menos-32-bytes-de-longitud"
os.environ["ENVIRONMENT"] = "test"
os.environ["DEBUG"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402

USER = {
    "email": "alice@example.com",
    "name": "Alice",
    "password": "secreto123",
}


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as test_client:
        yield test_client


def _register_and_login(client: TestClient, email: str = USER["email"]) -> tuple[str, int]:
    response = client.post(
        "/api/auth/register",
        json={**USER, "email": email},
    )
    assert response.status_code == 201, response.text
    user_id = response.json()["id"]

    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": USER["password"]},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"], user_id


@pytest.fixture()
def auth_headers(client):
    token, _ = _register_and_login(client)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def other_auth_headers(client):
    token, _ = _register_and_login(client, "bob@example.com")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def device(client, auth_headers):
    response = client.post(
        "/api/devices",
        json={"name": "Taladro", "description": "Bosch GSB 18V"},
        headers=auth_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()
