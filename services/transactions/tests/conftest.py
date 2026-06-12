"""Clave pública RS256 efímera en el entorno antes de importar la app,
y helper para emitir tokens de prueba con la privada correspondiente."""

import os
from datetime import UTC, datetime, timedelta

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

PRIVATE_PEM = _key.private_bytes(
    serialization.Encoding.PEM,
    serialization.PrivateFormat.PKCS8,
    serialization.NoEncryption(),
).decode()

PUBLIC_PEM = (
    _key.public_key()
    .public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    .decode()
)

os.environ.setdefault("TXN_JWT_PUBLIC_KEY", PUBLIC_PEM)


def make_token(
    roles: list[str] | None = None,
    *,
    user_id: str = "usr_01",
    username: str = "operador1",
    typ: str = "access",
    expired: bool = False,
) -> str:
    now = datetime.now(UTC)
    exp = now - timedelta(minutes=5) if expired else now + timedelta(minutes=15)
    return jwt.encode(
        {
            "sub": user_id,
            "username": username,
            "roles": roles or ["operador"],
            "typ": typ,
            "iss": "auth",
            "iat": now - timedelta(minutes=10) if expired else now,
            "exp": exp,
        },
        PRIVATE_PEM,
        algorithm="RS256",
    )


def auth_headers(roles: list[str] | None = None, **kwargs) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_token(roles, **kwargs)}"}
