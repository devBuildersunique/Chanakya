from fastapi.testclient import TestClient

from app.main import app
from app.schemas import DocumentGraph


def test_application_imports() -> None:
    assert app.title == "Chanakya API"


def test_health_endpoint() -> None:
    response = TestClient(app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_minimal_document_graph_validates() -> None:
    document = DocumentGraph(document_id="document-001")

    assert document.document_id == "document-001"
    assert document.entities == []
    assert document.relationships == []
