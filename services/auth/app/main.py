"""Esqueleto del servicio auth — se implementa en Fase 2.

Pendiente (ver plan): login/refresh/me, JWT RS256 (solo este servicio firma),
hashing argon2, rotación de refresh tokens con detección de reuso, RBAC.
"""

from fastapi import FastAPI

app = FastAPI(
    title="Consola de Operaciones Transaccionales API",
    version="1.1.0",
    description="Microservicio de autenticación. Contrato fuente: contracts/openapi.yaml.",
)


@app.get("/health", operation_id="getHealth", summary="Liveness probe", tags=["health"])
async def get_health() -> dict[str, str]:
    return {"status": "ok", "service": "auth"}
