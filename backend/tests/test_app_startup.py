"""Smoke tests for FastAPI application startup."""

from fastapi.testclient import TestClient

from app.main import app


def test_app_lifespan_starts_and_health_check_works():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
