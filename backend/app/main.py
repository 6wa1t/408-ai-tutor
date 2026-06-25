"""408考研AI专属助教 — FastAPI Application Entry Point.

Run with:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.core.exceptions import AppBaseException
from app.core.logging_config import setup_logging, get_logger
from app.database.schema_sync import sync_agent_knowledge_schema
from app.database.session import create_tables, engine

# Import models to register them with SQLAlchemy metadata
import app.models  # noqa: F401

# Import routers
from app.api.import_routes import router as import_router
from app.api.questions import router as questions_router
from app.api.quiz import router as quiz_router
from app.api.tutor import router as tutor_router
from app.api.misconceptions import router as misconceptions_router
from app.api.wrong_questions import router as wrong_questions_router
from app.api.conversations import router as conversations_router
from app.api.weak_knowledge import router as weak_knowledge_router
from app.api.agent_exports import router as agent_exports_router


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # Startup
    setup_logging()
    logger = get_logger("startup")
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")

    # Always create tables
    create_tables()
    sync_agent_knowledge_schema(engine)
    logger.info("Database tables ensured")

    # Dev-mode migrations
    if settings.debug:
        # Migration: add bookmarks column if missing.
        # Check existing columns via PRAGMA first so we (a) skip the no-op ALTER
        # when the column already exists, and (b) do NOT swallow real DB errors
        # behind a bare `except Exception`.
        from sqlalchemy import text
        with engine.connect() as conn:
            existing_cols = {
                row[1] for row in conn.execute(
                    text("PRAGMA table_info(conversations)")
                )
            }
            if "bookmarks" not in existing_cols:
                conn.execute(
                    text(
                        "ALTER TABLE conversations "
                        "ADD COLUMN bookmarks TEXT NOT NULL DEFAULT '[]'"
                    )
                )
                conn.commit()
                logger.info("Migration: added bookmarks column to conversations")
            else:
                logger.debug(
                    "Migration: bookmarks column already exists, skipping"
                )

    yield

    # Shutdown
    logger = get_logger("shutdown")
    logger.info("Application shutting down")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="408考研AI专属助教 — PDF题库导入、刷题、错题分析",
    lifespan=lifespan,
)

# --- CORS ---
_cors_origins = ["*"] if settings.debug else ["http://localhost:8501", "http://127.0.0.1:8501"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=not settings.debug,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Register routers ---
app.include_router(import_router)
app.include_router(questions_router)
app.include_router(quiz_router)
app.include_router(tutor_router)
app.include_router(misconceptions_router)
app.include_router(wrong_questions_router)
app.include_router(conversations_router)
app.include_router(weak_knowledge_router)
app.include_router(agent_exports_router)

# --- Static files: serve extracted question images ---
_images_dir = Path(settings.image_dir)
_images_dir.mkdir(parents=True, exist_ok=True)
app.mount("/images", StaticFiles(directory=str(_images_dir)), name="images")


# --- Global exception handler ---
@app.exception_handler(AppBaseException)
async def app_exception_handler(request: Request, exc: AppBaseException):
    """Handle custom application exceptions."""
    logger = get_logger("exception")
    logger.error(f"{type(exc).__name__}: {exc.message}")
    return JSONResponse(
        status_code=400,
        content={"error": type(exc).__name__, "message": exc.message},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Catch-all exception handler."""
    logger = get_logger("exception")
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "InternalError", "message": "服务器内部错误"},
    )


# --- Health check ---
@app.get("/health")
def health_check():
    """Simple health check endpoint."""
    return {"status": "ok", "app": settings.app_name, "version": settings.app_version}
