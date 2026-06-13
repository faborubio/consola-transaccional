"""Esquema de error uniforme (code + message + details) en toda la API.

FastAPI emite por defecto 422 con su propio HTTPValidationError; eso rompería
tanto el contrato como el candado anti-drift. Estos handlers fuerzan el formato
del contrato en todos los caminos de error.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.models import Error, ErrorDetail

logger = logging.getLogger("api.error")


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=Error(code=exc.code, message=exc.message).model_dump(exclude_none=True),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            ErrorDetail(
                field=".".join(str(p) for p in err["loc"][1:]) or str(err["loc"][0]),
                issue=err["msg"],
            )
            for err in exc.errors()
        ]
        body = Error(code="VALIDATION_ERROR", message="Parámetros inválidos.", details=details)
        return JSONResponse(status_code=422, content=body.model_dump(exclude_none=True))

    @app.exception_handler(Exception)
    async def unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
        # Red de seguridad: cualquier excepción no manejada (bug, dependencia
        # caída) responde con el esquema del contrato, no el detail por defecto
        # de FastAPI. El log lleva el correlation ID (lo inyecta el formatter).
        logger.exception("Excepción no manejada: %s", exc)
        return JSONResponse(
            status_code=500,
            content=Error(code="INTERNAL", message="Error interno del servidor.").model_dump(
                exclude_none=True
            ),
        )
