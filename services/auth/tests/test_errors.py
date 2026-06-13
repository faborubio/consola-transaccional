"""Caminos de error que deben cumplir el esquema del contrato (code/message).

No requieren Mongo: el cuerpo falla al parsearse antes de tocar el repositorio, y
TestClient(app) sin `with` no dispara el lifespan (bootstrap de usuarios demo).
Regresión del hallazgo de Schemathesis (Fase 6): bytes no decodificables daban el
400 {"detail": ...} por defecto de FastAPI, fuera del contrato.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_cuerpo_ilegible_se_normaliza_a_422_con_esquema_del_contrato():
    res = client.post(
        "/auth/login",
        content=b"\xff\xff\x68",  # ni siquiera decodifica como texto
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 422
    body = res.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert set(body) <= {"code", "message", "details"}  # nada de {"detail": ...}


def test_metodo_no_permitido_conserva_allow_y_usa_esquema_del_contrato():
    res = client.request("TRACE", "/auth/login")
    assert res.status_code == 405
    assert "allow" in {k.lower() for k in res.headers}  # RFC 7231
    assert res.json()["code"] == "METHOD_NOT_ALLOWED"
