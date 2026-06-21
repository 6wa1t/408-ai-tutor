"""PDF Import API routes."""

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import get_settings
from app.core.logging_config import get_logger
from app.schemas.import_report import ImportReportResponse
from app.services.import_service import ImportService

logger = get_logger("api.import")

router = APIRouter(prefix="/api/import", tags=["导入"])


def _validate_directory_path(directory: str) -> Path:
    """Validate that the directory path is within allowed locations."""
    settings = get_settings()
    allowed_roots = [
        Path(settings.pdf_dir).resolve(),
        Path(settings.image_dir).resolve(),
    ]

    resolved = Path(directory).resolve()

    if not resolved.exists():
        raise HTTPException(status_code=400, detail=f"目录不存在: {directory}")
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail=f"路径不是目录: {directory}")

    for root in allowed_roots:
        try:
            resolved.relative_to(root)
            return resolved
        except ValueError:
            continue

    raise HTTPException(
        status_code=403,
        detail=f"不允许访问该目录。仅允许以下路径: {', '.join(str(r) for r in allowed_roots)}"
    )


@router.post("/upload", response_model=ImportReportResponse)
async def upload_and_import_pdf(
    file: UploadFile = File(..., description="PDF题库文件"),
    force_vlm: bool = Form(False, description="强制使用视觉大模型(VLM)提取，跳过文本提取"),
    auto_process: bool = Form(True, description="导入后自动提取配图并修复PUA乱码"),
    db: Session = Depends(get_db),
):
    """Upload a single PDF file and import its questions.

    The file is saved to a temporary location, parsed, and then
    imported into the database.

    Set force_vlm=True to skip text extraction and use VLM directly
    (useful for known-scanned/image-based PDFs).
    Set auto_process=False to skip post-import image extraction and PUA repair.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    logger.info(f"Received upload: {file.filename} (force_vlm={force_vlm}, auto_process={auto_process})")

    # Save to temp file
    tmp_dir = tempfile.mkdtemp()
    tmp_path = Path(tmp_dir) / file.filename
    try:
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        service = ImportService(db, force_vlm=force_vlm, auto_process=auto_process)
        result = service.import_pdf(str(tmp_path))

        return ImportReportResponse(
            started_at=datetime.now(),
            finished_at=datetime.now(),
            total_files=1,
            total_questions=result.total_found,
            total_success=result.success_count,
            total_skipped=result.skipped_count,
            total_errors=result.error_count,
            file_results=[result],
        )
    except Exception as e:
        logger.error(f"Upload import failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        # Cleanup temp file
        if tmp_path.exists():
            tmp_path.unlink()
        Path(tmp_dir).rmdir()


@router.post("/directory", response_model=ImportReportResponse)
async def import_directory(
    directory: str = Form(..., description="PDF题库目录路径"),
    force_vlm: bool = Form(False, description="强制使用视觉大模型(VLM)提取"),
    auto_process: bool = Form(True, description="导入后自动提取配图并修复PUA乱码"),
    db: Session = Depends(get_db),
):
    """Import all PDF files from a specified directory.

    Scans the directory for .pdf files, parses each one,
    and imports questions into the database.
    """
    # Validate path to prevent directory traversal
    _validate_directory_path(directory)

    logger.info(f"Directory import request: {directory} (force_vlm={force_vlm}, auto_process={auto_process})")

    try:
        service = ImportService(db, force_vlm=force_vlm, auto_process=auto_process)
        report = service.import_directory(directory)
        return report
    except Exception as e:
        logger.error(f"Directory import failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
