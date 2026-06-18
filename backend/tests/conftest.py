"""Pytest fixtures for testing."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.base import Base

# Import all models to register them
import app.models  # noqa: F401


@pytest.fixture(scope="function")
def db_session():
    """Create an in-memory SQLite database and yield a session.

    Tables are created fresh for each test and dropped after.
    """
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def sample_question(db_session):
    """Create a sample question in the database and return it."""
    from app.models.question import Question

    q = Question(
        subject="数据结构",
        chapter="第一章 绪论",
        knowledge_tag="时间复杂度",
        question_type="choice",
        question_text="下列算法的时间复杂度是？",
        option_a="O(n)",
        option_b="O(n^2)",
        option_c="O(log n)",
        option_d="O(n log n)",
        answer="B",
        analysis="嵌套循环，外层n次，内层n次，总共n^2次操作。",
        source_pdf="test.pdf",
        text_hash="abc123test",
    )
    db_session.add(q)
    db_session.commit()
    db_session.refresh(q)
    return q
