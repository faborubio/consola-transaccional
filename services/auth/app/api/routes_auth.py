from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.errors import ApiError
from app.domain.models import Error, LoginRequest, RefreshRequest, TokenPair, User
from app.repository.users_repo import UsersRepository
from app.services.passwords import verify_password
from app.services.token_service import (
    InvalidTokenError,
    ReuseDetectedError,
    TokenService,
    decode_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])

ERROR_401 = {"model": Error, "description": "Token ausente, inválido o expirado."}
ERROR_429 = {
    "model": Error,
    "description": "Demasiadas solicitudes.",
    "headers": {
        "Retry-After": {
            "schema": {"type": "integer"},
            "description": "Segundos hasta el próximo intento permitido.",
        }
    },
}

_bearer = HTTPBearer(auto_error=False)


def get_repo() -> UsersRepository:
    return UsersRepository()


def get_token_service() -> TokenService:
    return TokenService()


@router.post(
    "/login",
    operation_id="login",
    summary="Iniciar sesión y obtener tokens",
    response_model=TokenPair,
    responses={401: ERROR_401, 422: {"model": Error}, 429: ERROR_429},
)
async def login(
    body: LoginRequest,
    repo: Annotated[UsersRepository, Depends(get_repo)],
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> TokenPair:
    user = await repo.find_by_username(body.username)
    # Mismo error para usuario inexistente y contraseña mala: no se revela cuál.
    if user is None or not verify_password(user["passwordHash"], body.password):
        raise ApiError(401, "UNAUTHORIZED", "Credenciales inválidas.")
    return TokenPair(**await tokens.issue_pair(user))


@router.post(
    "/refresh",
    operation_id="refreshToken",
    summary="Renovar el access token con un refresh token",
    response_model=TokenPair,
    responses={401: ERROR_401, 422: {"model": Error}},
)
async def refresh(
    body: RefreshRequest,
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> TokenPair:
    try:
        return TokenPair(**await tokens.rotate(body.refreshToken))
    except ReuseDetectedError as exc:
        raise ApiError(401, "UNAUTHORIZED", str(exc)) from exc
    except InvalidTokenError as exc:
        raise ApiError(401, "UNAUTHORIZED", str(exc)) from exc


@router.post(
    "/logout",
    operation_id="logout",
    summary="Cerrar sesión y revocar la familia de refresh tokens",
    status_code=204,
    responses={422: {"model": Error}},
)
async def logout(
    body: RefreshRequest,
    tokens: Annotated[TokenService, Depends(get_token_service)],
) -> None:
    await tokens.revoke_session(body.refreshToken)


@router.get(
    "/me",
    operation_id="getCurrentUser",
    summary="Perfil del usuario autenticado",
    response_model=User,
    responses={401: ERROR_401},
)
async def me(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    repo: Annotated[UsersRepository, Depends(get_repo)],
) -> User:
    if credentials is None:
        raise ApiError(401, "UNAUTHORIZED", "Token ausente.")
    try:
        claims = decode_token(credentials.credentials, expected_typ="access")
    except InvalidTokenError as exc:
        raise ApiError(401, "UNAUTHORIZED", str(exc)) from exc
    user = await repo.find_by_id(claims["sub"])
    if user is None:
        raise ApiError(401, "UNAUTHORIZED", "Usuario inexistente.")
    return User(
        id=user["_id"],
        username=user["username"],
        fullName=user.get("fullName"),
        roles=user["roles"],
    )
