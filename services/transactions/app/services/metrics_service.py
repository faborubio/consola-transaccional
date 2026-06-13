"""Métricas del dashboard: un solo $facet + cache Redis con TTL corto.

Aquí el cache SÍ tiene sentido (a diferencia de los listados): la invalidación
es por tiempo, no por evento; el resultado es un objeto pequeño; y correr el
pipeline sobre 500k en cada carga degrada sin necesidad. Si Redis no está, se
sirve siempre fresco (fail-open: el dashboard es lectura, no una mutación).
"""

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

        metrics = await self._compute()
        await self._write_cache(metrics)
        return metrics, False

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
