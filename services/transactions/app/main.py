from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.api.routes_health import router as health_router
from app.api.routes_transactions import router as transactions_router
from app.repository.transactions_repo import close_client


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await close_client()


app = FastAPI(
    title="Consola de Operaciones Transaccionales API",
    version="1.1.0",
    description="Microservicio núcleo transaccional. Contrato fuente: contracts/openapi.yaml.",
    lifespan=lifespan,
)

register_error_handlers(app)
app.include_router(health_router)
app.include_router(transactions_router)


def custom_openapi():
    """Declara bearerAuth como en el contrato; la verificación JWT llega en Fase 2."""
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
    schema["paths"]["/health"]["get"]["security"] = []
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi
