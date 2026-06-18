"""Unified logging configuration."""

import logging
import sys
from pathlib import Path

from app.config import get_settings


_configured = False


def setup_logging() -> logging.Logger:
    """Configure application-wide logging.

    Outputs to both console (stdout) and a rotating log file.
    Safe to call multiple times — only configures once.
    """
    global _configured
    if _configured:
        return logging.getLogger("app")

    settings = get_settings()

    # Ensure log directory exists
    log_path = Path(settings.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("app")
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler.setFormatter(console_fmt)

    # File handler
    file_handler = logging.FileHandler(
        settings.log_file, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    _configured = True
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a named child logger under the app logger."""
    setup_logging()
    return logging.getLogger(f"app.{name}")
