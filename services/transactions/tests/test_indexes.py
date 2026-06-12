"""Test obligatorio de Fase 1: explain() sobre cada patrón de listado.

Falla si el plan ganador contiene COLLSCAN (escaneo completo de la colección)
o un SORT bloqueante en memoria (a 500k documentos excede el límite de 32MB).
"Tiene índices" no se afirma: se prueba.

Requiere Mongo corriendo (docker compose); si no está, se salta.
"""

from datetime import UTC, datetime

import pytest
from pymongo.errors import PyMongoError

from app.config import get_settings
from app.repository.transactions_repo import (
    TRANSACTIONS,
    TransactionsRepository,
    build_list_query,
    get_db,
)
from app.services import pagination

# (descripción, filtros para build_list_query, sort)
DOMINANT_QUERIES = [
    ("sin filtros, más recientes", {}, "-createdAt"),
    ("por estado, más recientes", {"status": ["PENDIENTE", "EN_REVISION"]}, "-createdAt"),
    ("por estado, mayor monto", {"status": ["APROBADA"]}, "-amount"),
    (
        "por estado y rango de fechas",
        {
            "status": ["PENDIENTE"],
            "date_from": datetime(2026, 1, 1, tzinfo=UTC),
            "date_to": datetime(2026, 6, 1, tzinfo=UTC),
        },
        "-createdAt",
    ),
    ("mayor monto, sin filtros", {}, "-amount"),
]

parametrize_queries = pytest.mark.parametrize(
    ("desc", "partial", "sort"),
    DOMINANT_QUERIES,
    ids=[d for d, _, _ in DOMINANT_QUERIES],
)

FORBIDDEN_STAGES = {"COLLSCAN", "SORT"}


def _full_filters(partial: dict) -> dict:
    defaults = dict(
        status=None, type_=None, min_amount=None, max_amount=None,
        currency=None, counterparty=None, date_from=None, date_to=None,
    )
    return {**defaults, **partial}


def _stages(plan: dict) -> set[str]:
    """Recorre el árbol del winningPlan y junta los nombres de stage."""
    found = set()
    stack = [plan]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if "stage" in node:
                found.add(node["stage"])
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return found


async def _explain(query: dict, sort_field: str, direction: int) -> dict:
    db = get_db()
    return await db.command(
        "explain",
        {
            "find": TRANSACTIONS,
            "filter": query,
            "sort": {sort_field: direction, "_id": direction},
            "limit": 26,
        },
        verbosity="queryPlanner",
    )


@pytest.fixture(scope="module", autouse=True)
async def mongo_disponible():
    try:
        db = get_db()
        await db.command("ping")
    except PyMongoError:
        pytest.skip(f"Mongo no disponible en {get_settings().mongo_uri}")
    await TransactionsRepository().ensure_indexes()


@parametrize_queries
async def test_listado_usa_indices(desc: str, partial: dict, sort: str):
    sort_field, direction = pagination.parse_sort(sort)
    query = build_list_query(**_full_filters(partial))

    plan = await _explain(query, sort_field, direction)
    stages = _stages(plan["queryPlanner"]["winningPlan"])
    bad = stages & FORBIDDEN_STAGES
    assert not bad, f"[{desc}] plan ganador usa {bad}; stages: {stages}"


async def test_counterparty_prefijo_usa_indice():
    """La búsqueda por contraparte es prefijo anclado sobre searchKeys (multikey).

    Se prohíbe COLLSCAN pero se permite SORT: con un rango en el campo líder
    del índice el orden no se hereda, y el SORT con limit es top-k de memoria
    acotada — aceptable para una acción de búsqueda. Un substring sin anclar
    sería COLLSCAN siempre; ese es el caso que este test impide reintroducir.
    """
    query = build_list_query(**_full_filters({"counterparty": "comercial"}))
    assert "searchKeys" in query, "counterparty debe buscar sobre searchKeys"

    plan = await _explain(query, "createdAt", -1)
    stages = _stages(plan["queryPlanner"]["winningPlan"])
    assert "COLLSCAN" not in stages, f"búsqueda por contraparte escanea la colección: {stages}"
    assert "IXSCAN" in stages


@parametrize_queries
async def test_listado_con_cursor_usa_indices(desc: str, partial: dict, sort: str):
    """La query de 'página siguiente' (comparación compuesta) también debe usar índice."""
    sort_field, direction = pagination.parse_sort(sort)
    base = build_list_query(**_full_filters(partial))

    cursor_value = datetime(2026, 3, 1, tzinfo=UTC) if sort_field == "createdAt" else 500_000.0
    after = pagination.cursor_filter(sort_field, direction, cursor_value, "txn_ffffffffffff")
    query = {"$and": [base, after]} if base else after

    plan = await _explain(query, sort_field, direction)
    stages = _stages(plan["queryPlanner"]["winningPlan"])
    bad = stages & FORBIDDEN_STAGES
    assert not bad, f"[{desc} + cursor] plan ganador usa {bad}; stages: {stages}"
