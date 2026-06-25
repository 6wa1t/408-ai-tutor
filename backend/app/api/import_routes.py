"""Import API routes — file upload, directory import, and question bank management.

Supports three import modes:
- text_pdf:    PyMuPDF text extraction (fast, free)
- scanned_pdf: Qwen VL Max vision model (for scanned PDFs)
- markdown:    Direct markdown parsing (recommended, MinerU output)
"""

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.config import get_settings
from app.core.logging_config import get_logger
from app.schemas.import_report import ImportReportResponse
from app.services.bank_service import BankService
from app.services.import_service import ImportService, IMPORT_MODES

logger = get_logger("api.import")

router = APIRouter(prefix="/api/import", tags=["导入"])


# ── Helper ─────────────────────────────────────

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


def _validate_import_mode(mode: str) -> str:
    """Validate import_mode parameter."""
    if mode not in IMPORT_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"无效的导入模式: '{mode}'。可选值: {', '.join(IMPORT_MODES)}"
        )
    return mode


# ── File upload ────────────────────────────────

@router.post("/upload", response_model=ImportReportResponse)
async def upload_and_import_file(
    file: UploadFile = File(..., description="PDF 或 Markdown 题库文件"),
    import_mode: str = Form("text_pdf", description="导入模式: text_pdf / scanned_pdf / markdown"),
    auto_process: bool = Form(True, description="导入后自动提取配图并修复PUA乱码"),
    db: Session = Depends(get_db),
):
    """Upload a single file and import its questions.

    - text_pdf: 文字型PDF，PyMuPDF快速提取（免费）
    - scanned_pdf: 扫描型PDF，千问VL-Max视觉识别（有API费用）
    - markdown: Markdown文件导入（推荐，MinerU转换输出）
    """
    _validate_import_mode(import_mode)

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    filename_lower = file.filename.lower()

    # Validate file extension based on import mode
    if import_mode == "markdown":
        if not filename_lower.endswith(".md"):
            raise HTTPException(
                status_code=400,
                detail="Markdown 导入模式仅接受 .md 文件"
            )
    else:
        if not filename_lower.endswith(".pdf"):
            raise HTTPException(
                status_code=400,
                detail="PDF 导入模式仅接受 .pdf 文件"
            )

    logger.info(
        f"Received upload: {file.filename} "
        f"(mode={import_mode}, auto_process={auto_process})"
    )

    # Save to temp file
    tmp_dir = tempfile.mkdtemp()
    tmp_path = Path(tmp_dir) / file.filename
    try:
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        service = ImportService(
            db, import_mode=import_mode, auto_process=auto_process
        )
        result = service.import_file(str(tmp_path))

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


# ── Directory import ───────────────────────────

@router.post("/directory", response_model=ImportReportResponse)
async def import_directory(
    directory: str = Form(..., description="题库文件目录路径"),
    import_mode: str = Form("text_pdf", description="导入模式: text_pdf / scanned_pdf / markdown"),
    auto_process: bool = Form(True, description="导入后自动提取配图并修复PUA乱码"),
    db: Session = Depends(get_db),
):
    """Import all files from a specified directory.

    - text_pdf / scanned_pdf: 扫描目录中的 .pdf 文件
    - markdown: 递归扫描目录中的 .md 文件
    """
    _validate_import_mode(import_mode)
    _validate_directory_path(directory)

    logger.info(
        f"Directory import request: {directory} "
        f"(mode={import_mode}, auto_process={auto_process})"
    )

    try:
        service = ImportService(
            db, import_mode=import_mode, auto_process=auto_process
        )
        report = service.import_directory(directory)
        return report
    except Exception as e:
        logger.error(f"Directory import failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Question bank endpoints ────────────────────

class BankImportRequest(BaseModel):
    bank_id: str = Field(..., description="题库ID")


class BankExportRequest(BaseModel):
    subject: str = Field(..., description="科目名称")
    bank_name: str = Field("", description="题库显示名称")
    description: str = Field("", description="题库描述")


@router.get("/banks")
async def list_banks(db: Session = Depends(get_db)):
    """List all available pre-built question banks."""
    service = BankService(db)
    banks = service.list_banks()
    return {"banks": banks, "count": len(banks)}


@router.post("/banks/{bank_id}")
async def import_bank(bank_id: str, db: Session = Depends(get_db)):
    """Import a pre-built question bank into the current database.

    Uses text_hash deduplication to avoid importing duplicate questions.
    """
    try:
        service = BankService(db)
        result = service.import_bank(bank_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Bank import failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export")
async def export_bank(
    request: BankExportRequest,
    db: Session = Depends(get_db),
):
    """Export questions from the current database as a shareable bank package.

    Creates a SQLite database + metadata.json in the question_banks/ directory.
    """
    try:
        service = BankService(db)
        result = service.export_bank(
            subject=request.subject,
            bank_name=request.bank_name,
            description=request.description,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Bank export failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
