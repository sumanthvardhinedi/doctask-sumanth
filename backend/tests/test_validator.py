import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import uuid

from app.models.enums import FindingResult
from app.validator import (
    DocumentInput,
    PackageInput,
    get_rules_for_authority,
    map_findings_to_models,
    validate_package,
)


def _authority_a_valid_package() -> PackageInput:
    return PackageInput(
        authority_code="authority_a",
        name="Valid Authority A package",
        documents=(
            DocumentInput(
                filename="cover_letter.pdf",
                content_type="application/pdf",
                file_size_bytes=1024,
                sort_order=1,
                has_signature=True,
                declaration_present=True,
            ),
            DocumentInput(
                filename="appendix_a.pdf",
                content_type="application/pdf",
                file_size_bytes=2048,
                sort_order=2,
            ),
        ),
    )


def test_authority_a_valid_package_passes_all_rules() -> None:
    findings = validate_package(_authority_a_valid_package(), get_rules_for_authority("authority_a"))
    assert findings
    assert all(finding.result == FindingResult.PASS for finding in findings)


def test_missing_required_document_fails() -> None:
    package = PackageInput(
        authority_code="authority_a",
        name="Missing appendix",
        documents=(
            DocumentInput(
                filename="cover_letter.pdf",
                content_type="application/pdf",
                file_size_bytes=1024,
                sort_order=1,
                has_signature=True,
                declaration_present=True,
            ),
        ),
    )
    findings = validate_package(package, get_rules_for_authority("authority_a"))
    failed = [finding for finding in findings if finding.result == FindingResult.FAIL]
    assert any(finding.rule_id == "mandatory.appendix_a" for finding in failed)


def test_invalid_filename_pattern_fails() -> None:
    package = PackageInput(
        authority_code="authority_a",
        name="Bad filename",
        documents=(
            DocumentInput(
                filename="Cover-Letter.pdf",
                content_type="application/pdf",
                file_size_bytes=1024,
                sort_order=1,
                has_signature=True,
                declaration_present=True,
            ),
            DocumentInput(
                filename="appendix_a.pdf",
                content_type="application/pdf",
                file_size_bytes=2048,
                sort_order=2,
            ),
        ),
    )
    findings = validate_package(package, get_rules_for_authority("authority_a"))
    failed = [finding for finding in findings if finding.rule_id == "naming.lowercase_underscore"]
    assert failed
    assert failed[0].result == FindingResult.FAIL


def test_wrong_document_order_fails() -> None:
    package = PackageInput(
        authority_code="authority_a",
        name="Wrong order",
        documents=(
            DocumentInput(
                filename="appendix_a.pdf",
                content_type="application/pdf",
                file_size_bytes=2048,
                sort_order=1,
            ),
            DocumentInput(
                filename="cover_letter.pdf",
                content_type="application/pdf",
                file_size_bytes=1024,
                sort_order=2,
                has_signature=True,
                declaration_present=True,
            ),
        ),
    )
    findings = validate_package(package, get_rules_for_authority("authority_a"))
    order_findings = [finding for finding in findings if finding.rule_id == "ordering.standard"]
    assert order_findings
    assert order_findings[0].result == FindingResult.FAIL


def test_invalid_content_type_fails() -> None:
    package = PackageInput(
        authority_code="authority_a",
        name="Wrong format",
        documents=(
            DocumentInput(
                filename="cover_letter.pdf",
                content_type="text/plain",
                file_size_bytes=1024,
                sort_order=1,
                has_signature=True,
                declaration_present=True,
            ),
            DocumentInput(
                filename="appendix_a.pdf",
                content_type="application/pdf",
                file_size_bytes=2048,
                sort_order=2,
            ),
        ),
    )
    findings = validate_package(package, get_rules_for_authority("authority_a"))
    failed = [finding for finding in findings if finding.rule_id == "format.pdf_only"]
    assert any(finding.result == FindingResult.FAIL for finding in failed)


