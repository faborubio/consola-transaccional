"""Flujo transaccional completo contra Mongo real (replica set) + fakeredis.

Cubre el hito de Fase 4: transiciones inválidas rechazadas; maker no puede
ser checker; dos requests idempotentes simultáneos → solo uno ejecuta; dos
actores en paralelo → el segundo recibe STALE_VERSION; la auditoría refleja
todo; y un crash simulado entre escrituras no deja estado inconsistente.
"""

import asyncio
import uuid
from datetime import UTC, datetime

import fakeredis.aioredis
import pytest
from pymongo.errors import PyMongoError

from app.config import get_settings
from app.domain.models import TransactionStatus as S
from app.domain.models import TransitionAction as A
from app.repository.transactions_repo import TRANSACTIONS, TransactionsRepository, get_db
from app.services.idempotency import IdempotencyStore
from app.services.transitions_service import TransitionError, TransitionsService

MARKER_CURRENCY = "TRX"  # aísla los docs de este test
MAKER = "usr_01"
CHECKER = "usr_09"


def _txn_doc(txn_id: str, status: str = "PENDIENTE") -> dict:
    now = datetime.now(UTC)
    return {
        "_id": txn_id,
        "amount": 100_000.0,
        "currency": MARKER_CURRENCY,
        "type": "PAGO",
        "status": status,
        "version": 1,
        "source": {"accountId": "CL-900-1", "name": "Origen Tx"},
        "destination": {"accountId": "CL-901-1", "name": "Destino Tx"},
        "createdBy": MAKER,
        "reviewedBy": None,
        "createdAt": now,
        "updatedAt": now,
    }


@pytest.fixture(scope="module", autouse=True)
async def mongo_limpio():
    db = get_db()
    try:
        await db.command("ping")
    except PyMongoError:
        pytest.skip(f"Mongo no disponible en {get_settings().mongo_uri}")
    yield
    await db[TRANSACTIONS].delete_many({"currency": MARKER_CURRENCY})
    await db["audit_entries"].delete_many({"transactionId": {"$regex": "^txn_t4_"}})


@pytest.fixture
def service() -> TransitionsService:
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    return TransitionsService(idempotency=IdempotencyStore(client=fake))


async def _insert(status: str = "PENDIENTE") -> str:
    txn_id = f"txn_t4_{uuid.uuid4().hex[:10]}"
    await get_db()[TRANSACTIONS].insert_one(_txn_doc(txn_id, status))
    return txn_id


def _key() -> str:
    return str(uuid.uuid4())


async def test_aprobar_camino_feliz(service):
    txn_id = await _insert()
    result = await service.execute(
        txn_id=txn_id, action=A.APROBAR, expected_version=1,
        reason=None, actor_id=CHECKER, idempotency_key=_key(),
    )
    assert result.status == S.APROBADA
    assert result.version == 2
    assert result.reviewedBy == CHECKER

    audit = await TransactionsRepository().audit_for(txn_id)
    assert len(audit) == 1
    assert audit[0]["fromStatus"] == "PENDIENTE"
    assert audit[0]["toStatus"] == "APROBADA"
    assert audit[0]["actor"] == CHECKER


async def test_maker_no_puede_aprobar_lo_suyo(service):
    txn_id = await _insert()
    with pytest.raises(TransitionError) as exc:
        await service.execute(
            txn_id=txn_id, action=A.APROBAR, expected_version=1,
            reason=None, actor_id=MAKER, idempotency_key=_key(),
        )
    assert exc.value.code == "SEGREGATION_OF_DUTIES"
    assert exc.value.status_code == 403
    # ni el estado ni la auditoría se tocaron
    doc = await TransactionsRepository().find_by_id(txn_id)
    assert doc["status"] == "PENDIENTE" and doc["version"] == 1
    assert await TransactionsRepository().audit_for(txn_id) == []


async def test_transicion_invalida(service):
    txn_id = await _insert("PENDIENTE")
    with pytest.raises(TransitionError) as exc:
        await service.execute(
            txn_id=txn_id, action=A.REVERTIR, expected_version=1,
            reason="motivo", actor_id=CHECKER, idempotency_key=_key(),
        )
    assert exc.value.code == "INVALID_TRANSITION"


async def test_motivo_obligatorio_para_rechazar(service):
    txn_id = await _insert()
    with pytest.raises(TransitionError) as exc:
        await service.execute(
            txn_id=txn_id, action=A.RECHAZAR, expected_version=1,
            reason="  ", actor_id=CHECKER, idempotency_key=_key(),
        )
    assert exc.value.code == "VALIDATION_ERROR"
    assert exc.value.status_code == 422


