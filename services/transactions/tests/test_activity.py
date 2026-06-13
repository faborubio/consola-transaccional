"""'Mi actividad': la auditoría por actor — la respuesta correcta a 'qué hice',
estable aunque otro actor opere después (a diferencia de reviewedBy)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from pymongo.errors import PyMongoError

from app.config import get_settings
from app.repository.transactions_repo import TransactionsRepository, get_db


@pytest.fixture(scope="module", autouse=True)
async def auditoria():
    db = get_db()
    try:
        await db.command("ping")
    except PyMongoError:
        pytest.skip(f"Mongo no disponible en {get_settings().mongo_uri}")
    base = datetime(2026, 5, 1, tzinfo=UTC)
    docs = [
        # supervisor A envía a revisión
        {"_id": f"aud_act_{uuid.uuid4().hex[:8]}", "transactionId": "txn_act_1",
         "action": "ENVIAR_A_REVISION", "fromStatus": "PENDIENTE", "toStatus": "EN_REVISION",
         "actor": "sup_A", "reason": None, "at": base},
        # supervisor B aprueba LA MISMA transacción después
        {"_id": f"aud_act_{uuid.uuid4().hex[:8]}", "transactionId": "txn_act_1",
         "action": "APROBAR", "fromStatus": "EN_REVISION", "toStatus": "APROBADA",
         "actor": "sup_B", "reason": None, "at": base + timedelta(hours=1)},
        # A rechaza otra
        {"_id": f"aud_act_{uuid.uuid4().hex[:8]}", "transactionId": "txn_act_2",
         "action": "RECHAZAR", "fromStatus": "PENDIENTE", "toStatus": "RECHAZADA",
         "actor": "sup_A", "reason": "duplicada", "at": base + timedelta(hours=2)},
    ]
    await db["audit_entries"].insert_many(docs)
    yield
    await db["audit_entries"].delete_many({"transactionId": {"$regex": "^txn_act_"}})


async def test_actividad_del_actor_incluye_lo_que_envio_a_revision():
    repo = TransactionsRepository()
    acts = await repo.audit_by_actor("sup_A", action=None, limit=50)
    txns = {a["transactionId"] for a in acts}
    # Aunque B aprobó txn_act_1 después, el envío a revisión de A SIGUE ahí:
    # esto es lo que reviewedBy=A no podría mostrar (reviewedBy ahora es B).
    assert "txn_act_1" in txns
    assert "txn_act_2" in txns
    assert all(a["actor"] == "sup_A" for a in acts)
    # orden: más reciente primero
    assert acts[0]["at"] >= acts[-1]["at"]


async def test_filtro_por_accion():
    repo = TransactionsRepository()
    solo_revision = await repo.audit_by_actor("sup_A", action="ENVIAR_A_REVISION", limit=50)
    assert len(solo_revision) == 1
    assert solo_revision[0]["transactionId"] == "txn_act_1"


async def test_actividad_del_otro_actor_no_ve_lo_ajeno():
    repo = TransactionsRepository()
    acts = await repo.audit_by_actor("sup_B", action=None, limit=50)
    assert all(a["actor"] == "sup_B" for a in acts)
    assert {a["transactionId"] for a in acts} == {"txn_act_1"}
