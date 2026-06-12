"""Cursor compuesto para paginación server-side.

El cursor codifica (valor del campo de orden, _id) — el desempate por _id evita
saltos o duplicados cuando el campo de orden tiene valores repetidos (p. ej.
timestamps iguales a volumen). Es opaco para el cliente: base64(json).
"""

import base64
import json
from datetime import datetime
from typing import Any

SORTABLE_FIELDS = {"createdAt", "amount"}


class InvalidCursorError(ValueError):
    pass


class InvalidSortError(ValueError):
    pass


def parse_sort(sort: str) -> tuple[str, int]:
    """'-createdAt' → ('createdAt', -1); 'amount' → ('amount', 1)."""
    direction = -1 if sort.startswith("-") else 1
    field = sort.lstrip("-")
    if field not in SORTABLE_FIELDS:
        raise InvalidSortError(f"Campo de orden no soportado: {field!r}")
    return field, direction


def encode_cursor(sort_field: str, sort_value: Any, doc_id: str) -> str:
    if isinstance(sort_value, datetime):
        sort_value = sort_value.isoformat()
    payload = json.dumps({"f": sort_field, "v": sort_value, "id": doc_id})
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor(cursor: str, expected_field: str) -> tuple[Any, str]:
    """Devuelve (valor del campo de orden, _id). Valida coherencia con el sort pedido."""
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        field, value, doc_id = payload["f"], payload["v"], payload["id"]
    except (ValueError, KeyError, TypeError) as exc:
        # ValueError cubre binascii.Error, JSONDecodeError y UnicodeDecodeError
        raise InvalidCursorError("Cursor malformado.") from exc
    if field != expected_field:
        raise InvalidCursorError("El cursor no corresponde al ordenamiento solicitado.")
    if field == "createdAt":
        try:
            value = datetime.fromisoformat(value)
        except (ValueError, TypeError) as exc:
            raise InvalidCursorError("Cursor malformado.") from exc
    return value, doc_id


def cursor_filter(sort_field: str, direction: int, value: Any, doc_id: str) -> dict:
    """Comparación compuesta (campo, _id) para continuar después del cursor."""
    op = "$lt" if direction == -1 else "$gt"
    return {
        "$or": [
            {sort_field: {op: value}},
            {sort_field: value, "_id": {op: doc_id}},
        ]
    }
