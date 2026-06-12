from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TXN_", env_file=".env", extra="ignore")

    mongo_uri: str = "mongodb://localhost:27017/?replicaSet=rs0&directConnection=true"
    mongo_db: str = "transactions_db"
    service_name: str = "transactions"
    # Fase 2 activa la verificación JWT; en Fase 0 el esquema se declara
    # en el contrato pero no se exige, para que la rebanada vertical corra sin auth.
    auth_enforced: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
