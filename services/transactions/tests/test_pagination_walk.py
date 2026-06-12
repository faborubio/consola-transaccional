"""Test de comportamiento del cursor compuesto contra Mongo real.

El riesgo que cubre (plan, Fase 1): un cursor mal hecho con timestamps
duplicados salta o repite filas — bug silencioso que solo aparece a volumen.
Aquí se fuerza el peor caso: N documentos con createdAt idéntico (y amount
idéntico), y se camina página por página verificando que cada documento
aparece exactamente una vez.

Requiere Mongo corriendo (docker compose); si no está, se salta.
"""

from datetime import UTC, datetime

import pytest
from pymongo.errors import PyMongoError

from app.config import get_settings
from app.repository.transactions_repo import TRANSACTIONS, get_db
from app.services.transactions_service import TransactionsService

MARKER_CURRENCY = "TST"  # aísla los docs de este test del seed real
N_DOCS = 50
PAGE_SIZE = 7
SAME_INSTANT = datetime(2026, 5, 1, 12, 0, 0, tzinfo=UTC)
SAME_AMOUNT = 999_999.99


def _doc(i: int) -> dict:
    return {
        "_id": f"txn_walk_{i:04d}",
        "amount": SAME_AMOUNT,
        "currency": MARKER_CURRENCY,
        "type": "PAGO",
        "status": "PENDIENTE",
        "version": 1,
        "source": {"accountId": f"CL-900-{i:08d}", "name": f"Origen Walk {i}"},
        "destination": {"accountId": f"CL-901-{i:08d}", "name": f"Destino Walk {i}"},
        "createdBy": "usr_test",
        "createdAt": SAME_INSTANT,
    }


@pytest.fixture(scope="module", autouse=True)
async def docs_con_empates():
    db = get_db()
    try:
        await db.command("ping")
    except PyMongoError:
        pytest.skip(f"Mongo no disponible en {get_settings().mongo_uri}")
    col = db[TRANSACTIONS]
    await col.delete_many({"currency": MARKER_CURRENCY})
    await col.insert_many([_doc(i) for i in range(N_DOCS)])
    yield
    await col.delete_many({"currency": MARKER_CURRENCY})


async def _walk(sort: str) -> list[str]:
    """Camina todas las páginas y devuelve los ids en orden de aparición."""
    service = TransactionsService()
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(N_DOCS):  # cota dura: jamás más páginas que documentos
        page = await service.list_transactions(
            cursor=cursor,
            limit=PAGE_SIZE,
            sort=sort,
            status=None,
            type_=None,
            min_amount=None,
            max_amount=None,
            currency=MARKER_CURRENCY,
            counterparty=None,
            date_from=None,
            date_to=None,
        )
        seen.extend(t.id for t in page.items)
        if not page.pageInfo.hasNextPage:
            break
        cursor = page.pageInfo.nextCursor
    return seen


@pytest.mark.parametrize("sort", ["-createdAt", "createdAt", "-amount", "amount"])
async def test_caminata_sin_duplicados_ni_saltos(sort: str):
    """Con TODOS los valores de orden empatados, el desempate por _id debe
    entregar cada documento exactamente una vez."""
    seen = await _walk(sort)
    esperados = {f"txn_walk_{i:04d}" for i in range(N_DOCS)}

    assert len(seen) == N_DOCS, f"se vieron {len(seen)} documentos, esperaba {N_DOCS}"
    assert len(set(seen)) == N_DOCS, "hay documentos repetidos entre páginas"
    assert set(seen) == esperados, "faltan o sobran documentos"


async def test_ultima_pagina_reporta_fin():
    seen_pages = 0
    service = TransactionsService()
    cursor: str | None = None
    while True:
        page = await service.list_transactions(
            cursor=cursor,
            limit=PAGE_SIZE,
            sort="-createdAt",
            status=None,
            type_=None,
            min_amount=None,
            max_amount=None,
            currency=MARKER_CURRENCY,
            counterparty=None,
            date_from=None,
            date_to=None,
        )
        seen_pages += 1
        if not page.pageInfo.hasNextPage:
            assert page.pageInfo.nextCursor is None
            break
        cursor = page.pageInfo.nextCursor
        assert seen_pages <= N_DOCS

    # 50 docs / 7 por página = 8 páginas (la última con 1)
    assert seen_pages == (N_DOCS + PAGE_SIZE - 1) // PAGE_SIZE
