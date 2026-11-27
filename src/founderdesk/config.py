"""All settings come from environment variables (or a local .env file)."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from founderdesk.db.url import to_asyncpg_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "founderdesk"
    # No defaults on purpose: if these are missing, the app refuses to start (fail fast).
    app_env: Literal["local", "ci", "production"]
    database_url: str
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    data_file: Path = Path("data/sample_records.json")
    db_pool_size: int = 5
    db_max_overflow: int = 5
    # The commit this image was built from. CI sets it (Dockerfile ARG GIT_SHA); locally "dev".
    git_sha: str = "dev"

    # LLM provider keys. Default empty: tests and CI run without any key.
    gemini_api_key: str = ""
    groq_api_key: str = ""

    # Provider model names and base URLs — settings, not code.
    # Accept both snake_case and UPPER_CASE env names (e.g. LLM_PRIMARY_MODEL).
    llm_primary_model: str = Field("gemini-3.8-flash", validation_alias="LLM_PRIMARY_MODEL")
    llm_primary_base_url: str = Field(
        "https://generativelanguage.googleapis.com/v1beta/openai",
        validation_alias="LLM_PRIMARY_BASE_URL",
    )
    llm_fallback_model: str = Field("openai/gpt-oss-20b", validation_alias="LLM_FALLBACK_MODEL")
    llm_fallback_base_url: str = Field(
        "https://api.groq.com/openai/v1",
        validation_alias="LLM_FALLBACK_BASE_URL",
    )
    llm_request_timeout: float = 30.0

    # INR per USD for rupee cost display. Rs 95 on 22 Nov 2026.
    usd_inr: float = 95.0

    # Ingestion backpressure: two documents at a time, twelve model calls a minute.
    ingest_concurrency: int = 2
    ingest_rpm: int = 12

    # Job lock: a job silent for 60 seconds is offered again.
    ingest_job_timeout: int = 60

    # The worker runs inside the API on Render (free plan has no worker service).
    # Stays false on your laptop.
    worker_in_api: bool = False

    # Admin token: required for POST /v1/ingest. Make a long random one.
    admin_token: str = ""

    # Redis: the job queue. On the laptop it's localhost:6379; on Render it's the
    # internal URL of the Key Value service.
    redis_url: str = "redis://localhost:6379"

    @field_validator("database_url")
    @classmethod
    def _asyncpg(cls, value: str) -> str:
        return to_asyncpg_url(value)


@lru_cache
def get_settings() -> Settings:
    """Build the settings once and reuse them."""
    return Settings()
