"""Settings read from the environment (and a .env file in development)."""

import os
from dataclasses import dataclass

from dotenv import find_dotenv, load_dotenv

_DEV_SECRET = "dev-secret-key-change-me"


@dataclass(frozen=True)
class Settings:
    env: str
    database_url: str
    secret_key: str
    session_cookie_secure: bool
    session_max_age_seconds: int
    max_body_bytes: int
    # SLIM's reference tables. Defaults to DATABASE_URL: one Postgres shared with the ecosystem.
    slim_database_url: str | None = None
    reference_cache_ttl_seconds: int = 300

    @property
    def is_production(self) -> bool:
        return self.env == "production"


def _bool(value: str | None, default: bool) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _database_url(raw: str) -> str:
    # Render and Heroku hand out postgres:// URLs; SQLAlchemy 2 only accepts postgresql://.
    if raw.startswith("postgres://"):
        return "postgresql+psycopg2://" + raw.removeprefix("postgres://")
    return raw


def load_settings() -> Settings:
    load_dotenv(find_dotenv(usecwd=True))
    env = os.environ.get("APP_ENV", "development").strip().lower()
    secret_key = os.environ.get("SECRET_KEY", "")
    if not secret_key:
        if env == "production":
            raise RuntimeError("SECRET_KEY must be set when APP_ENV=production")
        secret_key = _DEV_SECRET
    return Settings(
        env=env,
        database_url=_database_url(os.environ.get("DATABASE_URL", "sqlite:///slim_lab_portal.db")),
        secret_key=secret_key,
        session_cookie_secure=_bool(os.environ.get("SESSION_COOKIE_SECURE"), env == "production"),
        session_max_age_seconds=int(os.environ.get("SESSION_MAX_AGE_SECONDS", 8 * 60 * 60)),
        max_body_bytes=int(os.environ.get("MAX_BODY_BYTES", 1024 * 1024)),
        slim_database_url=_database_url(os.environ["SLIM_DATABASE_URL"]) if os.environ.get("SLIM_DATABASE_URL") else None,
        reference_cache_ttl_seconds=int(os.environ.get("REFERENCE_CACHE_TTL_SECONDS", 300)),
    )
