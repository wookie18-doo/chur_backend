import enum
import os
from functools import lru_cache
from pathlib import Path
from tempfile import gettempdir

from pydantic_settings import BaseSettings, SettingsConfigDict
from yarl import URL

TEMP_DIR = Path(gettempdir())


class LogLevel(enum.StrEnum):
    """Possible log levels."""

    NOTSET = "NOTSET"
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    FATAL = "FATAL"


class AppSettings(BaseSettings):
    """Core application settings: environment and logging."""

    # Current environment
    environment: str = "dev"

    log_level: LogLevel = LogLevel.INFO


class UsersSettings(BaseSettings):
    """Settings for the users/auth subsystem."""

    users_secret: str = os.getenv("USERS_SECRET", "")
    users_access_token_lifetime_seconds: int = 60 * 60 * 24 * 7
    users_reset_password_token_lifetime_seconds: int = 60 * 60
    users_verification_token_lifetime_seconds: int = 60 * 60 * 24
    users_otp_lifetime_seconds: int = 60 * 5
    users_cookie_name: str = "finance_manager_session"


class DatabaseSettings(BaseSettings):
    """Variables for the database."""

    db_host: str = "localhost"
    db_port: int = 5432
    db_user: str = "finance_manager"
    db_pass: str = "finance_manager"  # noqa: S105
    db_base: str = "finance_manager"
    db_echo: bool = False

    @property
    def db_url(self) -> URL:
        """
        Assemble database URL from settings.

        :return: database URL.
        """
        return URL.build(
            scheme="postgresql+asyncpg",
            host=self.db_host,
            port=self.db_port,
            user=self.db_user,
            password=self.db_pass,
            path=f"/{self.db_base}",
        )


class RedisSettings(BaseSettings):
    """Variables for Redis."""

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_user: str | None = None
    redis_pass: str | None = None
    redis_base: int | None = None

    @property
    def redis_url(self) -> URL:
        """
        Assemble REDIS URL from settings.

        :return: redis URL.
        """
        path = ""
        if self.redis_base is not None:
            path = f"/{self.redis_base}"
        return URL.build(
            scheme="redis",
            host=self.redis_host,
            port=self.redis_port,
            user=self.redis_user,
            password=self.redis_pass,
            path=path,
        )


class Settings(
    AppSettings,
    UsersSettings,
    DatabaseSettings,
    RedisSettings,
):
    """
    Application settings.

    Assembled from the feature-specific settings groups above; each group
    can be configured independently with environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="FINANCE_MANAGER_",
        env_file_encoding="utf-8",
    )


@lru_cache
def get_settings() -> Settings:
    """
    Build and cache the settings instance.

    :return: cached settings instance.
    """
    return Settings()


settings = get_settings()
