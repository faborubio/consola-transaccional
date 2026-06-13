"""Acceso a MongoDB para transacciones y auditoría.

Cliente async oficial de PyMongo (Motor está en mantenimiento). La conexión es
perezosa: el cliente no abre sockets hasta la primera operación, lo que permite
levantar la app (y testear /health) sin Mongo disponible.
"""

import re
from datetime import datetime
from typing import Any

from pymongo import AsyncMongoClient

from app.config import get_settings

TRANSACTIONS = "transactions"
AUDIT = "audit_entries"

_client: AsyncMongoClient | None = None


def get_db():
    global _client
    settings = get_settings()
    if _client is None:
        _client = AsyncMongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)
    return _client[settings.mongo_db]


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


class TransactionsRepository:
    def __init__(self) -> None:
        db = get_db()
        self.transactions = db[TRANSACTIONS]
        self.audit = db[AUDIT]

    async def list_page(
        self,
        query: dict[str, Any],
        sort_field: str,
        direction: int,
        limit: int,
    ) -> list[dict]:
        """Trae limit+1 documentos: el extra señala si hay página siguiente."""
        cursor = (
            self.transactions.find(query)
            .sort([(sort_field, direction), ("_id", direction)])
            .limit(limit + 1)
            .max_time_ms(get_settings().query_timeout_ms)
        )
        return await cursor.to_list(length=limit + 1)

    async def estimated_total(self, has_filters: bool) -> int | None:
        """Conteo aproximado solo sin filtros — count() exacto a 500k es costoso."""
        if has_filters:
            return None
        return await self.transactions.estimated_document_count()

    async def find_by_id(self, txn_id: str) -> dict | None:
        return await self.transactions.find_one({"_id": txn_id})

    async def audit_for(self, txn_id: str) -> list[dict]:
        cursor = self.audit.find({"transactionId": txn_id}).sort("at", 1)
        return await cursor.to_list(length=None)

    async def ensure_indexes(self) -> None:
        """Índices ESR para los patrones de acceso dominantes (ver Fase 1)."""
        await self.transactions.create_index([("createdAt", -1), ("_id", -1)])
        await self.transactions.create_index([("amount", -1), ("_id", -1)])
        await self.transactions.create_index([("status", 1), ("createdAt", -1), ("_id", -1)])
        await self.transactions.create_index([("status", 1), ("amount", -1), ("_id", -1)])
        await self.transactions.create_index([("searchKeys", 1)])
        await self.audit.create_index([("transactionId", 1), ("at", 1)])


def build_list_query(
    *,
    status: list[str] | None,
    type_: str | None,
    min_amount: float | None,
    max_amount: float | None,
    currency: str | None,
    counterparty: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if status:
        query["status"] = {"$in": status}
    if type_:
        query["type"] = type_
    amount: dict[str, float] = {}
    if min_amount is not None:
        amount["$gte"] = min_amount
    if max_amount is not None:
        amount["$lte"] = max_amount
    if amount:
        query["amount"] = amount
    if currency:
        query["currency"] = currency
    if counterparty:
        # Prefijo anclado sobre searchKeys (nombres y cuentas normalizados en
        # minúsculas, índice multikey). Una regex sin anclar no usa índices.
        needle = re.escape(counterparty.strip().lower())
        query["searchKeys"] = {"$regex": f"^{needle}"}
    created: dict[str, datetime] = {}
    if date_from:
        created["$gte"] = date_from
    if date_to:
        created["$lte"] = date_to
    if created:
        query["createdAt"] = created
    return query
