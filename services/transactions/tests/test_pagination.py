from datetime import UTC, datetime

import pytest

from app.services import pagination


def test_roundtrip_cursor_datetime():
    created = datetime(2026, 3, 14, 12, 30, 45, tzinfo=UTC)
    cursor = pagination.encode_cursor("createdAt", created, "txn_abc123")
    value, doc_id = pagination.decode_cursor(cursor, "createdAt")
    assert value == created
    assert doc_id == "txn_abc123"


def test_roundtrip_cursor_amount():
    cursor = pagination.encode_cursor("amount", 1250000.0, "txn_x")
    value, doc_id = pagination.decode_cursor(cursor, "amount")
    assert value == 1250000.0
    assert doc_id == "txn_x"


def test_cursor_field_mismatch_rejected():
    cursor = pagination.encode_cursor("amount", 10.0, "txn_x")
    with pytest.raises(pagination.InvalidCursorError):
        pagination.decode_cursor(cursor, "createdAt")


def test_malformed_cursor_rejected():
    with pytest.raises(pagination.InvalidCursorError):
        pagination.decode_cursor("no-es-base64!!!", "createdAt")


def test_parse_sort():
    assert pagination.parse_sort("-createdAt") == ("createdAt", -1)
    assert pagination.parse_sort("amount") == ("amount", 1)
    with pytest.raises(pagination.InvalidSortError):
        pagination.parse_sort("-password")


def test_cursor_filter_compound_desc():
    created = datetime(2026, 1, 1, tzinfo=UTC)
    f = pagination.cursor_filter("createdAt", -1, created, "txn_5")
    assert f == {
        "$or": [
            {"createdAt": {"$lt": created}},
            {"createdAt": created, "_id": {"$lt": "txn_5"}},
        ]
    }
