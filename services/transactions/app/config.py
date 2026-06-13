from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TXN_", env_file=".env", extra="ignore")

    mongo_uri: str = "mongodb://localhost:27017/?replicaSet=rs0&directConnection=true"
    mongo_db: str = "transactions_db"
    service_name: str = "transactions"

    # Cota dura por query (maxTimeMS): una consulta demasiado amplia falla
    # rápido (503 QUERY_TIMEOUT) en vez de acumularse en Mongo — el frontend
    # cancela su request pero el servidor seguiría ejecutando la query.
    query_timeout_ms: int = 10_000

    # Clave PÚBLICA RS256: este servicio solo verifica tokens; jamás los emite.
    # PEM inline (tests) o ruta a archivo (compose monta infra/keys/jwt-public.pem).
    jwt_public_key: str | None = None
    jwt_public_key_file: str | None = None

    def public_key_pem(self) -> str:
        if self.jwt_public_key:
            return self.jwt_public_key
        if self.jwt_public_key_file:
            return Path(self.jwt_public_key_file).read_text()
        raise RuntimeError("Falta TXN_JWT_PUBLIC_KEY(_FILE)")


@lru_cache
def get_settings() -> Settings:
    return Settings()
