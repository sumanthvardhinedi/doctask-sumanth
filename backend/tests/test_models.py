import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.database import Base, engine, ensure_extensions
from app.models import (
    ApprovalDecision,
    FilingPackage,
    Finding,
    FindingResult,
    FindingSeverity,
    PackageDocument,
    PackageStatus,
    ValidationRun,
    ValidationRunStatus,
)


@pytest.fixture(scope="module")
def db_tables() -> None:
    try:
        ensure_extensions()
        Base.metadata.create_all(bind=engine)
    except OperationalError as exc:
        pytest.fail(
            f"Could not create model tables at {settings.database_url}. "
            "Is Docker PostgreSQL running? Start with: docker compose up -d\n"
            f"Original error: {exc}"
        )
    yield
    Base.metadata.drop_all(bind=engine)


def test_regulatory_domain_models_persist_and_relate(db_tables: None) -> None:
    package_id = uuid.uuid4()
    document_id = uuid.uuid4()
    run_id = uuid.uuid4()
    finding_id = uuid.uuid4()
    decision_id = uuid.uuid4()

    with Session(engine) as session:
        package = FilingPackage(
            id=package_id,
            authority_code="authority_a",
            name="Synthetic filing package",
            status=PackageStatus.PENDING,
        )
        document = PackageDocument(
            id=document_id,
            package_id=package_id,
            filename="cover_letter.pdf",
            content_type="application/pdf",
            file_size_bytes=1024,
            storage_path="uploads/cover_letter.pdf",
            sort_order=1,
        )
        validation_run = ValidationRun(
            id=run_id,
            package_id=package_id,
            authority_code="authority_a",
            status=ValidationRunStatus.RUNNING,
            current_stage="validate_package",
        )
        finding = Finding(
            id=finding_id,
            validation_run_id=run_id,
            package_document_id=document_id,
            rule_id="mandatory.cover_letter",
            rule_category="mandatory_sections",
            severity=FindingSeverity.ERROR,
            result=FindingResult.FAIL,
            location="package.documents[0]",
            evidence="cover_letter.pdf missing required signature block",
            explanation="Authority A requires a signed cover letter.",
            is_hard_rejection=True,
        )
        decision = ApprovalDecision(
            id=decision_id,
            finding_id=finding_id,
            approved=False,
            reviewer_notes="Reject until signature is added.",
        )

        session.add_all([package, document, validation_run, finding, decision])
        session.commit()

        stored_package = session.get(FilingPackage, package_id)
        assert stored_package is not None
        assert stored_package.authority_code == "authority_a"
        assert len(stored_package.documents) == 1
        assert stored_package.documents[0].filename == "cover_letter.pdf"
        assert len(stored_package.validation_runs) == 1
        assert stored_package.validation_runs[0].current_stage == "validate_package"

        stored_finding = session.get(Finding, finding_id)
        assert stored_finding is not None
        assert stored_finding.rule_id == "mandatory.cover_letter"
        assert stored_finding.is_hard_rejection is True
        assert stored_finding.approval_decision is not None
        assert stored_finding.approval_decision.approved is False
