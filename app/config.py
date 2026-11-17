"""Configuración de la aplicación, cargada desde variables de entorno o .env."""

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "ObraTrack API"
    environment: str = "development"
    debug: bool = False

    # Conexión a MySQL
    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "obratrack"
    db_password: str = "obratrack_dev"
    db_name: str = "obratrack"
    # Si se define, tiene prioridad sobre los campos DB_*.
    database_url: str | None = None

    # Autenticación
    jwt_secret: str = "dev-secret-cambia-esto"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    allow_registration: bool = True

    # CORS: "*" o lista separada por comas
    cors_origins: str = "*"

    # Validaciones de telemetría
    telemetry_reject_null_island: bool = True

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return (
            f"mysql+pymysql://{quote_plus(self.db_user)}:{quote_plus(self.db_password)}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )

    @property
    def is_sqlite(self) -> bool:
        return self.sqlalchemy_url.startswith("sqlite")

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
