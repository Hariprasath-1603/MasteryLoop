from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Platform-wide centralized configuration schema."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    ENVIRONMENT: Literal["development", "testing", "staging", "production"] = (
        "development"
    )
    LOG_LEVEL: str = "INFO"

    # PostgreSQL Configuration
    POSTGRES_USER: str = Field(default="masteryloop")
    POSTGRES_PASSWORD: str = Field(default="masteryloop_secret")
    POSTGRES_HOST: str = Field(default="localhost")
    POSTGRES_PORT: int = Field(default=5432)
    POSTGRES_DB: str = Field(default="masteryloop")

    DATABASE_URL_ASYNC: str | None = None
    DATABASE_URL_SYNC: str | None = None

    # Redis Configuration
    REDIS_HOST: str = Field(default="localhost")
    REDIS_PORT: int = Field(default=6379)
    REDIS_DB: int = Field(default=0)
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # Qdrant Vector Search
    QDRANT_HOST: str = Field(default="localhost")
    QDRANT_PORT: int = Field(default=6333)
    QDRANT_URL: str = Field(default="http://localhost:6333")

    # MLflow Tracking Server
    MLFLOW_PORT: int = Field(default=5000)
    MLFLOW_TRACKING_URI: str = Field(default="http://localhost:5000")

    # Security
    JWT_SECRET_KEY: str = Field(
        default="dev_secret_key_change_in_production_min32chars"
    )
    JWT_ALGORITHM: str = Field(default="HS256")
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60)

    @computed_field
    @property
    def async_database_url(self) -> str:
        """Returns the PostgreSQL connection string using asyncpg driver."""
        if self.DATABASE_URL_ASYNC:
            return self.DATABASE_URL_ASYNC
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @computed_field
    @property
    def sync_database_url(self) -> str:
        """Returns the PostgreSQL connection string using psycopg3 driver."""
        if self.DATABASE_URL_SYNC:
            return self.DATABASE_URL_SYNC
        return (
            f"postgresql+psycopg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retrieve singleton instance of cached application settings."""
    return Settings()
