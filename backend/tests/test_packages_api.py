import uuid

from fastapi.testclient import TestClient

from app.db.database import Base, SessionLocal, engine
from app.main import app
from app.models.filing import FilingPackage


client = TestClient(app)


def setup_function() -> None:
    Base.metadata.create_all(bind=engine)


def teardown_function() -> None:
    Base.metadata.drop_all(bind=engine)


def test_create_package_successfully() -> None:
    response = client.post(
        "/api/v1/packages",
        json={
            "authority_code": "authority_a",
            "name": "Test Filing Package",
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert uuid.UUID(body["id"])
    assert body["authority_code"] == "authority_a"
    assert body["name"] == "Test Filing Package"
    assert body["status"] == "pending"
    assert body["document_count"] == 0


def test_create_package_rejects_unknown_authority() -> None:
    response = client.post(
        "/api/v1/packages",
        json={
            "authority_code": "unknown_authority",
            "name": "Invalid Package",
        },
    )

    assert response.status_code == 400
    assert "Unknown authority code" in response.json()["detail"]


def test_created_package_is_persisted() -> None:
    response = client.post(
        "/api/v1/packages",
        json={
            "authority_code": "authority_a",
            "name": "Persisted Package",
        },
    )

    assert response.status_code == 201

    package_id = uuid.UUID(response.json()["id"])

    db = SessionLocal()
    try:
        package = db.get(FilingPackage, package_id)

        assert package is not None
        assert package.authority_code == "authority_a"
        assert package.name == "Persisted Package"
        assert package.status == "pending"
    finally:
        db.close()


def test_new_package_has_pending_status() -> None:
    response = client.post(
        "/api/v1/packages",
        json={
            "authority_code": "authority_a",
            "name": "Pending Package",
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "pending"