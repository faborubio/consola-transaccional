"""Métricas: agregación $facet contra Mongo real + cache con fakeredis."""

import uuid
from datetime import UTC, datetime

import fakeredis.aioredis
import pytest
from pymongo.errors import PyMongoError

from app.config import get_settings
from app.repository.transactions_repo import TRANSACTIONS, TransactionsRepository, get_client
from app.services.metrics_service import CACHE_KEY, MetricsService

# Base aislada: el $facet escanea TODA la colección; sobre los 500k de
# desarrollo cada test tardaría segundos. Aquí escanea solo estos 5 docs.
TEST_DB = "transactions_metrics_test"


def _doc(status: str, amount: float, month: int) -> dict:
    return {
        "_id": f"txn_met_{uuid.uuid4().hex[:8]}",
        "amount": amount,
        "currency": "MET",
        "type": "PAGO",
        "status": status,
        "version": 1,
        "source": {"accountId": "CL-1", "name": "A"},
        "destination": {"accountId": "CL-2", "name": "B"},
        "createdBy": "usr_01",
        "createdAt": datetime(2026, month, 15, tzinfo=UTC),
    }


@pytest.fixture(scope="module", autouse=True)
async def datos():
    try:
        client = get_client()
        await client.admin.command("ping")
    except PyMongoError:
        pytest.skip(f"Mongo no disponible en {get_settings().mongo_uri}")
    db = client[TEST_DB]
    await db[TRANSACTIONS].delete_many({})
    await db[TRANSACTIONS].insert_many(
        [
            _doc("APROBADA", 100.0, 1),
            _doc("APROBADA", 200.0, 1),
            _doc("APROBADA", 300.0, 2),
            _doc("RECHAZADA", 50.0, 2),
            _doc("EN_REVISION", 999.0, 3),
        ]
    )
    yield
    await client.drop_database(TEST_DB)


@pytest.fixture
def service() -> MetricsService:
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    repo = TransactionsRepository(db=get_client()[TEST_DB])
    return MetricsService(repo=repo, redis=fake)


async def test_facet_calcula_todas_las_metricas(service):
    metrics, cache_hit = await service.dashboard()
    assert cache_hit is False

    por_estado = {b.status: b for b in metrics.byStatus}
    # 3 aprobadas (100+200+300=600), 1 rechazada, 1 en revisión
    assert por_estado["APROBADA"].count == 3
    assert por_estado["APROBADA"].totalAmount == 600.0
    assert por_estado["RECHAZADA"].count == 1
    assert por_estado["EN_REVISION"].count == 1
    # todos los estados presentes aunque tengan 0 (PENDIENTE, REVERTIDA)
    assert {b.status for b in metrics.byStatus} == {
        "PENDIENTE", "EN_REVISION", "APROBADA", "RECHAZADA", "REVERTIDA"
    }


async def test_approval_rate_y_meses(service):
    metrics, _ = await service.dashboard()
    # aprobadas 3 / (aprobadas 3 + rechazadas 1) = 0.75
    assert metrics.approvalRate == 0.75
    assert metrics.inReview == 1
    meses = {b.month for b in metrics.byMonth}
    assert {"2026-01", "2026-02", "2026-03"} <= meses


async def test_segundo_request_sirve_del_cache(service):
    _, hit1 = await service.dashboard()
    _, hit2 = await service.dashboard()
    assert hit1 is False  # MISS: calculó
    assert hit2 is True  # HIT: sirvió del cache


async def test_cache_expira(service):
    await service.dashboard()
    # forzar expiración borrando la clave (equivale al TTL)
    await service._redis.delete(CACHE_KEY)
    _, hit = await service.dashboard()
    assert hit is False


async def test_single_flight_evita_estampida():
    """Dos cargas simultáneas tras un MISS → UNA sola recomputación; el segundo
    espera y recibe el resultado del cache (no escanea la colección de nuevo)."""
    import asyncio

    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    repo = TransactionsRepository(db=get_client()[TEST_DB])

    computes = {"n": 0}
    original = repo.metrics_rollups

    async def counting_rollups(timeout_ms):
        computes["n"] += 1
        await asyncio.sleep(0.2)  # simula el costo del scan, da tiempo a la carrera
        return await original(timeout_ms)

    repo.metrics_rollups = counting_rollups
    svc = MetricsService(repo=repo, redis=fake)

    r1, r2 = await asyncio.gather(svc.dashboard(), svc.dashboard())

    assert computes["n"] == 1, "single-flight debe recomputar una sola vez"
    hits = sorted([r1[1], r2[1]])
    assert hits == [False, True]  # uno computó (MISS), el otro esperó (HIT)