def test_oversized_file_fails() -> None:
    package = PackageInput(
        authority_code="authority_a",
        name="Oversized file",
        documents=(
            DocumentInput(
                filename="cover_letter.pdf",
                content_type="application/pdf",
                file_size_bytes=20_000_000,
                sort_order=1,
                has_signature=True,
                declaration_present=True,
            ),
            DocumentInput(
                filename="appendix_a.pdf",
                content_type="application/pdf",
                file_size_bytes=2048,
                sort_order=2,
            ),
        ),
    )
    findings = validate_package(package, get_rules_for_authority("authority_a"))
    failed = [finding for finding in findings if finding.rule_id == "size.max_ten_mb"]
    assert any(finding.result == FindingResult.FAIL for finding in failed)


def test_missing_signature_metadata_reports_insufficient_evidence() -> None:
    package = PackageInput(
        authority_code="authority_a",
        name="Unknown signature",
        documents=(
            DocumentInput(
                filename="cover_letter.pdf",
                content_type="application/pdf",
                file_size_bytes=1024,
                sort_order=1,
                declaration_present=True,
            ),
            DocumentInput(
                filename="appendix_a.pdf",
                content_type="application/pdf",
                file_size_bytes=2048,
                sort_order=2,
            ),
        ),
    )
    findings = validate_package(package, get_rules_for_authority("authority_a"))
    signature_findings = [finding for finding in findings if finding.rule_id == "signature.cover_letter"]
    assert signature_findings
    assert signature_findings[0].result == FindingResult.INSUFFICIENT_EVIDENCE


def test_empty_package_fails_mandatory_rules() -> None:
    package = PackageInput(
        authority_code="authority_a",
        name="Empty package",
        documents=(),
    )
    findings = validate_package(package, get_rules_for_authority("authority_a"))
    failed = [finding for finding in findings if finding.result == FindingResult.FAIL]
    assert any(finding.rule_id == "mandatory.cover_letter" for finding in failed)
    assert any(finding.rule_id == "mandatory.appendix_a" for finding in failed)


def test_validation_is_deterministic() -> None:
    package = _authority_a_valid_package()
    rules = get_rules_for_authority("authority_a")
    first = validate_package(package, rules)
    second = validate_package(package, rules)
    assert first == second


def test_authority_b_uses_different_rules_without_code_branching() -> None:
    package = PackageInput(
        authority_code="authority_b",
        name="Valid Authority B package",
        documents=(
            DocumentInput(
                filename="ES_executive_summary.pdf",
                content_type="application/pdf",
                file_size_bytes=1024,
                sort_order=1,
                has_signature=True,
            ),
            DocumentInput(
                filename="TS_technical_schedule.pdf",
                content_type="application/pdf",
                file_size_bytes=2048,
                sort_order=2,
            ),
        ),
    )
    findings = validate_package(package, get_rules_for_authority("authority_b"))
    assert all(finding.result == FindingResult.PASS for finding in findings)
    assert not any(finding.rule_id == "mandatory.cover_letter" for finding in findings)


def test_unknown_authority_raises_clear_error() -> None:
    try:
        get_rules_for_authority("unknown_authority")
    except ValueError as exc:
        assert "Unknown authority code" in str(exc)
    else:
        raise AssertionError("Expected ValueError for unknown authority")


def test_map_findings_to_models_is_separate_from_evaluation() -> None:
    package = _authority_a_valid_package()
    findings = validate_package(package, get_rules_for_authority("authority_a"))
    run_id = uuid.uuid4()
    document_ids = {
        "cover_letter.pdf": uuid.uuid4(),
        "appendix_a.pdf": uuid.uuid4(),
    }
    orm_findings = map_findings_to_models(findings, run_id, document_ids)
    assert len(orm_findings) == len(findings)
    assert all(finding.validation_run_id == run_id for finding in orm_findings)
    assert all(finding.explanation for finding in orm_findings)