async def test_dos_actores_el_segundo_recibe_stale_version(service):
    txn_id = await _insert()
    await service.execute(
        txn_id=txn_id, action=A.ENVIAR_A_REVISION, expected_version=1,
        reason=None, actor_id=CHECKER, idempotency_key=_key(),
    )
    # otro actor leyó la versión 1 antes de la mutación de arriba
    with pytest.raises(TransitionError) as exc:
        await service.execute(
            txn_id=txn_id, action=A.APROBAR, expected_version=1,
            reason=None, actor_id="usr_10", idempotency_key=_key(),
        )
    assert exc.value.code == "STALE_VERSION"
    assert len(await TransactionsRepository().audit_for(txn_id)) == 1


async def test_reintento_idempotente_no_reejecuta(service):
    txn_id = await _insert()
    key = _key()
    first = await service.execute(
        txn_id=txn_id, action=A.APROBAR, expected_version=1,
        reason=None, actor_id=CHECKER, idempotency_key=key,
    )
    retry = await service.execute(
        txn_id=txn_id, action=A.APROBAR, expected_version=1,
        reason=None, actor_id=CHECKER, idempotency_key=key,
    )
    assert retry.model_dump() == first.model_dump()
    # una sola ejecución real: una entrada de auditoría, versión 2 (no 3)
    assert len(await TransactionsRepository().audit_for(txn_id)) == 1
    doc = await TransactionsRepository().find_by_id(txn_id)
    assert doc["version"] == 2


async def test_misma_clave_payload_distinto_conflicto(service):
    txn_id = await _insert()
    key = _key()
    await service.execute(
        txn_id=txn_id, action=A.ENVIAR_A_REVISION, expected_version=1,
        reason=None, actor_id=CHECKER, idempotency_key=key,
    )
    with pytest.raises(TransitionError) as exc:
        await service.execute(
            txn_id=txn_id, action=A.APROBAR, expected_version=2,
            reason=None, actor_id=CHECKER, idempotency_key=key,
        )
    assert exc.value.code == "IDEMPOTENCY_CONFLICT"


async def test_concurrencia_misma_clave_solo_uno_ejecuta(service):
    """Dos requests idempotentes SIMULTÁNEOS: el SET NX garantiza que solo
    uno ejecuta; el otro ve 'en curso' (409) o recibe el resultado guardado."""
    txn_id = await _insert()
    key = _key()

    async def attempt():
        try:
            return await service.execute(
                txn_id=txn_id, action=A.APROBAR, expected_version=1,
                reason=None, actor_id=CHECKER, idempotency_key=key,
            )
        except TransitionError as e:
            return e

    r1, r2 = await asyncio.gather(attempt(), attempt())
    errors = [r for r in (r1, r2) if isinstance(r, TransitionError)]
    successes = [r for r in (r1, r2) if not isinstance(r, TransitionError)]

    assert len(successes) >= 1, "al menos uno debe ejecutar"
    for e in errors:
        assert e.code == "IDEMPOTENCY_CONFLICT"
    # la prueba dura: UNA sola ejecución real
    assert len(await TransactionsRepository().audit_for(txn_id)) == 1
    doc = await TransactionsRepository().find_by_id(txn_id)
    assert doc["version"] == 2


class _FailingAudit:
    async def insert_one(self, *_args, **_kwargs):
        raise RuntimeError("crash simulado entre la escritura de estado y la auditoría")


async def test_crash_entre_escrituras_no_deja_estado_inconsistente(service):
    """La transacción Mongo multi-documento aborta completa: si la auditoría
    no se pudo escribir, el cambio de estado TAMPOCO queda."""
    txn_id = await _insert()
    repo = TransactionsRepository()
    repo.audit = _FailingAudit()
    broken = TransitionsService(
        repo=repo,
        idempotency=IdempotencyStore(
            client=fakeredis.aioredis.FakeRedis(decode_responses=True)
        ),
    )
    with pytest.raises(RuntimeError):
        await broken.execute(
            txn_id=txn_id, action=A.APROBAR, expected_version=1,
            reason=None, actor_id=CHECKER, idempotency_key=_key(),
        )
    doc = await TransactionsRepository().find_by_id(txn_id)
    assert doc["status"] == "PENDIENTE", "el estado se escribió sin su auditoría"
    assert doc["version"] == 1
    assert await TransactionsRepository().audit_for(txn_id) == []
