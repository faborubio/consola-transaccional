"""Modelos de dominio alineados 1:1 con contracts/openapi.yaml.

Los nombres de clase definen los nombres de schema que FastAPI publica en su
OpenAPI; deben coincidir con los del contrato para que el candado anti-drift
(oasdiff en CI) pase. No renombrar sin actualizar el contrato.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TransactionStatus(StrEnum):
    PENDIENTE = "PENDIENTE"
    EN_REVISION = "EN_REVISION"
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"
    REVERTIDA = "REVERTIDA"


class TransactionType(StrEnum):
    TRANSFERENCIA = "TRANSFERENCIA"
    PAGO = "PAGO"
    ABONO = "ABONO"
    REVERSA = "REVERSA"


class TransitionAction(StrEnum):
    APROBAR = "APROBAR"
    RECHAZAR = "RECHAZAR"
    ENVIAR_A_REVISION = "ENVIAR_A_REVISION"
    REVERTIR = "REVERTIR"


class Party(BaseModel):
    accountId: str
    name: str


class Transaction(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(validation_alias="_id")
    amount: float
    currency: str = Field(min_length=3, max_length=3)
    type: TransactionType
    status: TransactionStatus
    version: int
    source: Party
    destination: Party
    reference: str | None = None
    createdBy: str
    reviewedBy: str | None = None
    createdAt: datetime
    updatedAt: datetime | None = None
    metadata: dict[str, Any] | None = None


class PageInfo(BaseModel):
    hasNextPage: bool
    nextCursor: str | None = None
    totalEstimate: int | None = None


class TransactionPage(BaseModel):
    items: list[Transaction]
    pageInfo: PageInfo


class AuditEntry(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str = Field(validation_alias="_id")
    transactionId: str
    action: TransitionAction
    fromStatus: TransactionStatus
    toStatus: TransactionStatus
    actor: str
    reason: str | None = None
    at: datetime


class ErrorDetail(BaseModel):
    field: str | None = None
    issue: str | None = None


class Error(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] | None = None
