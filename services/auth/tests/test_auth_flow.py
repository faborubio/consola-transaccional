"""Flujo completo de auth contra Mongo real: login, /me, rotación y reuso.

Requiere Mongo (docker compose); si no está, se salta. Usa la base
`auth_db_test` (ver conftest) y la limpia en cada corrida.
"""

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from app.config import get_settings
from app.main import app


@pytest.fixture(scope="module")
def client():
    settings = get_settings()
    try:
        sync = MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=3000)
        sync.admin.command("ping")
    except PyMongoError:
        pytest.skip(f"Mongo no disponible en {settings.mongo_uri}")
    sync.drop_database(settings.mongo_db)
    # El context manager dispara el lifespan: índices + usuarios demo.
    with TestClient(app) as c:
        yield c
    sync.drop_database(settings.mongo_db)
    sync.close()


def _login(client: TestClient, username="operador1", password="Demo1234!") -> dict:
    res = client.post("/auth/login", json={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return res.json()


def test_login_ok(client):
    pair = _login(client)
    assert pair["tokenType"] == "Bearer"
    assert pair["expiresIn"] == 900
    assert pair["accessToken"] != pair["refreshToken"]


def test_login_password_mala(client):
    res = client.post("/auth/login", json={"username": "operador1", "password": "incorrecta1"})
    assert res.status_code == 401
    assert res.json()["code"] == "UNAUTHORIZED"


def test_login_usuario_inexistente_mismo_error(client):
    res = client.post("/auth/login", json={"username": "nadie", "password": "Demo1234!"})
    assert res.status_code == 401
    # Mismo código y mensaje que password mala: no se revela si el usuario existe.
    assert res.json() == {"code": "UNAUTHORIZED", "message": "Credenciales inválidas."}


def test_me(client):
    pair = _login(client)
    res = client.get("/auth/me", headers={"Authorization": f"Bearer {pair['accessToken']}"})
    assert res.status_code == 200
    body = res.json()
    assert body["username"] == "operador1"
    assert body["roles"] == ["operador"]


def test_me_sin_token(client):
    res = client.get("/auth/me")
    assert res.status_code == 401


def test_refresh_rota_el_token(client):
    pair = _login(client)
    res = client.post("/auth/refresh", json={"refreshToken": pair["refreshToken"]})
    assert res.status_code == 200
    nuevo = res.json()
    assert nuevo["refreshToken"] != pair["refreshToken"]
    # el access nuevo funciona
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {nuevo['accessToken']}"})
    assert me.status_code == 200


def test_reuso_de_refresh_quema_la_familia(client):
    pair = _login(client)
    rotado = client.post("/auth/refresh", json={"refreshToken": pair["refreshToken"]}).json()

    # Reusar el refresh viejo (ya rotado) = señal de robo → 401
    reuso = client.post("/auth/refresh", json={"refreshToken": pair["refreshToken"]})
    assert reuso.status_code == 401

    # Y la familia completa quedó invalidada: el refresh NUEVO tampoco sirve.
    res = client.post("/auth/refresh", json={"refreshToken": rotado["refreshToken"]})
    assert res.status_code == 401


def test_access_no_sirve_para_refresh(client):
    pair = _login(client)
    res = client.post("/auth/refresh", json={"refreshToken": pair["accessToken"]})
    assert res.status_code == 401


def test_logout_revoca_la_familia(client):
    pair = _login(client)
    res = client.post("/auth/logout", json={"refreshToken": pair["refreshToken"]})
    assert res.status_code == 204

    # El refresh de la sesión cerrada ya no sirve.
    res = client.post("/auth/refresh", json={"refreshToken": pair["refreshToken"]})
    assert res.status_code == 401


def test_logout_con_token_invalido_tambien_204(client):
    # No se revela si el token era válido; revocar es inocuo.
    res = client.post("/auth/logout", json={"refreshToken": "no.es.jwt"})
    assert res.status_code == 204
