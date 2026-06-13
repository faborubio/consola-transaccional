from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query
from pymongo.errors import ExecutionTimeout

from app.api.auth import AuthContext, current_user, require_role
from app.api.errors import ApiError
from app.domain.models import (
    AuditEntry,
    Error,
    Transaction,
    TransactionPage,
    TransactionStatus,
    TransactionType,
    TransitionRequest,
)
from app.services.pagination import InvalidCursorError, InvalidSortError
from app.services.transactions_service import TransactionsService
from app.services.transitions_service import TransitionError, TransitionsService

router = APIRouter(
    prefix="/transactions",
    tags=["transactions"],
    dependencies=[Depends(current_user)],
)

ERROR_401 = {"model": Error, "description": "Token ausente, inválido o expirado."}
ERROR_404 = {"model": Error, "description": "Recurso no encontrado."}

TransactionId = Annotated[str, Path(description="Identificador de la transacción.")]


def get_service() -> TransactionsService:
    return TransactionsService()


def get_transitions_service() -> TransitionsService:
    return TransitionsService()


@router.get(
    "",
    operation_id="listTransactions",
    summary="Listar transacciones (paginación y filtros server-side)",
    response_model=TransactionPage,
    response_model_exclude_none=False,
    responses={401: ERROR_401, 422: {"model": Error}, 503: {"model": Error}},
)
async def list_transactions(
    service: Annotated[TransactionsService, Depends(get_service)],
    cursor: Annotated[str | None, Query(description="Cursor opaco de paginación.")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    status: Annotated[list[TransactionStatus] | None, Query()] = None,
    type: Annotated[TransactionType | None, Query()] = None,  # noqa: A002
    minAmount: Annotated[float | None, Query(ge=0)] = None,  # noqa: N803
    maxAmount: Annotated[float | None, Query(ge=0)] = None,  # noqa: N803
    currency: Annotated[str | None, Query(min_length=3, max_length=3)] = None,
    counterparty: Annotated[str | None, Query(min_length=3)] = None,
    dateFrom: Annotated[datetime | None, Query()] = None,  # noqa: N803
    dateTo: Annotated[datetime | None, Query()] = None,  # noqa: N803
    sort: Annotated[str, Query()] = "-createdAt",
) -> TransactionPage:
    try:
        return await service.list_transactions(
            cursor=cursor,
            limit=limit,
            sort=sort,
            status=[s.value for s in status] if status else None,
            type_=type.value if type else None,
            min_amount=minAmount,
            max_amount=maxAmount,
            currency=currency,
            counterparty=counterparty,
            date_from=dateFrom,
            date_to=dateTo,
        )
    except (InvalidCursorError, InvalidSortError) as exc:
        raise ApiError(422, "VALIDATION_ERROR", str(exc)) from exc
    except ExecutionTimeout as exc:
        raise ApiError(
            503, "QUERY_TIMEOUT", "La consulta tardó demasiado; acote los filtros."
        ) from exc


@router.get(
    "/{id}",
    operation_id="getTransaction",
    summary="Detalle de una transacción",
    response_model=Transaction,
    responses={401: ERROR_401, 404: ERROR_404, 422: {"model": Error}},
)
async def get_transaction(
    id: TransactionId,  # noqa: A002
    service: Annotated[TransactionsService, Depends(get_service)],
) -> Transaction:
    txn = await service.get_transaction(id)
    if txn is None:
        raise ApiError(404, "NOT_FOUND", "Transacción no encontrada.")
    return txn


@router.post(
    "/{id}/transitions",
    operation_id="transitionTransaction",
    summary="Ejecutar una transición de estado (aprobar, rechazar, revisar, revertir)",
    response_model=Transaction,
    responses={
        401: ERROR_401,
        403: {"model": Error},
        404: ERROR_404,
        409: {"model": Error},
        422: {"model": Error},
        503: {"model": Error},
    },
)
async def transition_transaction(
    id: TransactionId,  # noqa: A002
    body: TransitionRequest,
    idempotency_key: Annotated[
        UUID,
        Header(
            alias="Idempotency-Key",
            description="Clave única (UUID) por intento de operación.",
        ),
    ],
    user: Annotated[AuthContext, Depends(require_role("supervisor"))],
    service: Annotated[TransitionsService, Depends(get_transitions_service)],
) -> Transaction:
    try:
        return await service.execute(
            txn_id=id,
            action=body.action,
            expected_version=body.expectedVersion,
            reason=body.reason,
            actor_id=user.user_id,
            idempotency_key=str(idempotency_key),
        )
    except TransitionError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message) from exc


@router.get(
    "/{id}/audit",
    operation_id="getTransactionAudit",
    summary="Historial de auditoría (append-only) de una transacción",
    response_model=list[AuditEntry],
    responses={401: ERROR_401, 404: ERROR_404, 422: {"model": Error}},
)
async def get_transaction_audit(
    id: TransactionId,  # noqa: A002
    service: Annotated[TransactionsService, Depends(get_service)],
) -> list[AuditEntry]:
    entries = await service.get_audit(id)
    if entries is None:
        raise ApiError(404, "NOT_FOUND", "Transacción no encontrada.")
    return [AuditEntry.model_validate(e) for e in entries]
