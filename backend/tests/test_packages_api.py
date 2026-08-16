import uuid

from fastapi.testclient import TestClient
from app.models.finding import ApprovalDecision
from app.db.database import Base, SessionLocal, engine
from app.main import app
from app.models.filing import FilingPackage, PackageDocument
from app.models.validation import ValidationRun


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


def test_create_document_successfully() -> None:
    package_response = client.post(
        "/api/v1/packages",
        json={
            "authority_code": "authority_a",
            "name": "Document Test Package",
        },
    )

    assert package_response.status_code == 201

    package_id = package_response.json()["id"]

    response = client.post(
        f"/api/v1/packages/{package_id}/documents",
        json={
            "filename": "cover_letter.pdf",
            "content_type": "application/pdf",
            "file_size_bytes": 125000,
            "storage_path": "test/cover_letter.pdf",
            "sort_order": 0,
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert uuid.UUID(body["id"])
    assert body["package_id"] == package_id
    assert body["filename"] == "cover_letter.pdf"
    assert body["content_type"] == "application/pdf"
    assert body["file_size_bytes"] == 125000
    assert body["storage_path"] == "test/cover_letter.pdf"
    assert body["sort_order"] == 0


def test_create_document_rejects_unknown_package() -> None:
    package_id = str(uuid.uuid4())

    response = client.post(
        f"/api/v1/packages/{package_id}/documents",
        json={
            "filename": "cover_letter.pdf",
            "content_type": "application/pdf",
            "file_size_bytes": 125000,
            "storage_path": "test/cover_letter.pdf",
            "sort_order": 0,
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Filing package not found"


def test_created_document_is_persisted() -> None:
    package_response = client.post(
        "/api/v1/packages",
        json={
            "authority_code": "authority_a",
            "name": "Persistence Test Package",
        },
    )

    assert package_response.status_code == 201

    package_id = uuid.UUID(package_response.json()["id"])

    response = client.post(
        f"/api/v1/packages/{package_id}/documents",
        json={
            "filename": "financial_statement.pdf",
            "content_type": "application/pdf",
            "file_size_bytes": 250000,
            "storage_path": "test/financial_statement.pdf",
            "sort_order": 1,
        },
    )

    assert response.status_code == 201

    document_id = uuid.UUID(response.json()["id"])

    db = SessionLocal()
    try:
        document = db.get(PackageDocument, document_id)

        assert document is not None
        assert document.package_id == package_id
        assert document.filename == "financial_statement.pdf"
        assert document.content_type == "application/pdf"
        assert document.file_size_bytes == 250000
        assert document.storage_path == "test/financial_statement.pdf"
        assert document.sort_order == 1
    finally:
        db.close()


def test_document_belongs_to_correct_package() -> None:
    first_package = client.post(
        "/api/v1/packages",
        json={
            "authority_code": "authority_a",
            "name": "First Package",
        },
    )

    second_package = client.post(
        "/api/v1/packages",
        json={
            "authority_code": "authority_a",
            "name": "Second Package",
        },
    )

    assert first_package.status_code == 201
    assert second_package.status_code == 201

    first_package_id = first_package.json()["id"]
    second_package_id = second_package.json()["id"]

    response = client.post(
        f"/api/v1/packages/{first_package_id}/documents",
        json={
            "filename": "document.pdf",
            "content_type": "application/pdf",
            "file_size_bytes": 1000,
            "storage_path": "test/document.pdf",
            "sort_order": 0,
        },
    )

    assert response.status_code == 201
    assert response.json()["package_id"] == first_package_id
    assert response.json()["package_id"] != second_package_id


def test_adding_document_keeps_package_pending() -> None:
    package_response = client.post(
        "/api/v1/packages",
        json={
            "authority_code": "authority_a",
            "name": "Pending Package",
        },
    )

    assert package_response.status_code == 201

    package_id = uuid.UUID(package_response.json()["id"])

    response = client.post(
        f"/api/v1/packages/{package_id}/documents",
        json={
            "filename": "document.pdf",
            "content_type": "application/pdf",
            "file_size_bytes": 1000,
            "storage_path": "test/document.pdf",
            "sort_order": 0,
        },
    )

    assert response.status_code == 201

    db = SessionLocal()
    try:
        package = db.get(FilingPackage, package_id)

        assert package is not None
        assert package.status == "pending"
    finally:
        db.close()


def test_validate_package_successfully() -> None:
    package_response = client.post(
        "/api/v1/packages",
        json={
            "authority_code": "authority_a",
            "name": "Validation Package",
        },
    )

    assert package_response.status_code == 201

    package_id = package_response.json()["id"]

    document_response = client.post(
        f"/api/v1/packages/{package_id}/documents",
        json={
            "filename": "cover_letter.pdf",
            "content_type": "application/pdf",
            "file_size_bytes": 1000,
            "storage_path": "test/cover_letter.pdf",
            "sort_order": 0,
        },
    )

    assert document_response.status_code == 201

    response = client.post(
        f"/api/v1/packages/{package_id}/validate",
    )

    assert response.status_code == 201

    body = response.json()

    assert uuid.UUID(body["id"])
    assert body["package_id"] == package_id
    assert body["status"] in {"completed", "awaiting_approval"}


def test_validate_unknown_package_returns_404() -> None:
    package_id = uuid.uuid4()

    response = client.post(
        f"/api/v1/packages/{package_id}/validate",
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Filing package not found"


def test_validation_run_is_persisted() -> None:
    package_response = client.post(
        "/api/v1/packages",
        json={
            "authority_code": "authority_a",
            "name": "Persisted Validation Package",
        },
    )

    assert package_response.status_code == 201

    package_id = uuid.UUID(package_response.json()["id"])

    document_response = client.post(
        f"/api/v1/packages/{package_id}/documents",
        json={
            "filename": "cover_letter.pdf",
            "content_type": "application/pdf",
            "file_size_bytes": 1000,
            "storage_path": "test/cover_letter.pdf",
            "sort_order": 0,
        },
    )

    assert document_response.status_code == 201

    response = client.post(
        f"/api/v1/packages/{package_id}/validate",
    )

    assert response.status_code == 201

    validation_run_id = uuid.UUID(response.json()["id"])

    db = SessionLocal()
    try:
        validation_run = db.get(ValidationRun, validation_run_id)

        assert validation_run is not None
        assert validation_run.package_id == package_id
        assert validation_run.status in {"completed", "awaiting_approval"}
    finally:
        db.close()

def test_get_validation_runs_for_package() -> None:
    package_response = client.post(
        "/api/v1/packages",
        json={
            "authority_code": "authority_a",
            "name": "Validation Runs Package",
        },
    )

    assert package_response.status_code == 201
    package_id = package_response.json()["id"]

    document_response = client.post(
        f"/api/v1/packages/{package_id}/documents",
        json={
            "filename": "cover_letter.pdf",
            "content_type": "application/pdf",
            "file_size_bytes": 1000,
            "storage_path": "test/cover_letter.pdf",
            "sort_order": 0,
        },
    )

    assert document_response.status_code == 201

    validation_response = client.post(
        f"/api/v1/packages/{package_id}/validate",
    )

    assert validation_response.status_code == 201

    validation_run_id = validation_response.json()["id"]

    response = client.get(
        f"/api/v1/packages/{package_id}/validation-runs",
    )

    assert response.status_code == 200

    body = response.json()

    assert len(body) == 1
    assert body[0]["id"] == validation_run_id
    assert body[0]["package_id"] == package_id
    assert body[0]["authority_code"] == "authority_a"
    assert body[0]["status"] in {"completed", "awaiting_approval"}
def test_get_validation_runs_returns_empty_list() -> None:
    package_response = client.post(
        "/api/v1/packages",
        json={
            "authority_code": "authority_a",
            "name": "No Validation Runs Package",
        },
    )

    assert package_response.status_code == 201
    package_id = package_response.json()["id"]

    response = client.get(
        f"/api/v1/packages/{package_id}/validation-runs",
    )

    assert response.status_code == 200
    assert response.json() == []


def test_get_validation_runs_unknown_package_returns_404() -> None:
    package_id = uuid.uuid4()

    response = client.get(
        f"/api/v1/packages/{package_id}/validation-runs",
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Filing package not found"


def test_get_validation_findings_for_run() -> None:
    package_response = client.post(
        "/api/v1/packages",
        json={
            "authority_code": "authority_a",
            "name": "Findings Package",
        },
    )

    assert package_response.status_code == 201
    package_id = package_response.json()["id"]

    document_response = client.post(
        f"/api/v1/packages/{package_id}/documents",
        json={
            "filename": "cover_letter.pdf",
            "content_type": "application/pdf",
            "file_size_bytes": 1000,
            "storage_path": "test/cover_letter.pdf",
            "sort_order": 0,
        },
    )

    assert document_response.status_code == 201

    validation_response = client.post(
        f"/api/v1/packages/{package_id}/validate",
    )

    assert validation_response.status_code == 201

    validation_run_id = validation_response.json()["id"]

    response = client.get(
        f"/api/v1/packages/{package_id}/validation-runs/{validation_run_id}/findings",
    )

    assert response.status_code == 200

    body = response.json()

    assert isinstance(body, list)

    for finding in body:
        assert uuid.UUID(finding["id"])
        assert finding["validation_run_id"] == validation_run_id
        assert "rule_id" in finding
        assert "rule_category" in finding
        assert "severity" in finding
        assert "result" in finding
        assert "explanation" in finding
        assert "is_hard_rejection" in finding


def test_get_validation_findings_unknown_run_returns_404() -> None:
    package_response = client.post(
        "/api/v1/packages",
        json={
            "authority_code": "authority_a",
            "name": "Unknown Run Package",
        },
    )

    assert package_response.status_code == 201
    package_id = package_response.json()["id"]

    validation_run_id = uuid.uuid4()

    response = client.get(
        f"/api/v1/packages/{package_id}/validation-runs/{validation_run_id}/findings",
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Validation run not found"


def test_get_validation_findings_rejects_run_from_another_package() -> None:
    first_package = client.post(
        "/api/v1/packages",
        json={
            "authority_code": "authority_a",
            "name": "First Findings Package",
        },
    )

    second_package = client.post(
        "/api/v1/packages",
        json={
            "authority_code": "authority_a",
            "name": "Second Findings Package",
        },
    )

    assert first_package.status_code == 201
    assert second_package.status_code == 201

    first_package_id = first_package.json()["id"]
    second_package_id = second_package.json()["id"]

    document_response = client.post(
        f"/api/v1/packages/{first_package_id}/documents",
        json={
            "filename": "document.pdf",
            "content_type": "application/pdf",
            "file_size_bytes": 1000,
            "storage_path": "test/document.pdf",
            "sort_order": 0,
        },
    )

    assert document_response.status_code == 201

    validation_response = client.post(
        f"/api/v1/packages/{first_package_id}/validate",
    )

    assert validation_response.status_code == 201

    validation_run_id = validation_response.json()["id"]

    response = client.get(
        f"/api/v1/packages/{second_package_id}/validation-runs/{validation_run_id}/findings",
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Validation run not found"


def test_get_validation_findings_unknown_package_returns_404() -> None:
    package_response = client.post(
        "/api/v1/packages",
        json={
            "authority_code": "authority_a",
            "name": "Unknown Package Findings",
        },
    )

    assert package_response.status_code == 201

    validation_run_id = uuid.uuid4()
    unknown_package_id = uuid.uuid4()

    response = client.get(
        f"/api/v1/packages/{unknown_package_id}/validation-runs/{validation_run_id}/findings",
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Filing package not found"

def test_approve_finding_successfully() -> None:
    package_response = client.post(
        "/api/v1/packages",
        json={
            "authority_code": "authority_a",
            "name": "Approval Package",
        },
    )

    assert package_response.status_code == 201
    package_id = package_response.json()["id"]

    document_response = client.post(
        f"/api/v1/packages/{package_id}/documents",
        json={
            "filename": "cover_letter.pdf",
            "content_type": "application/pdf",
            "file_size_bytes": 1000,
            "storage_path": "test/cover_letter.pdf",
            "sort_order": 0,
        },
    )

    assert document_response.status_code == 201

    validation_response = client.post(
        f"/api/v1/packages/{package_id}/validate",
    )

    assert validation_response.status_code == 201
    validation_run_id = validation_response.json()["id"]

    findings_response = client.get(
        f"/api/v1/packages/{package_id}/validation-runs/"
        f"{validation_run_id}/findings",
    )

    assert findings_response.status_code == 200

    findings = findings_response.json()
    assert findings
    finding_id = findings[0]["id"]
    response = client.post(
        f"/api/v1/packages/{package_id}/validation-runs/"
        f"{validation_run_id}/findings/{finding_id}/approval",
        json={
            "approved": True,
            "reviewer_notes": "Reviewed and accepted.",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert uuid.UUID(body["id"])
    assert body["finding_id"] == finding_id
    assert body["approved"] is True
    assert body["reviewer_notes"] == "Reviewed and accepted."
    assert body["decided_at"] is not None

    db = SessionLocal()
    try:
        decision = db.query(ApprovalDecision).filter_by(
            finding_id=uuid.UUID(finding_id)
        ).first()

        assert decision is not None
        assert decision.approved is True
        assert decision.reviewer_notes == "Reviewed and accepted."
    finally:
        db.close()


def test_reject_finding_successfully() -> None:
    package_response = client.post(
        "/api/v1/packages",
        json={
            "authority_code": "authority_a",
            "name": "Rejection Package",
        },
    )

    assert package_response.status_code == 201
    package_id = package_response.json()["id"]

    document_response = client.post(
        f"/api/v1/packages/{package_id}/documents",
        json={
            "filename": "document.pdf",
            "content_type": "application/pdf",
            "file_size_bytes": 1000,
            "storage_path": "test/document.pdf",
            "sort_order": 0,
        },
    )

    assert document_response.status_code == 201

    validation_response = client.post(
        f"/api/v1/packages/{package_id}/validate",
    )

    assert validation_response.status_code == 201
    validation_run_id = validation_response.json()["id"]

    findings_response = client.get(
        f"/api/v1/packages/{package_id}/validation-runs/"
        f"{validation_run_id}/findings",
    )

    assert findings_response.status_code == 200

    findings = findings_response.json()
    assert findings
    finding_id = findings[0]["id"]

    response = client.post(
        f"/api/v1/packages/{package_id}/validation-runs/"
        f"{validation_run_id}/findings/{finding_id}/approval",
        json={
            "approved": False,
            "reviewer_notes": "Requires correction.",
        },
    )

    assert response.status_code == 200
    assert response.json()["approved"] is False
    assert response.json()["reviewer_notes"] == "Requires correction."


def test_cannot_decide_on_finding_twice() -> None:
    package_response = client.post(
        "/api/v1/packages",
        json={
            "authority_code": "authority_a",
            "name": "Duplicate Approval Package",
        },
    )

    assert package_response.status_code == 201
    package_id = package_response.json()["id"]

    document_response = client.post(
        f"/api/v1/packages/{package_id}/documents",
        json={
            "filename": "document.pdf",
            "content_type": "application/pdf",
            "file_size_bytes": 1000,
            "storage_path": "test/document.pdf",
            "sort_order": 0,
        },
    )

    assert document_response.status_code == 201

    validation_response = client.post(
        f"/api/v1/packages/{package_id}/validate",
    )

    assert validation_response.status_code == 201
    validation_run_id = validation_response.json()["id"]

    findings_response = client.get(
        f"/api/v1/packages/{package_id}/validation-runs/"
        f"{validation_run_id}/findings",
    )

    assert findings_response.status_code == 200

    findings = findings_response.json()

    assert findings
    finding_id = findings[0]["id"]

    approval_url = (
        f"/api/v1/packages/{package_id}/validation-runs/"
        f"{validation_run_id}/findings/{finding_id}/approval"
    )

    first_response = client.post(
        approval_url,
        json={"approved": True},
    )

    assert first_response.status_code == 200

    second_response = client.post(
        approval_url,
        json={"approved": False},
    )

    assert second_response.status_code == 409
    assert second_response.json()["detail"] == (
        "Finding already has an approval decision"
    )