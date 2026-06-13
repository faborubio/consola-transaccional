"""Tests de la capa HTTP con el servicio mockeado — no requieren Mongo."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.api.routes_transactions import get_service
from app.domain.models import PageInfo, Transaction, TransactionPage
from app.main import app
from tests.conftest import auth_headers

client = TestClient(app)
HEADERS = auth_headers()


def _sample_txn() -> Transaction:
    return Transaction(
        id="txn_8f3a1c2e",
        amount=1250000.0,
        currency="CLP",
        type="PAGO",
        status="PENDIENTE",
        version=1,
        source={"accountId": "CL-001-1", "name": "Origen SA"},
        destination={"accountId": "CL-001-2", "name": "Destino SA"},
        createdBy="usr_01",
        createdAt=datetime(2026, 3, 1, tzinfo=UTC),
    )


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok", "service": "transactions"}


def test_list_transactions_ok():
    mock = AsyncMock()
    mock.list_transactions.return_value = TransactionPage(
        items=[_sample_txn()],
        pageInfo=PageInfo(hasNextPage=False, nextCursor=None, totalEstimate=1),
    )
    app.dependency_overrides[get_service] = lambda: mock
    try:
        res = client.get("/transactions", headers=HEADERS)
        assert res.status_code == 200
        body = res.json()
        assert body["items"][0]["id"] == "txn_8f3a1c2e"
        assert body["pageInfo"]["hasNextPage"] is False
    finally:
        app.dependency_overrides.clear()


def test_validation_error_uses_contract_schema():
    res = client.get("/transactions", params={"limit": 0}, headers=HEADERS)
    assert res.status_code == 422
    body = res.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["message"]
    assert any(d["field"] == "limit" for d in body["details"])


def test_counterparty_corto_rechazado():
    """Prefijos de <3 caracteres degradan el índice multikey: 422 del contrato."""
    res = client.get("/transactions", params={"counterparty": "co"}, headers=HEADERS)
    assert res.status_code == 422
    body = res.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert any(d["field"] == "counterparty" for d in body["details"])


def test_query_timeout_responde_503():
    """ExecutionTimeout de Mongo (maxTimeMS) → 503 QUERY_TIMEOUT accionable."""
    from pymongo.errors import ExecutionTimeout

    mock = AsyncMock()
    mock.list_transactions.side_effect = ExecutionTimeout("operation exceeded time limit")
    app.dependency_overrides[get_service] = lambda: mock
    try:
        res = client.get("/transactions", headers=HEADERS)
        assert res.status_code == 503
        assert res.json()["code"] == "QUERY_TIMEOUT"
    finally:
        app.dependency_overrides.clear()


def test_excepcion_no_manejada_usa_esquema_del_contrato():
    """Una excepción inesperada (bug, dependencia caída) responde 500 con el
    esquema code/message, no el 'detail' por defecto de FastAPI."""
    mock = AsyncMock()
    mock.list_transactions.side_effect = RuntimeError("boom inesperado")
    app.dependency_overrides[get_service] = lambda: mock
    # raise_server_exceptions=False: queremos la respuesta JSON, no que propague
    local = TestClient(app, raise_server_exceptions=False)
    try:
        res = local.get("/transactions", headers=HEADERS)
        assert res.status_code == 500
        assert res.json() == {"code": "INTERNAL", "message": "Error interno del servidor."}
    finally:
        app.dependency_overrides.clear()


def test_not_found_uses_contract_schema():
    mock = AsyncMock()
    mock.get_transaction.return_value = None
    app.dependency_overrides[get_service] = lambda: mock
    try:
        res = client.get("/transactions/txn_inexistente", headers=HEADERS)
        assert res.status_code == 404
        assert res.json() == {"code": "NOT_FOUND", "message": "Transacción no encontrada."}
    finally:
        app.dependency_overrides.clear()
