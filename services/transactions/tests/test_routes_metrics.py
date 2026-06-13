"""Capa HTTP de métricas/actividad con servicio y repo mockeados (sin Mongo)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.api.routes_metrics import get_metrics_service, get_repo
from app.domain.models import DashboardMetrics
from app.main import app
from tests.conftest import auth_headers

client = TestClient(app)


def _metrics() -> DashboardMetrics:
    return DashboardMetrics(
        byStatus=[],
        byMonth=[],
        totalCount=500000,
        approvalRate=0.85,
        inReview=25000,
        generatedAt=datetime(2026, 6, 13, tzinfo=UTC),
    )


def test_dashboard_requiere_token():
    assert client.get("/metrics/dashboard").status_code == 401


def test_dashboard_marca_x_cache_miss():
    mock = AsyncMock()
    mock.dashboard.return_value = (_metrics(), False)
    app.dependency_overrides[get_metrics_service] = lambda: mock
    try:
        res = client.get("/metrics/dashboard", headers=auth_headers())
        assert res.status_code == 200
        assert res.headers["X-Cache"] == "MISS"
        assert res.json()["totalCount"] == 500000
    finally:
        app.dependency_overrides.clear()


def test_dashboard_marca_x_cache_hit():
    mock = AsyncMock()
    mock.dashboard.return_value = (_metrics(), True)
    app.dependency_overrides[get_metrics_service] = lambda: mock
    try:
        res = client.get("/metrics/dashboard", headers=auth_headers())
        assert res.headers["X-Cache"] == "HIT"
    finally:
        app.dependency_overrides.clear()


def test_activity_propia_pasa_el_actor_del_token():
    repo = AsyncMock()
    repo.audit_by_actor.return_value = []
    app.dependency_overrides[get_repo] = lambda: repo
    try:
        res = client.get("/activity", headers=auth_headers(user_id="usr_07"))
        assert res.status_code == 200
        repo.audit_by_actor.assert_awaited_once()
        assert repo.audit_by_actor.call_args.kwargs["actor"] == "usr_07"
    finally:
        app.dependency_overrides.clear()


def test_activity_filtra_por_accion():
    repo = AsyncMock()
    repo.audit_by_actor.return_value = []
    app.dependency_overrides[get_repo] = lambda: repo
    try:
        client.get("/activity?action=APROBAR", headers=auth_headers())
        assert repo.audit_by_actor.call_args.kwargs["action"] == "APROBAR"
    finally:
        app.dependency_overrides.clear()


def test_supervisor_no_puede_ver_actividad_ajena():
    repo = AsyncMock()
    app.dependency_overrides[get_repo] = lambda: repo
    try:
        res = client.get(
            "/activity?actor=usr_99", headers=auth_headers(["supervisor"], user_id="usr_09")
        )
        assert res.status_code == 403
        assert res.json()["code"] == "FORBIDDEN_ROLE"
        repo.audit_by_actor.assert_not_called()
    finally:
        app.dependency_overrides.clear()


def test_auditor_si_puede_ver_actividad_ajena():
    repo = AsyncMock()
    repo.audit_by_actor.return_value = []
    app.dependency_overrides[get_repo] = lambda: repo
    try:
        res = client.get(
            "/activity?actor=usr_09", headers=auth_headers(["auditor"], user_id="usr_20")
        )
        assert res.status_code == 200
        assert repo.audit_by_actor.call_args.kwargs["actor"] == "usr_09"
    finally:
        app.dependency_overrides.clear()
