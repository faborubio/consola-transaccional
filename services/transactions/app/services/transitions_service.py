"""Orquestación de una transición de estado — el corazón transaccional.

Orden de los controles (cada uno con su error del contrato):
1. Motivo obligatorio para RECHAZAR/REVERTIR        → 422 VALIDATION_ERROR
2. Idempotencia (SET NX atómico)                    → repetido: resultado guardado
                                                      en curso/payload distinto: 409
3. Existencia                                       → 404 NOT_FOUND
4. Maker-checker (segregación de funciones)         → 403 SEGREGATION_OF_DUTIES
5. Máquina de estados                               → 409 INVALID_TRANSITION
6. Update con versión + auditoría (tx Mongo)        → carrera: 409 STALE_VERSION

Si cualquier control falla, la clave de idempotencia se LIBERA: el reintento
con la misma clave es legítimo (el intento no ejecutó).
"""

import secrets
from datetime import UTC, datetime

from app.domain.models import Transaction, TransitionAction
from app.domain.state_machine import REQUIRES_REASON, next_status
from app.observability import correlation_id
from app.repository.transactions_repo import StaleVersionError, TransactionsRepository
from app.services.idempotency import (
    AlreadyProcessingError,
    IdempotencyStore,
    IdempotencyUnavailableError,
    PayloadMismatchError,
    payload_hash,
)


class TransitionError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


class TransitionsService:
    def __init__(
        self,
        repo: TransactionsRepository | None = None,
        idempotency: IdempotencyStore | None = None,
    ) -> None:
        self.repo = repo or TransactionsRepository()
        self.idempotency = idempotency or IdempotencyStore()

    async def execute(
        self,
        *,
        txn_id: str,
        action: TransitionAction,
        expected_version: int,
        reason: str | None,
        actor_id: str,
        idempotency_key: str,
    ) -> Transaction:
        if action in REQUIRES_REASON and not (reason and reason.strip()):
            raise TransitionError(
                422, "VALIDATION_ERROR", f"La acción {action} exige un motivo."
            )

        request_hash = payload_hash(
            {"txn": txn_id, "action": action, "version": expected_version, "reason": reason}
        )
        try:
            stored = await self.idempotency.claim(idempotency_key, request_hash)
        except AlreadyProcessingError:
            raise TransitionError(
                409, "IDEMPOTENCY_CONFLICT", "La misma operación está en curso."
            ) from None
        except PayloadMismatchError:
            raise TransitionError(
                409,
                "IDEMPOTENCY_CONFLICT",
                "La clave de idempotencia ya fue usada con otro payload.",
            ) from None
        except IdempotencyUnavailableError:
            # Fail-closed: sin garantía de idempotencia no se muta el estado.
            raise TransitionError(
                503,
                "SERVICE_UNAVAILABLE",
                "Servicio temporalmente no disponible; reintente en unos segundos.",
            ) from None
        if stored is not None:
            # Reintento legítimo: se devuelve el resultado original sin re-ejecutar.
            return Transaction.model_validate(stored)

        try:
            result = await self._execute_claimed(
                txn_id=txn_id,
                action=action,
                expected_version=expected_version,
                reason=reason,
                actor_id=actor_id,
            )
        except Exception:
            await self.idempotency.release(idempotency_key)
            raise

        await self.idempotency.store(
            idempotency_key, request_hash, result.model_dump(mode="json")
        )
        return result

    async def _execute_claimed(
        self,
        *,
        txn_id: str,
        action: TransitionAction,
        expected_version: int,
        reason: str | None,
        actor_id: str,
    ) -> Transaction:
        doc = await self.repo.find_by_id(txn_id)
        if doc is None:
            raise TransitionError(404, "NOT_FOUND", "Transacción no encontrada.")

        # Maker-checker: quien inició no puede aprobar lo suyo. Control clásico
        # de banca; se valida contra el actor del TOKEN, no contra el payload.
        if action == TransitionAction.APROBAR and doc["createdBy"] == actor_id:
            raise TransitionError(
                403,
                "SEGREGATION_OF_DUTIES",
                "El iniciador no puede aprobar su propia transacción.",
            )

        current = doc["status"]
        target = next_status(current, action)
        if target is None:
            raise TransitionError(
                409, "INVALID_TRANSITION", f"No se puede {action} desde {current}."
            )

        now = datetime.now(UTC)
        try:
            updated = await self.repo.apply_transition(
                txn_id=txn_id,
                expected_version=expected_version,
                update_fields={
                    "status": target.value,
                    "reviewedBy": actor_id,
                    "updatedAt": now,
                },
                audit_doc={
                    "_id": f"aud_{secrets.token_hex(8)}",
                    "transactionId": txn_id,
                    "action": action.value,
                    "fromStatus": current,
                    "toStatus": target.value,
                    "actor": actor_id,
                    "reason": reason,
                    "at": now,
                    # Trazabilidad forense: enlaza la entrada con los logs del
                    # request (mismo id que viajó del click al servidor). No se
                    # expone en el contrato; el response model lo filtra.
                    "correlationId": correlation_id.get(),
                },
            )
        except StaleVersionError:
            raise TransitionError(
                409,
                "STALE_VERSION",
                "La transacción fue modificada por otro usuario; recargue e intente de nuevo.",
            ) from None
        return Transaction.model_validate(updated)
