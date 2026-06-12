"""Logs estructurados (JSON) + correlation ID.

El interceptor de Angular genera X-Correlation-Id, el gateway lo propaga y este
middleware lo adopta (o genera uno si falta): cada línea de log del request lo
lleva, y vuelve en la respuesta. Un request se sigue de punta a punta.

Solo stdlib — sin dependencias nuevas por un formatter.
"""

import json
import logging
import time
import uuid
from contextvars import ContextVar

from fastapi import FastAPI, Request

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="-")

access_logger = logging.getLogger("api.access")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlationId": correlation_id.get(),
        }
        extra = getattr(record, "extra_fields", None)
        if extra:
            entry.update(extra)
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    # El middleware ya emite una línea por request, con correlation ID;
    # el access log plano de uvicorn sería ruido duplicado.
    logging.getLogger("uvicorn.access").disabled = True


def register_observability(app: FastAPI) -> None:
    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next):
        cid = request.headers.get("x-correlation-id") or str(uuid.uuid4())
        token = correlation_id.set(cid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            access_logger.info(
                "%s %s -> %s",
                request.method,
                request.url.path,
                response.status_code,
                extra={
                    "extra_fields": {
                        "method": request.method,
                        "path": request.url.path,
                        "status": response.status_code,
                        "durationMs": round((time.perf_counter() - start) * 1000, 1),
                    }
                },
            )
            response.headers["X-Correlation-Id"] = cid
            return response
        finally:
            correlation_id.reset(token)
