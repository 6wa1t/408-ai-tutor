"""Tests for Markdown import media normalization."""

from pathlib import Path

from app.config import get_settings
from app.models.question import Question
from app.models.question_asset import QuestionAsset
from app.services.import_service import ImportService


def test_markdown_import_copies_images_to_question_assets(
    db_session,
    tmp_path,
    monkeypatch,
):
    """Markdown image sources are copied into runtime media and stored as assets."""
    md_dir = tmp_path / "mineru"
    image_dir = md_dir / "images"
    image_dir.mkdir(parents=True)
    source_image = image_dir / "diagram.jpg"
    source_image.write_bytes(b"image bytes")

    md_path = md_dir / "sample_bank.md"
    md_path.write_text(
        "\n".join(
            [
                "## 1.1 Sample Section",
                "1. Which component is shown in the diagram?",
                "![](images/diagram.jpg)",
                "A. ALU",
                "B. Cache",
                "C. Register",
                "D. Bus",
            ]
        ),
        encoding="utf-8",
    )

    runtime_media_dir = tmp_path / "images" / "question_assets"
    monkeypatch.setattr(
        get_settings(),
        "runtime_media_dir",
        str(runtime_media_dir),
    )

    result = ImportService(
        db_session,
        import_mode="markdown",
        auto_process=False,
    ).import_file(str(md_path))

    assert result.success_count == 1

    question = db_session.query(Question).one()
    asset = db_session.query(QuestionAsset).one()

    assert asset.question_id == question.id
    assert asset.asset_type == "image"
    assert asset.source_type == "markdown"
    assert asset.page_no is None
    assert asset.confidence == 0.9

    assert asset.path.startswith("question_assets/")
    assert not Path(asset.path).is_absolute()
    assert ".." not in asset.path.split("/")

    copied_file = runtime_media_dir / asset.path.removeprefix("question_assets/")
    assert copied_file.read_bytes() == b"image bytes"
    assert question.image_path == asset.path

    source_image_path = str(source_image.resolve())
    assert source_image_path not in (question.image_path or "")
    assert source_image_path not in asset.path


def test_markdown_import_does_not_store_absolute_source_image_path(
    db_session,
    tmp_path,
    monkeypatch,
):
    """The legacy image_path field stores runtime-relative paths, not sources."""
    md_dir = tmp_path / "mineru"
    image_dir = md_dir / "images"
    image_dir.mkdir(parents=True)
    source_image = image_dir / "diagram.jpg"
    source_image.write_bytes(b"image bytes")

    md_path = md_dir / "sample_bank.md"
    md_path.write_text(
        "\n".join(
            [
                "## 1.1 Sample Section",
                "1. Which component is shown in the diagram?",
                "![](images/diagram.jpg)",
                "A. ALU",
                "B. Cache",
                "C. Register",
                "D. Bus",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        get_settings(),
        "runtime_media_dir",
        str(tmp_path / "images" / "question_assets"),
    )

    result = ImportService(
        db_session,
        import_mode="markdown",
        auto_process=False,
    ).import_file(str(md_path))

    assert result.success_count == 1
    question = db_session.query(Question).one()

    assert question.image_path is not None
    assert question.image_path.startswith("question_assets/")
    assert str(source_image.resolve()) not in question.image_path
