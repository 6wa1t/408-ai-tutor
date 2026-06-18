"""Application configuration using Pydantic Settings."""

from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


# Project root: 408-ai-tutor/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Global application settings.

    All config values can be overridden via environment variables
    or a .env file in the project root.
    """

    # --- Application ---
    app_name: str = "408考研AI专属助教"
    app_version: str = "0.1.0"
    debug: bool = False

    # --- Database ---
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'data' / 'questions.db'}"

    # --- Logging ---
    log_level: str = "INFO"
    log_file: str = str(PROJECT_ROOT / "logs" / "app.log")

    # --- Paths ---
    pdf_dir: str = str(PROJECT_ROOT / "data")
    image_dir: str = str(PROJECT_ROOT / "images")

    # --- LLM (Phase 4) ---
    llm_api_base: str = ""
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
    )


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
