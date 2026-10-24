from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process settings. Secrets come from the environment, never from the repo."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    database_url: str = "postgresql+psycopg://vora:vora@localhost:5432/vora"
    app_database_url: str = "postgresql+psycopg://vora_app:vora@localhost:5432/vora"
    admin_database_url: str = "postgresql+psycopg://vora_admin:vora@localhost:5432/vora"
    redis_url: str = "redis://localhost:6379/0"
    cors_origins: str = "http://localhost:3000"
    jwt_secret: str = "local-dev-jwt-secret-not-for-production"
    internal_auth_secret: str = ""
    livekit_url: str = ""
    livekit_api_key: str = ""
    livekit_api_secret: str = ""
    access_ttl_minutes: int = 15
    refresh_ttl_days: int = 14

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
