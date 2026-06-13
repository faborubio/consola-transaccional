"""Hook de autenticación para Schemathesis (Fase 6).

Sin esto, Schemathesis recibe 401 en cada endpoint protegido y el paso de CI es un
"teatro verde" que no prueba nada. El auth provider hace login REAL contra el servicio
`auth` una sola vez (con refresh cada `refresh_interval` s) e inyecta el bearer en cada
request generado — tanto para el esquema de `auth` como el de `transactions`.

Se carga vía `SCHEMATHESIS_HOOKS=schemathesis_hooks` (con `infra/ci` en el PYTHONPATH).
Credenciales y rol salen de los usuarios demo de auth (`supervisor1` cubre lecturas y
`/transitions`). `AUTH_BASE_URL` apunta al servicio auth (distinto del esquema bajo
prueba cuando se fuzzea `transactions`).
"""

import os

import requests
import schemathesis

AUTH_BASE_URL = os.environ.get("AUTH_BASE_URL", "http://localhost:8001")
USERNAME = os.environ.get("SCHEMATHESIS_USERNAME", "supervisor1")
PASSWORD = os.environ.get("SCHEMATHESIS_PASSWORD", "Demo1234!")


@schemathesis.auth(refresh_interval=300)
class TokenAuth:
    """Login una vez, reutiliza el access token, lo refresca cada 5 min."""

    def get(self, case, ctx):
        resp = requests.post(
            f"{AUTH_BASE_URL}/auth/login",
            json={"username": USERNAME, "password": PASSWORD},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["accessToken"]

    def set(self, case, data, ctx):
        case.headers = case.headers or {}
        case.headers["Authorization"] = f"Bearer {data}"
