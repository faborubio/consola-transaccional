"""Idempotencia con SET NX atómico en Redis.

La clave se reserva ATÓMICAMENTE (`SET key processing NX EX 30`) al inicio de
la operación. Un GET-luego-SET tiene su propia carrera: dos requests con la
misma clave en el mismo milisegundo ven ambos la clave ausente y ejecutan dos
veces. La atomicidad del NX es la solución, no un detalle.

Estados de una clave:
- ausente               → nadie la usó: se reserva y se ejecuta
- "__processing__"      → otra request la está ejecutando AHORA
- JSON {hash, response} → ya ejecutada: mismo payload devuelve el resultado
                          guardado; payload distinto es conflicto
"""

import hashlib
import json
from typing import Any

import redis.asyncio as aioredis

from app.config import get_settings

PROCESSING = "__processing__"
CLAIM_TTL_S = 30  # si el proceso muere a mitad, la clave expira y se puede reintentar
RESULT_TTL_S = 24 * 3600

_client: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(get_settings().redis_uri, decode_responses=True)
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


class AlreadyProcessingError(Exception):
    """La misma clave está siendo ejecutada en este instante por otra request."""


class PayloadMismatchError(Exception):
    """La clave ya fue usada con un payload distinto."""


class IdempotencyStore:
    def __init__(self, client: aioredis.Redis | None = None) -> None:
        self.redis = client or get_redis()

    @staticmethod
    def _key(key: str) -> str:
        return f"idem:{key}"

    async def claim(self, key: str, request_hash: str) -> dict | None:
        """Reserva la clave. Devuelve None si la reservamos (hay que ejecutar),
        o la respuesta guardada si ya se ejecutó con el mismo payload."""
        claimed = await self.redis.set(self._key(key), PROCESSING, nx=True, ex=CLAIM_TTL_S)
        if claimed:
            return None
        stored = await self.redis.get(self._key(key))
        if stored is None or stored == PROCESSING:
            raise AlreadyProcessingError
        record = json.loads(stored)
        if record["hash"] != request_hash:
            raise PayloadMismatchError
        return record["response"]

    async def store(self, key: str, request_hash: str, response: dict) -> None:
        await self.redis.set(
            self._key(key),
            json.dumps({"hash": request_hash, "response": response}),
            ex=RESULT_TTL_S,
        )

    async def release(self, key: str) -> None:
        """Libera la reserva cuando la operación falla: el reintento es legítimo."""
        await self.redis.delete(self._key(key))
