import uuid

from app.models.finding import Finding
from app.validator.types import ValidationFinding


def map_findings_to_models(
    findings: list[ValidationFinding],
    validation_run_id: uuid.UUID,
    documents_by_filename: dict[str, uuid.UUID],
) -> list[Finding]:
    orm_findings: list[Finding] = []
    for finding in findings:
        document_id = None
        if finding.document_filename is not None:
            document_id = documents_by_filename.get(finding.document_filename)
        orm_findings.append(
            Finding(
                validation_run_id=validation_run_id,
                package_document_id=document_id,
                rule_id=finding.rule_id,
                rule_category=finding.rule_category,
                severity=finding.severity,
                result=finding.result,
                location=finding.location,
                evidence=finding.evidence,
                explanation=finding.message,
                is_hard_rejection=finding.is_hard_rejection,
            )
        )
    return orm_findings
