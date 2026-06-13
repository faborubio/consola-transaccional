"""Métricas del dashboard: rollups con cache Redis (TTL corto) y single-flight.

Aquí el cache SÍ tiene sentido (a diferencia de los listados): la invalidación
es por tiempo, no por evento; el resultado es un objeto pequeño; y correr los
rollups sobre 500k en cada carga degrada sin necesidad. Si Redis no está, se
sirve siempre fresco (fail-open: el dashboard es lectura, no una mutación).

Single-flight: al expirar el TTL, N operadores simultáneos producirían N
recomputaciones concurrentes (estampida — el primo del problema de bola de
nieve de la Fase 3). Un lock `SET NX` deja que UN worker regenere mientras los
demás esperan el resultado en cache.
"""

import asyncio
import logging
from datetime import UTC, datetime

from redis.exceptions import RedisError

from app.config import get_settings
from app.domain.models import DashboardMetrics, MonthBucket, StatusBucket
from app.domain.models import TransactionStatus as S
from app.repository.transactions_repo import TransactionsRepository
from app.services.idempotency import get_redis

logger = logging.getLogger("api.metrics")

CACHE_KEY = "metrics:dashboard"
LOCK_KEY = "metrics:dashboard:lock"
LOCK_TTL_S = 20  # auto-expira si el worker que regenera muere
WAIT_POLLS = 50  # hasta 5s esperando el resultado del que tiene el lock
WAIT_INTERVAL_S = 0.1


class MetricsService:
    def __init__(self, repo: TransactionsRepository | None = None, redis=None) -> None:
        self.repo = repo or TransactionsRepository()
        self.settings = get_settings()
        self._redis = redis if redis is not None else get_redis()

    async def dashboard(self) -> tuple[DashboardMetrics, bool]:
        """Devuelve (métricas, cache_hit)."""
        cached = await self._read_cache()
        if cached is not None:
            return cached, True

        lock = await self._acquire_lock()
        if lock is None:
            # Redis no disponible: sin cache ni lock posibles → computar (fail-open).
            return await self._compute(), False
        if lock:
            try:
                metrics = await self._compute()
                await self._write_cache(metrics)
                return metrics, False
            finally:
                await self._release_lock()

        # Otro worker está regenerando: esperar su resultado en cache.
        for _ in range(WAIT_POLLS):
            await asyncio.sleep(WAIT_INTERVAL_S)
            cached = await self._read_cache()
            if cached is not None:
                return cached, True
        # Si tardó demasiado, computar igual (correcto, sin bloquear indefinido).
        return await self._compute(), False

    async def _acquire_lock(self) -> bool | None:
        """True = lo tomamos; False = otro lo tiene; None = Redis caído."""
        try:
            got = await self._redis.set(LOCK_KEY, "1", nx=True, ex=LOCK_TTL_S)
            return bool(got)
        except RedisError:
            return None

    async def _release_lock(self) -> None:
        try:
            await self._redis.delete(LOCK_KEY)
        except RedisError:
            pass

    async def _compute(self) -> DashboardMetrics:
        rows_status, rows_month = await self.repo.metrics_rollups(
            self.settings.dashboard_timeout_ms
        )

        by_status = {row["_id"]: row for row in rows_status}
        buckets = [
            StatusBucket(
                status=S(status),
                count=by_status.get(status, {}).get("count", 0),
                totalAmount=by_status.get(status, {}).get("totalAmount", 0.0),
            )
            for status in S
        ]
        by_month = [
            MonthBucket(month=row["_id"], count=row["count"], totalAmount=row["totalAmount"])
            for row in rows_month
        ]
        # El total se deriva de los conteos por estado: una query menos.
        total = sum(row["count"] for row in rows_status)

        aprobadas = by_status.get(S.APROBADA, {}).get("count", 0)
        rechazadas = by_status.get(S.RECHAZADA, {}).get("count", 0)
        decididas = aprobadas + rechazadas
        approval_rate = aprobadas / decididas if decididas else 0.0
        in_review = by_status.get(S.EN_REVISION, {}).get("count", 0)

        return DashboardMetrics(
            byStatus=buckets,
            byMonth=by_month,
            totalCount=total,
            approvalRate=round(approval_rate, 4),
            inReview=in_review,
            generatedAt=datetime.now(UTC),
        )

    async def _read_cache(self) -> DashboardMetrics | None:
        try:
            raw = await self._redis.get(CACHE_KEY)
        except RedisError:
            logger.warning("Cache de dashboard no disponible; se sirve fresco")
            return None
        return DashboardMetrics.model_validate_json(raw) if raw else None

    async def _write_cache(self, metrics: DashboardMetrics) -> None:
        try:
            await self._redis.set(
                CACHE_KEY,
                metrics.model_dump_json(),
                ex=self.settings.dashboard_cache_ttl_s,
            )
        except RedisError:
            pass  # el dashboard funciona sin cache, solo más lento
