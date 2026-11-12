"""Health endpoint contract for Milestone 0."""

from fastapi.testclient import TestClient

from tradedisha.main import create_app


def test_health_reports_ok_with_version() -> None:
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "tradedisha"
    assert body["version"] == "0.1.0"
    assert body["milestone"] == 0
