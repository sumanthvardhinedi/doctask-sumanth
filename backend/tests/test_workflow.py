import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy.orm import Session

from app.db.database import Base, engine, ensure_extensions
from app.models import (
    FilingPackage,
    Finding,
    PackageDocument,
    PackageStatus,
    ValidationRun,
    ValidationRunStatus,
)
from app.workflow.validation_workflow import run_validation


@pytest.fixture()
def db() -> Session:
    ensure_extensions()
    Base.metadata.create_all(bind=engine)

    try:
        with Session(engine) as session:
            yield session
    finally:
        Base.metadata.drop_all(bind=engine)


def _create_package(
    db: Session,
    *,
    authority_code: str = "authority_a",
    with_document: bool = False,
) -> FilingPackage:
    package = FilingPackage(
        id=uuid.uuid4(),
        authority_code=authority_code,
        name="Workflow test package",
        status=PackageStatus.PENDING,
    )

    db.add(package)
    db.flush()

    if with_document:
        document = PackageDocument(
            id=uuid.uuid4(),
            package_id=package.id,
            filename="cover_letter.pdf",
            content_type="application/pdf",
            file_size_bytes=1024,
            storage_path="test/cover_letter.pdf",
            sort_order=1,
        )

        db.add(document)
        db.flush()

    return package


def test_validation_workflow_persists_run_and_findings(
    db: Session,
) -> None:
    package = _create_package(db, with_document=False)

    run = run_validation(db, package.id)

    assert run.status == ValidationRunStatus.COMPLETED
    assert run.current_stage == "completed"
    assert run.completed_at is not None

    stored_package = db.get(FilingPackage, package.id)

    assert stored_package is not None
    assert stored_package.status == PackageStatus.AWAITING_APPROVAL

    findings = (
        db.query(Finding)
        .filter(Finding.validation_run_id == run.id)
        .all()
    )

    assert findings
    assert any(finding.result == "fail" for finding in findings)


def test_validation_workflow_uses_existing_documents(
    db: Session,
) -> None:
    package = _create_package(db, with_document=True)

    run = run_validation(db, package.id)

    assert run.status == ValidationRunStatus.COMPLETED

    findings = (
        db.query(Finding)
        .filter(Finding.validation_run_id == run.id)
        .all()
    )

    assert findings

    assert any(
        finding.package_document_id is not None
        for finding in findings
    )


def test_validation_workflow_missing_package_fails(
    db: Session,
) -> None:
    missing_id = uuid.uuid4()

    with pytest.raises(ValueError, match="not found"):
        run_validation(db, missing_id)


def test_validation_workflow_unknown_authority_marks_run_failed(
    db: Session,
) -> None:
    package = _create_package(
        db,
        authority_code="unknown_authority",
    )

    package_id = package.id

    with pytest.raises(ValueError):
        run_validation(db, package_id)

    failed_run = (
        db.query(ValidationRun)
        .filter(ValidationRun.package_id == package_id)
        .order_by(ValidationRun.created_at.desc())
        .first()
    )

    assert failed_run is not None
    assert failed_run.status == ValidationRunStatus.FAILED

    failed_package = db.get(FilingPackage, package_id)

    assert failed_package is not None
    assert failed_package.status == PackageStatus.FAILED
