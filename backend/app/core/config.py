"""
Application settings loaded from environment variables.

Uses pydantic-settings to automatically read from .env files.
Every setting has a default so the app boots without manual configuration.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    All Application configuration in one place.

    Values are loaded from environment variables. If a variable isn't set, the default value here is used. In production, override via .env or container environment variables.
    """

    # ── Database ──
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@db:5432/docrag"

    # ── Redis ──
    REDIS_URL: str = "redis://redis:6379/0"

    # ── JWT Authentication ──
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    JWT_REFRESH_SECRET_KEY: str = "dev-refresh-secret-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ACCESS_COOKIE_NAME: str = "access_token"
    REFRESH_COOKIE_NAME: str = "refresh_token"
    REFRESH_COOKIE_SECURE: bool = False  # Set True in production (requires HTTPS)
    REFRESH_COOKIE_SAMESITE: str = "lax"

    # ── File Storage ──
    STORAGE_PATH: str = "storage/uploads"

    # ── Celery ──
    CELERY_BROKER_URL: str = "redis://redis:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/2"

    # ── Embedding Model ──
    EMBEDDING_MODEL: str = "BAAI/bge-base-en-v1.5"
    EMBEDDING_DIMENSION: int = 768

    # ── LLM Providers ──
    DEFAULT_LLM_PROVIDER: str = "ollama"
    OPENAI_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,    # DATABASE_URL != database_url
        extra="forbid",         # Fail loudly if typo in env vars
    )


def get_settings() -> Settings:
    """
    Factory function for settings.
    
    We use a function (not a global) so tests can override settings by monkeypatching this function.
    """
    return Settings()

    