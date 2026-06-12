"""Acceso a Mongo del servicio auth: usuarios y registros de refresh tokens.

Base `auth_db`, separada de transactions (sin monolito distribuido).
"""

from datetime import datetime
from typing import Any

from pymongo import AsyncMongoClient

from app.config import get_settings

USERS = "users"
REFRESH_TOKENS = "refresh_tokens"

_client: AsyncMongoClient | None = None


def get_db():
    global _client
    settings = get_settings()
    if _client is None:
        _client = AsyncMongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)
    return _client[settings.mongo_db]


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.close()
        _client = None


class UsersRepository:
    def __init__(self) -> None:
        db = get_db()
        self.users = db[USERS]
        self.refresh_tokens = db[REFRESH_TOKENS]

    async def find_by_username(self, username: str) -> dict | None:
        return await self.users.find_one({"username": username})

    async def find_by_id(self, user_id: str) -> dict | None:
        return await self.users.find_one({"_id": user_id})

    async def insert_user(self, doc: dict[str, Any]) -> None:
        await self.users.insert_one(doc)

    async def count_users(self) -> int:
        return await self.users.estimated_document_count()

    # --- refresh tokens (rotación con detección de reuso) ---

    async def insert_refresh(self, doc: dict[str, Any]) -> None:
        await self.refresh_tokens.insert_one(doc)

    async def find_refresh(self, jti: str) -> dict | None:
        return await self.refresh_tokens.find_one({"_id": jti})

    async def claim_refresh(self, jti: str, replaced_by: str) -> dict | None:
        """Revoca el token atómicamente. None = ya estaba revocado (o no existe):
        dos rotaciones concurrentes del mismo token no pueden ganar ambas."""
        return await self.refresh_tokens.find_one_and_update(
            {"_id": jti, "revoked": False},
            {"$set": {"revoked": True, "replacedBy": replaced_by, "revokedAt": datetime.now()}},
        )

    async def revoke_family(self, family_id: str) -> int:
        result = await self.refresh_tokens.update_many(
            {"familyId": family_id, "revoked": False},
            {"$set": {"revoked": True, "revokedReason": "REUSE_DETECTED"}},
        )
        return result.modified_count

    async def ensure_indexes(self) -> None:
        await self.users.create_index("username", unique=True)
        await self.refresh_tokens.create_index("familyId")
        # TTL: Mongo purga los registros vencidos solo
        await self.refresh_tokens.create_index("expiresAt", expireAfterSeconds=0)
