"""Modelos alineados 1:1 con contracts/openapi.yaml (ver nota en transactions)."""

from enum import StrEnum

from pydantic import BaseModel, Field


class Role(StrEnum):
    OPERADOR = "operador"
    SUPERVISOR = "supervisor"
    AUDITOR = "auditor"


class LoginRequest(BaseModel):
    username: str
    password: str = Field(min_length=8, json_schema_extra={"format": "password"})


class RefreshRequest(BaseModel):
    refreshToken: str


class TokenPair(BaseModel):
    accessToken: str
    refreshToken: str
    tokenType: str
    expiresIn: int


class User(BaseModel):
    id: str
    username: str
    fullName: str | None = None
    roles: list[Role]


class ErrorDetail(BaseModel):
    field: str | None = None
    issue: str | None = None


class Error(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] | None = None
