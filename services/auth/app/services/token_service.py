"""Emisión y rotación de JWT RS256.

- Solo este servicio firma (clave privada); el resto verifica con la pública.
- Rotación de refresh: cada uso emite uno nuevo y revoca el anterior de forma
  ATÓMICA (find_one_and_update). Si llega un refresh ya revocado, es señal de
  robo: se invalida la familia completa de esa sesión.
"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.config import get_settings
from app.repository.users_repo import UsersRepository

ALGORITHM = "RS256"
ISSUER = "auth"


class InvalidTokenError(Exception):
    pass


class ReuseDetectedError(Exception):
    pass


def _encode(claims: dict) -> str:
    return jwt.encode(claims, get_settings().private_key_pem(), algorithm=ALGORITHM)


def decode_token(token: str, expected_typ: str) -> dict:
    try:
        claims = jwt.decode(
            token,
            get_settings().public_key_pem(),
            algorithms=[ALGORITHM],
            issuer=ISSUER,
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError("Token inválido o expirado.") from exc
    if claims.get("typ") != expected_typ:
        raise InvalidTokenError("Tipo de token incorrecto.")
    return claims


class TokenService:
    def __init__(self, repo: UsersRepository | None = None) -> None:
        self.repo = repo or UsersRepository()
        self.settings = get_settings()

    async def issue_pair(self, user: dict, family_id: str | None = None) -> dict:
        now = datetime.now(UTC)
        family_id = family_id or str(uuid.uuid4())
        jti = str(uuid.uuid4())

        access = _encode(
            {
                "sub": user["_id"],
                "username": user["username"],
                "roles": user["roles"],
                "typ": "access",
                "iss": ISSUER,
                "iat": now,
                "exp": now + timedelta(seconds=self.settings.access_ttl_seconds),
            }
        )
        refresh_exp = now + timedelta(seconds=self.settings.refresh_ttl_seconds)
        refresh = _encode(
            {
                "sub": user["_id"],
                "jti": jti,
                "fam": family_id,
                "typ": "refresh",
                "iss": ISSUER,
                "iat": now,
                "exp": refresh_exp,
            }
        )
        await self.repo.insert_refresh(
            {
                "_id": jti,
                "familyId": family_id,
                "userId": user["_id"],
                "expiresAt": refresh_exp,
                "revoked": False,
                "replacedBy": None,
            }
        )
        return {
            "accessToken": access,
            "refreshToken": refresh,
            "tokenType": "Bearer",
            "expiresIn": self.settings.access_ttl_seconds,
        }

    async def rotate(self, refresh_token: str) -> dict:
        claims = decode_token(refresh_token, expected_typ="refresh")
        jti, family_id = claims["jti"], claims["fam"]

        new_jti_placeholder = str(uuid.uuid4())
        claimed = await self.repo.claim_refresh(jti, replaced_by=new_jti_placeholder)
        if claimed is None:
            record = await self.repo.find_refresh(jti)
            if record is not None and record.get("revoked"):
                # Refresh ya usado presentado de nuevo → posible robo:
                # se quema la familia entera de la sesión.
                await self.repo.revoke_family(family_id)
                raise ReuseDetectedError("Refresh token reutilizado; sesión invalidada.")
            raise InvalidTokenError("Refresh token desconocido o expirado.")

        user = await self.repo.find_by_id(claims["sub"])
        if user is None:
            raise InvalidTokenError("Usuario inexistente.")
        return await self.issue_pair(user, family_id=family_id)
