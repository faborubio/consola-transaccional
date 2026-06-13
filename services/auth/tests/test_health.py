from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.api.routes_auth import get_repo
from app.main import app

client = TestClient(app)


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "auth"}


def test_excepcion_no_manejada_usa_esquema_del_contrato():
    """Mismo contrato de error uniforme también en auth ante un fallo inesperado."""
    mock = AsyncMock()
    mock.find_by_username.side_effect = RuntimeError("boom")
    app.dependency_overrides[get_repo] = lambda: mock
    local = TestClient(app, raise_server_exceptions=False)
    try:
        res = local.post("/auth/login", json={"username": "x", "password": "Demo1234!"})
        assert res.status_code == 500
        assert res.json() == {"code": "INTERNAL", "message": "Error interno del servidor."}
    finally:
        app.dependency_overrides.clear()
