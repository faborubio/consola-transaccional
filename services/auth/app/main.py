import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from app.api.errors import register_error_handlers
from app.api.routes_auth import router as auth_router
from app.config import get_settings
from app.observability import register_observability, setup_logging
from app.repository.users_repo import UsersRepository, close_client
from app.services.passwords import hash_password

setup_logging()
logger = logging.getLogger(__name__)

# Alineados con el seed de transactions: usr_01 es maker, usr_09 es checker —
# así el maker-checker de Fase 4 se puede demostrar con los usuarios demo.
DEMO_USERS = [
    {"_id": "usr_01", "username": "operador1", "fullName": "Ana Pérez", "roles": ["operador"]},
    {"_id": "usr_09", "username": "supervisor1", "fullName": "Luis Soto", "roles": ["supervisor"]},
    {"_id": "usr_20", "username": "auditor1", "fullName": "Rosa Fuentes", "roles": ["auditor"]},
]


async def bootstrap_demo_users(repo: UsersRepository) -> None:
    settings = get_settings()
    if not settings.bootstrap_demo_users or await repo.count_users() > 0:
        return
    hashed = hash_password(settings.demo_password)
    for user in DEMO_USERS:
        await repo.insert_user({**user, "passwordHash": hashed})
    logger.info("Usuarios demo creados: %s", ", ".join(u["username"] for u in DEMO_USERS))


@asynccontextmanager
async def lifespan(_: FastAPI):
    try:
        repo = UsersRepository()
        await repo.ensure_indexes()
        await bootstrap_demo_users(repo)
    except Exception:  # noqa: BLE001
        logger.warning("No se pudo inicializar la base de auth al arranque", exc_info=True)
    yield
    await close_client()


app = FastAPI(
    title="Consola de Operaciones Transaccionales API",
    version="1.1.0",
    description="Microservicio de autenticación. Contrato fuente: contracts/openapi.yaml.",
    lifespan=lifespan,
)

register_observability(app)
register_error_handlers(app)
app.include_router(auth_router)


class HealthStatus(BaseModel):
    status: str
    service: str


@app.get("/health", operation_id="getHealth", summary="Liveness probe", tags=["health"])
async def get_health() -> HealthStatus:
    return HealthStatus(status="ok", service=get_settings().service_name)


def custom_openapi():
    """Esquema de seguridad como en el contrato: global bearerAuth; login,
    refresh y health son públicos; el HTTPBearer por-operación se elimina
    (lo cubre la seguridad global)."""
    if app.openapi_schema:
        return app.openapi_schema
    from fastapi.openapi.utils import get_openapi

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    schema.setdefault("components", {})["securitySchemes"] = {
        "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
    }
    schema["security"] = [{"bearerAuth": []}]
    public_paths = ("/health", "/auth/login", "/auth/refresh", "/auth/logout")
    for path, public in ((p, True) for p in public_paths):
        for op in schema["paths"].get(path, {}).values():
            op["security"] = [] if public else op.get("security")
    for ops in schema["paths"].values():
        for op in ops.values():
            if op.get("security") == [{"HTTPBearer": []}]:
                del op["security"]
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi
