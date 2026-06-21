"""Application configuration using Pydantic Settings."""

from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


# Project root detection:
# - Local dev: config.py is at backend/app/config.py → 3 levels up = project root
# - Docker:    config.py is at /app/app/config.py     → 2 levels up = /app (= project root)
_config_file = Path(__file__).resolve()
_candidate = _config_file.parent.parent.parent
if (_candidate / "backend").is_dir():
    # Local dev: project_root/backend/app/config.py
    PROJECT_ROOT = _candidate
else:
    # Docker: /app/app/config.py (backend/ was copied flat into WORKDIR /app)
    PROJECT_ROOT = _config_file.parent.parent


class Settings(BaseSettings):
    """Global application settings.

    All config values can be overridden via environment variables
    or a .env file in the project root.
    """

    # --- Application ---
    app_name: str = "408考研AI专属助教"
    app_version: str = "0.2.1"
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

    # --- Vision LLM (VLM fallback, scanned PDF extraction) ---
    # Separate from text LLM because DeepSeek doesn't support vision input.
    # Default: 通义千问VL via Alibaba DashScope (OpenAI-compatible API).
    vision_api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    vision_api_key: str = ""
    vision_model: str = "qwen-vl-max"

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
    )


@lru_cache()
def get_settings() -> Settings:
    """Cached settings singleton."""
    return Settings()
