"""Tests unitarios de emisión/validación de JWT (repo mockeado, sin Mongo)."""

from unittest.mock import AsyncMock

import jwt
import pytest

from app.services.token_service import InvalidTokenError, TokenService, decode_token

USER = {"_id": "usr_01", "username": "operador1", "roles": ["operador"]}


async def _pair() -> dict:
    service = TokenService(repo=AsyncMock())
    return await service.issue_pair(USER)


async def test_access_token_valido_y_con_claims():
    pair = await _pair()
    claims = decode_token(pair["accessToken"], expected_typ="access")
    assert claims["sub"] == "usr_01"
    assert claims["roles"] == ["operador"]
    assert pair["tokenType"] == "Bearer"
    assert pair["expiresIn"] == 900


async def test_refresh_no_sirve_como_access():
    pair = await _pair()
    with pytest.raises(InvalidTokenError):
        decode_token(pair["refreshToken"], expected_typ="access")


async def test_token_adulterado_rechazado():
    pair = await _pair()
    adulterado = pair["accessToken"][:-8] + "AAAAAAAA"
    with pytest.raises(InvalidTokenError):
        decode_token(adulterado, expected_typ="access")


async def test_token_firmado_con_otra_clave_rechazado():
    """El corazón de RS256: un token firmado por cualquier otro emisor no pasa.

    (El ataque de confusión HS256-con-clave-pública lo bloquea PyJWT en el
    encode mismo; aquí se prueba el caso de un emisor con SU PROPIA clave RSA.)
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    otra_clave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    otra_pem = otra_clave.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    otro = jwt.encode(
        {"sub": "usr_01", "typ": "access", "iss": "auth"},
        otra_pem,
        algorithm="RS256",
    )
    with pytest.raises(InvalidTokenError):
        decode_token(otro, expected_typ="access")
