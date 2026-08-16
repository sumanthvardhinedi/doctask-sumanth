import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_package_list_is_available_after_startup() -> None:
    response = client.get("/api/v1/packages")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
