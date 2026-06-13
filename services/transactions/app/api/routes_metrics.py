from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.api.auth import AuthContext, current_user
from app.api.errors import ApiError
from app.domain.models import AuditEntry, DashboardMetrics, Error, TransitionAction
from app.repository.transactions_repo import TransactionsRepository
from app.services.metrics_service import MetricsService

router = APIRouter(tags=["metrics"], dependencies=[Depends(current_user)])

ERROR_401 = {"model": Error, "description": "Token ausente, inválido o expirado."}


def get_metrics_service() -> MetricsService:
    return MetricsService()


def get_repo() -> TransactionsRepository:
    return TransactionsRepository()


@router.get(
    "/metrics/dashboard",
    operation_id="getDashboardMetrics",
    summary="Métricas agregadas del dashboard",
    response_model=DashboardMetrics,
    responses={401: ERROR_401},
)
async def dashboard_metrics(
    response: Response,
    service: Annotated[MetricsService, Depends(get_metrics_service)],
) -> DashboardMetrics:
    metrics, cache_hit = await service.dashboard()
    # Header fuera del contrato (no causa drift): hace observable el cache
    # en la demo — segundo reload dentro del TTL responde HIT.
    response.headers["X-Cache"] = "HIT" if cache_hit else "MISS"
    return metrics


@router.get(
    "/activity",
    operation_id="getMyActivity",
    summary="Acciones del usuario en sesión (sobre la auditoría)",
    response_model=list[AuditEntry],
    responses={401: ERROR_401, 403: {"model": Error}, 422: {"model": Error}},
)
async def my_activity(
    user: Annotated[AuthContext, Depends(current_user)],
    repo: Annotated[TransactionsRepository, Depends(get_repo)],
    actor: Annotated[str | None, Query()] = None,
    action: Annotated[TransitionAction | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[AuditEntry]:
    # Mirar a otro actor es privilegio del auditor; el resto ve siempre lo suyo.
    if actor is not None and actor != user.user_id and "auditor" not in user.roles:
        raise ApiError(
            403, "FORBIDDEN_ROLE", "Solo un auditor puede ver la actividad de otros."
        )
    entries = await repo.audit_by_actor(
        actor=actor or user.user_id,
        action=action.value if action else None,
        limit=limit,
    )
    return [AuditEntry.model_validate(e) for e in entries]
