"""Claves RS256 efímeras + base de test, antes de que se importe la app."""

import os

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

os.environ.setdefault("AUTH_JWT_PRIVATE_KEY", PRIVATE_PEM)
os.environ.setdefault("AUTH_JWT_PUBLIC_KEY", PUBLIC_PEM)
os.environ.setdefault("AUTH_MONGO_DB", "auth_db_test")
