from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AUTH_", env_file=".env", extra="ignore")

    mongo_uri: str = "mongodb://localhost:27017/?replicaSet=rs0&directConnection=true"
    # Base separada de transactions: tres servicios sobre una misma base
    # es un monolito distribuido (ver plan, Fase 6).
    mongo_db: str = "auth_db"
    service_name: str = "auth"

    # Claves RS256: PEM inline (tests) o ruta a archivo (compose monta infra/keys).
    # Solo este servicio conoce la privada — nadie más puede emitir tokens.
    jwt_private_key: str | None = None
    jwt_private_key_file: str | None = None
    jwt_public_key: str | None = None
    jwt_public_key_file: str | None = None

    access_ttl_seconds: int = 900
    refresh_ttl_seconds: int = 7 * 24 * 3600

    # Usuarios demo al primer arranque (portafolio); en producción sería un alta real.
    bootstrap_demo_users: bool = True
    demo_password: str = "Demo1234!"

    def private_key_pem(self) -> str:
        if self.jwt_private_key:
            return self.jwt_private_key
        if self.jwt_private_key_file:
            return Path(self.jwt_private_key_file).read_text()
        raise RuntimeError("Falta AUTH_JWT_PRIVATE_KEY(_FILE)")

    def public_key_pem(self) -> str:
        if self.jwt_public_key:
            return self.jwt_public_key
        if self.jwt_public_key_file:
            return Path(self.jwt_public_key_file).read_text()
        raise RuntimeError("Falta AUTH_JWT_PUBLIC_KEY(_FILE)")


@lru_cache
def get_settings() -> Settings:
    return Settings()
