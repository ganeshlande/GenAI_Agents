from fastapi.testclient import TestClient
from app.main import app


def test_health_check():
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "ganesh-agentops-backend"
    assert "version" in body


def test_docs_available():
    with TestClient(app) as client:
        response = client.get("/docs")
    assert response.status_code == 200


def test_openapi_schema():
    with TestClient(app) as client:
        response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "Ganesh AgentOps"
