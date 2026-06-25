"""API shape tests for practice question assets."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.deps import get_db
from app.api.questions import router as questions_router
from app.database.base import Base
from app.models.question import Question
from app.models.question_asset import QuestionAsset


@pytest.fixture
def api_db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _client_for_session(api_db_session) -> TestClient:
    app = FastAPI()
    app.include_router(questions_router)

    def override_get_db():
        yield api_db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _create_question_with_assets(api_db_session) -> Question:
    question = Question(
        subject="data-structure",
        chapter="chapter-1",
        knowledge_tag="asset-shape",
        question_type="choice",
        question_text="Which structure supports FIFO operations?",
        option_a="Stack",
        option_b="Queue",
        option_c="Tree",
        option_d="Graph",
        answer="B",
        image_path="legacy/images/fifo.png",
        source_pdf="assets.pdf",
        text_hash="asset-shape-question",
    )
    api_db_session.add(question)
    api_db_session.commit()
    api_db_session.refresh(question)

    image_asset = QuestionAsset(
        question_id=question.id,
        asset_type="image",
        source_type="import",
        path="question_assets/bank/images/fifo.png",
        page_no=3,
        bbox_json='{"x":1,"y":2,"w":30,"h":40}',
        confidence=0.91,
    )
    table_asset = QuestionAsset(
        question_id=question.id,
        asset_type="table",
        source_type="mineru",
        path="question_assets/bank/tables/fifo.md",
        page_no=4,
        text_content="| Operation | Order |\n| --- | --- |\n| enqueue | rear |",
        confidence=0.87,
    )
    api_db_session.add_all([image_asset, table_asset])
    api_db_session.commit()
    return question


def _assert_assets_shape(question_payload: dict) -> None:
    assert question_payload["image_path"] == "legacy/images/fifo.png"

    assets = question_payload["assets"]
    assert [asset["asset_type"] for asset in assets] == ["image", "table"]

    image_asset = assets[0]
    assert image_asset["path"] == "question_assets/bank/images/fifo.png"
    assert image_asset["source"] == "import"
    assert image_asset["source_type"] == "import"
    assert image_asset["page_number"] == 3
    assert image_asset["page_no"] == 3
    assert image_asset["bbox_json"] == '{"x":1,"y":2,"w":30,"h":40}'
    assert image_asset["confidence"] == 0.91

    table_asset = assets[1]
    assert table_asset["path"] == "question_assets/bank/tables/fifo.md"
    assert table_asset["content_md"] == table_asset["text_content"]
    assert table_asset["content_md"].startswith("| Operation | Order |")
    assert table_asset["source"] == "mineru"
    assert table_asset["source_type"] == "mineru"
    assert table_asset["page_number"] == 4
    assert table_asset["page_no"] == 4


def test_random_questions_include_structured_assets(api_db_session):
    _create_question_with_assets(api_db_session)
    client = _client_for_session(api_db_session)

    response = client.get(
        "/api/questions/random",
        params={"count": 1, "subject": "data-structure", "question_type": "choice"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    _assert_assets_shape(payload["questions"][0])


def test_by_chapter_questions_include_structured_assets(api_db_session):
    _create_question_with_assets(api_db_session)
    client = _client_for_session(api_db_session)

    response = client.get(
        "/api/questions/by_chapter",
        params={
            "subject": "data-structure",
            "chapter": "chapter-1",
            "question_type": "choice",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    _assert_assets_shape(payload["questions"][0])


def test_practice_question_text_removes_markdown_image_refs(api_db_session):
    question = Question(
        subject="computer-organization",
        chapter="machine-code",
        knowledge_tag="figures",
        question_type="other",
        question_text=(
            "Code is shown below.\n\n"
            "![](images/diagram.jpg)\n\n"
            "Figure (a) explains the datapath."
        ),
        image_path="question_assets/sample/images/diagram.jpg",
        source_pdf="figures.md",
        text_hash="markdown-image-ref-question",
    )
    api_db_session.add(question)
    api_db_session.commit()

    client = _client_for_session(api_db_session)
    response = client.get(
        "/api/questions/random",
        params={
            "count": 1,
            "subject": "computer-organization",
            "question_type": "other",
        },
    )

    assert response.status_code == 200
    payload = response.json()["questions"][0]
    assert "![]" not in payload["question_text"]
    assert "images/diagram.jpg" not in payload["question_text"]
    assert payload["image_path"] == "question_assets/sample/images/diagram.jpg"


def test_random_choice_questions_exclude_incomplete_options(api_db_session):
    complete = Question(
        subject="computer-organization",
        chapter="cpu",
        knowledge_tag="choice-quality",
        question_type="choice",
        question_text="Which option is complete?",
        option_a="A",
        option_b="B",
        option_c="C",
        option_d="D",
        answer="A",
        source_pdf="quality.md",
        text_hash="complete-choice",
    )
    incomplete = Question(
        subject="computer-organization",
        chapter="cpu",
        knowledge_tag="choice-quality",
        question_type="choice",
        question_text="This OCR split lost option B.",
        option_a="A",
        option_b="",
        option_c="C",
        option_d="D",
        answer="A",
        source_pdf="quality.md",
        text_hash="incomplete-choice",
    )
    api_db_session.add_all([complete, incomplete])
    api_db_session.commit()

    client = _client_for_session(api_db_session)
    response = client.get(
        "/api/questions/random",
        params={
            "count": 2,
            "subject": "computer-organization",
            "question_type": "choice",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["questions"][0]["id"] == complete.id


def test_by_chapter_choice_questions_exclude_incomplete_options(api_db_session):
    complete = Question(
        subject="computer-organization",
        chapter="cpu",
        knowledge_tag="choice-quality",
        question_type="choice",
        question_text="Which option is complete?",
        option_a="A",
        option_b="B",
        option_c="C",
        option_d="D",
        answer="A",
        source_pdf="quality.md",
        text_hash="complete-choice-by-chapter",
    )
    incomplete = Question(
        subject="computer-organization",
        chapter="cpu",
        knowledge_tag="choice-quality",
        question_type="choice",
        question_text="This OCR split lost option C.",
        option_a="A",
        option_b="B",
        option_c=None,
        option_d="D",
        answer="A",
        source_pdf="quality.md",
        text_hash="incomplete-choice-by-chapter",
    )
    api_db_session.add_all([complete, incomplete])
    api_db_session.commit()

    client = _client_for_session(api_db_session)
    response = client.get(
        "/api/questions/by_chapter",
        params={
            "subject": "computer-organization",
            "chapter": "cpu",
            "question_type": "choice",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert payload["questions"][0]["id"] == complete.id


def test_choice_chapter_counts_exclude_incomplete_options(api_db_session):
    complete = Question(
        subject="computer-organization",
        chapter="cpu",
        knowledge_tag="choice-quality",
        question_type="choice",
        question_text="Which option is complete?",
        option_a="A",
        option_b="B",
        option_c="C",
        option_d="D",
        answer="A",
        source_pdf="quality.md",
        text_hash="complete-choice-chapters",
    )
    incomplete = Question(
        subject="computer-organization",
        chapter="cpu",
        knowledge_tag="choice-quality",
        question_type="choice",
        question_text="This OCR split lost option A.",
        option_a=" ",
        option_b="B",
        option_c="C",
        option_d="D",
        answer="A",
        source_pdf="quality.md",
        text_hash="incomplete-choice-chapters",
    )
    api_db_session.add_all([complete, incomplete])
    api_db_session.commit()

    client = _client_for_session(api_db_session)
    response = client.get(
        "/api/questions/chapters",
        params={
            "subject": "computer-organization",
            "question_type": "choice",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["chapters"] == [{"name": "cpu", "count": 1}]
