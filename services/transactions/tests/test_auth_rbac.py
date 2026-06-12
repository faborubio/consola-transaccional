"""Hito Fase 2: el rechazo es a nivel de API, no de UI.

- Sin token, token basura, token expirado o refresh-como-access → 401.
- require_role: un operador no accede a un endpoint de supervisor (403),
  ni siquiera llamando a la API directa.
"""

from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.auth import AuthContext, require_role
from app.api.errors import register_error_handlers
from app.main import app
from tests.conftest import auth_headers

client = TestClient(app)


def test_sin_token_401():
    res = client.get("/transactions")
    assert res.status_code == 401
    assert res.json()["code"] == "UNAUTHORIZED"


def test_token_basura_401():
    res = client.get("/transactions", headers={"Authorization": "Bearer no.es.jwt"})
    assert res.status_code == 401


def test_token_expirado_401():
    res = client.get("/transactions", headers=auth_headers(expired=True))
    assert res.status_code == 401


def test_refresh_no_sirve_como_access_401():
    res = client.get("/transactions", headers=auth_headers(typ="refresh"))
    assert res.status_code == 401


def test_health_sigue_publico():
    assert client.get("/health").status_code == 200


# --- require_role: probado sobre un endpoint protegido real ---
# (el primer endpoint de negocio con rol llega en Fase 4 — /transitions;
#  la dependency se valida aquí con una ruta mínima)

_rbac_app = FastAPI()
register_error_handlers(_rbac_app)


@_rbac_app.post("/solo-supervisor")
async def solo_supervisor(
    user: Annotated[AuthContext, Depends(require_role("supervisor"))],
) -> dict:
    return {"actor": user.username}


_rbac_client = TestClient(_rbac_app)


def test_operador_no_accede_a_endpoint_de_supervisor():
    res = _rbac_client.post("/solo-supervisor", headers=auth_headers(["operador"]))
    assert res.status_code == 403
    assert res.json()["code"] == "FORBIDDEN_ROLE"


def test_supervisor_si_accede():
    res = _rbac_client.post(
        "/solo-supervisor", headers=auth_headers(["supervisor"], username="supervisor1")
    )
    assert res.status_code == 200
    assert res.json() == {"actor": "supervisor1"}


def test_auditor_tampoco_accede():
    res = _rbac_client.post("/solo-supervisor", headers=auth_headers(["auditor"]))
    assert res.status_code == 403
