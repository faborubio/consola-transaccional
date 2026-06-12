"""Verificación JWT (clave pública RS256) y RBAC como dependencies reutilizables.

La autorización del cliente (ocultar botones) es UX; esta es la seguridad real:
ningún endpoint protegido responde sin un token firmado por `auth`, y los roles
se exigen con `require_role(...)` — no con ifs regados por los routers.
"""

from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.errors import ApiError
from app.config import get_settings

ALGORITHM = "RS256"
ISSUER = "auth"

_bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user_id: str
    username: str
    roles: tuple[str, ...]


async def current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AuthContext:
    if credentials is None:
        raise ApiError(401, "UNAUTHORIZED", "Token ausente.")
    try:
        claims = jwt.decode(
            credentials.credentials,
            get_settings().public_key_pem(),
            algorithms=[ALGORITHM],
            issuer=ISSUER,
        )
    except jwt.PyJWTError as exc:
        raise ApiError(401, "UNAUTHORIZED", "Token inválido o expirado.") from exc
    if claims.get("typ") != "access":
        raise ApiError(401, "UNAUTHORIZED", "Tipo de token incorrecto.")
    return AuthContext(
        user_id=claims["sub"],
        username=claims.get("username", ""),
        roles=tuple(claims.get("roles", ())),
    )


def require_role(role: str):
    async def dependency(user: Annotated[AuthContext, Depends(current_user)]) -> AuthContext:
        if role not in user.roles:
            raise ApiError(403, "FORBIDDEN_ROLE", f"Se requiere rol {role}.")
        return user

    return dependency
