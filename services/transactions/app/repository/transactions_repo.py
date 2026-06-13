"""Acceso a MongoDB para transacciones y auditoría.

Cliente async oficial de PyMongo (Motor está en mantenimiento). La conexión es
perezosa: el cliente no abre sockets hasta la primera operación, lo que permite
levantar la app (y testear /health) sin Mongo disponible.
"""

import asyncio
import re
from datetime import datetime
from typing import Any

from pymongo import AsyncMongoClient, ReturnDocument

from app.config import get_settings

TRANSACTIONS = "transactions"
AUDIT = "audit_entries"

_client: AsyncMongoClient | None = None


class StaleVersionError(Exception):
    """El documento cambió desde que el cliente lo leyó (bloqueo optimista)."""


def get_client() -> AsyncMongoClient:
    global _client
    if _client is None:
        _client = AsyncMongoClient(get_settings().mongo_uri, serverSelectionTimeoutMS=5000)
    return _client


def get_db():
    return get_client()[get_settings().mongo_db]


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


class TransactionsRepository:
    def __init__(self, db=None) -> None:
        # db inyectable: permite aislar tests en una colección propia sin
        # tocar los datos de desarrollo.
        db = db if db is not None else get_db()
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

    async def apply_transition(
        self,
        txn_id: str,
        expected_version: int,
        update_fields: dict[str, Any],
        audit_doc: dict[str, Any],
    ) -> dict:
        """Estado + auditoría en UNA transacción Mongo (requiere replica set).

        Sin la sesión transaccional, un crash entre las dos escrituras deja el
        registro inconsistente — una auditoría que puede mentir es peor que no
        tener auditoría.

        El update filtra por versión (bloqueo optimista): si otro actor mutó
        el documento entremedio, no matchea, y se responde StaleVersionError
        — la transacción completa se aborta.
        """
        client = get_client()
        async with client.start_session() as session:
            async with await session.start_transaction():
                doc = await self.transactions.find_one_and_update(
                    {"_id": txn_id, "version": expected_version},
                    {"$set": update_fields, "$inc": {"version": 1}},
                    return_document=ReturnDocument.AFTER,
                    session=session,
                )
                if doc is None:
                    # aborta la transacción al salir por excepción
                    raise StaleVersionError(txn_id)
                await self.audit.insert_one(audit_doc, session=session)
        return doc

    async def metrics_rollups(self, timeout_ms: int) -> tuple[list[dict], list[dict]]:
        """Devuelve (porEstado, porMes) con los dos $group ejecutados en paralelo.

        NO se usa $facet a propósito: medido sobre 500k, $facet tarda ~69s
        (materializa toda la entrada en memoria y sus sub-pipelines no usan
        índices), mientras que los dos $group por separado tardan ~1.2s en
        total. La intuición "una sola pasada" es falsa aquí; ver el registro
        de problemas resueltos. El conteo total se deriva de porEstado (no
        hace falta una tercera query).
        """
        by_status, by_month = await asyncio.gather(
            self._group_by_status(timeout_ms),
            self._group_by_month(timeout_ms),
        )
        return by_status, by_month

    async def _group_by_status(self, timeout_ms: int) -> list[dict]:
        cursor = await self.transactions.aggregate(
            [
                {
                    "$group": {
                        "_id": "$status",
                        "count": {"$sum": 1},
                        "totalAmount": {"$sum": "$amount"},
                    }
                }
            ],
            maxTimeMS=timeout_ms,
        )
        return await cursor.to_list(length=None)

    async def _group_by_month(self, timeout_ms: int) -> list[dict]:
        cursor = await self.transactions.aggregate(
            [
                {
                    "$group": {
                        "_id": {"$dateToString": {"format": "%Y-%m", "date": "$createdAt"}},
                        "count": {"$sum": 1},
                        "totalAmount": {"$sum": "$amount"},
                    }
                },
                {"$sort": {"_id": 1}},
            ],
            maxTimeMS=timeout_ms,
        )
        return await cursor.to_list(length=None)

    async def audit_by_actor(
        self, actor: str, action: str | None, limit: int
    ) -> list[dict]:
        query: dict[str, Any] = {"actor": actor}
        if action:
            query["action"] = action
        cursor = self.audit.find(query).sort("at", -1).limit(limit)
        return await cursor.to_list(length=limit)

    async def ensure_indexes(self) -> None:
        """Índices ESR para los patrones de acceso dominantes (ver Fase 1)."""
        await self.transactions.create_index([("createdAt", -1), ("_id", -1)])
        await self.transactions.create_index([("amount", -1), ("_id", -1)])
        await self.transactions.create_index([("status", 1), ("createdAt", -1), ("_id", -1)])
        await self.transactions.create_index([("status", 1), ("amount", -1), ("_id", -1)])
        await self.transactions.create_index([("searchKeys", 1)])
        await self.audit.create_index([("transactionId", 1), ("at", 1)])
        # "Mi actividad": auditoría por actor, más reciente primero.
        await self.audit.create_index([("actor", 1), ("at", -1)])


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
