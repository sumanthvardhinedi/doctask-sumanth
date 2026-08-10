import re

from app.models.enums import FindingResult
from app.validator.types import DocumentInput, PackageInput, RuleDefinition, ValidationFinding


def _pass_finding(rule: RuleDefinition, message: str, **kwargs: object) -> ValidationFinding:
    return ValidationFinding(
        rule_id=rule.rule_id,
        rule_category=rule.category,
        severity=rule.severity,
        result=FindingResult.PASS,
        message=message,
        is_hard_rejection=rule.is_hard_rejection,
        evidence=kwargs.get("evidence"),  # type: ignore[arg-type]
        document_filename=kwargs.get("document_filename"),  # type: ignore[arg-type]
        location=kwargs.get("location"),  # type: ignore[arg-type]
    )


def _fail_finding(rule: RuleDefinition, message: str, **kwargs: object) -> ValidationFinding:
    return ValidationFinding(
        rule_id=rule.rule_id,
        rule_category=rule.category,
        severity=rule.severity,
        result=FindingResult.FAIL,
        message=message,
        is_hard_rejection=rule.is_hard_rejection,
        evidence=kwargs.get("evidence"),  # type: ignore[arg-type]
        document_filename=kwargs.get("document_filename"),  # type: ignore[arg-type]
        location=kwargs.get("location"),  # type: ignore[arg-type]
    )


def _insufficient_evidence_finding(rule: RuleDefinition, message: str, **kwargs: object) -> ValidationFinding:
    return ValidationFinding(
        rule_id=rule.rule_id,
        rule_category=rule.category,
        severity=rule.severity,
        result=FindingResult.INSUFFICIENT_EVIDENCE,
        message=message,
        is_hard_rejection=rule.is_hard_rejection,
        evidence=kwargs.get("evidence"),  # type: ignore[arg-type]
        document_filename=kwargs.get("document_filename"),  # type: ignore[arg-type]
        location=kwargs.get("location"),  # type: ignore[arg-type]
    )


def _evaluate_required_document(
    package: PackageInput, rule: RuleDefinition
) -> ValidationFinding:
    filename = str(rule.parameters["filename"])
    present = any(document.filename == filename for document in package.documents)
    if present:
        return _pass_finding(
            rule,
            f"Required document '{filename}' is present.",
            document_filename=filename,
            location="package.documents",
        )
    return _fail_finding(
        rule,
        f"Required document '{filename}' is missing.",
        evidence=f"Observed filenames: {[doc.filename for doc in package.documents]}",
        location="package.documents",
    )


def _evaluate_filename_pattern(
    package: PackageInput, rule: RuleDefinition
) -> list[ValidationFinding]:
    pattern = re.compile(str(rule.parameters["pattern"]))
    findings: list[ValidationFinding] = []
    for document in package.documents:
        if pattern.fullmatch(document.filename):
            findings.append(
                _pass_finding(
                    rule,
                    f"Filename '{document.filename}' matches the required pattern.",
                    document_filename=document.filename,
                    location=f"document:{document.filename}",
                )
            )
        else:
            findings.append(
                _fail_finding(
                    rule,
                    f"Filename '{document.filename}' does not match the required pattern.",
                    evidence=f"Expected pattern: {pattern.pattern}",
                    document_filename=document.filename,
                    location=f"document:{document.filename}",
                )
            )
    return findings


def _evaluate_document_order(
    package: PackageInput, rule: RuleDefinition
) -> ValidationFinding:
    expected_order = list(rule.parameters["order"])
    actual_order = [document.filename for document in sorted(package.documents, key=lambda d: d.sort_order)]
    if actual_order == expected_order:
        return _pass_finding(
            rule,
            "Document order matches the published filing order.",
            evidence=f"Observed order: {actual_order}",
            location="package.documents",
        )
    return _fail_finding(
        rule,
        "Document order does not match the published filing order.",
        evidence=f"Expected {expected_order}, observed {actual_order}",
        location="package.documents",
    )


def _evaluate_allowed_content_types(
    package: PackageInput, rule: RuleDefinition
) -> list[ValidationFinding]:
    allowed = set(rule.parameters["content_types"])
    findings: list[ValidationFinding] = []
    for document in package.documents:
        if document.content_type in allowed:
            findings.append(
                _pass_finding(
                    rule,
                    f"Content type '{document.content_type}' is allowed.",
                    document_filename=document.filename,
                    location=f"document:{document.filename}",
                )
            )
        else:
            findings.append(
                _fail_finding(
                    rule,
                    f"Content type '{document.content_type}' is not allowed.",
                    evidence=f"Allowed content types: {sorted(allowed)}",
                    document_filename=document.filename,
                    location=f"document:{document.filename}",
                )
            )
    return findings


def _evaluate_max_file_size(
    package: PackageInput, rule: RuleDefinition
) -> list[ValidationFinding]:
    max_bytes = int(rule.parameters["max_bytes"])
    findings: list[ValidationFinding] = []
    for document in package.documents:
        if document.file_size_bytes is None:
            findings.append(
                _insufficient_evidence_finding(
                    rule,
                    f"File size is unknown for '{document.filename}'.",
                    evidence="file_size_bytes was not provided",
                    document_filename=document.filename,
                    location=f"document:{document.filename}",
                )
            )
        elif document.file_size_bytes <= max_bytes:
            findings.append(
                _pass_finding(
                    rule,
                    f"File '{document.filename}' is within the size limit.",
                    evidence=f"size_bytes={document.file_size_bytes}",
                    document_filename=document.filename,
                    location=f"document:{document.filename}",
                )
            )
        else:
            findings.append(
                _fail_finding(
                    rule,
                    f"File '{document.filename}' exceeds the maximum allowed size.",
                    evidence=f"size_bytes={document.file_size_bytes}, max_bytes={max_bytes}",
                    document_filename=document.filename,
                    location=f"document:{document.filename}",
                )
            )
    return findings


def _evaluate_requires_signature(
    package: PackageInput, rule: RuleDefinition
) -> ValidationFinding:
    filename = str(rule.parameters["filename"])
    document = next((doc for doc in package.documents if doc.filename == filename), None)
    if document is None:
        return _fail_finding(
            rule,
            f"Cannot verify signature because '{filename}' is missing.",
            evidence="Document not present in package",
            location=f"document:{filename}",
        )
    if document.has_signature is None:
        return _insufficient_evidence_finding(
            rule,
            f"Signature status is unknown for '{filename}'.",
            evidence="has_signature was not provided",
            document_filename=filename,
            location=f"document:{filename}",
        )
    if document.has_signature:
        return _pass_finding(
            rule,
            f"Signature requirement satisfied for '{filename}'.",
            document_filename=filename,
            location=f"document:{filename}",
        )
    return _fail_finding(
        rule,
        f"Signature requirement not satisfied for '{filename}'.",
        evidence="has_signature=false",
        document_filename=filename,
        location=f"document:{filename}",
    )


def _evaluate_requires_declaration(
    package: PackageInput, rule: RuleDefinition
) -> ValidationFinding:
    filename = str(rule.parameters["filename"])
    document = next((doc for doc in package.documents if doc.filename == filename), None)
    if document is None:
        return _fail_finding(
            rule,
            f"Cannot verify declaration because '{filename}' is missing.",
            evidence="Document not present in package",
            location=f"document:{filename}",
        )
    if document.declaration_present is None:
        return _insufficient_evidence_finding(
            rule,
            f"Declaration status is unknown for '{filename}'.",
            evidence="declaration_present was not provided",
            document_filename=filename,
            location=f"document:{filename}",
        )
    if document.declaration_present:
        return _pass_finding(
            rule,
            f"Declaration requirement satisfied for '{filename}'.",
            document_filename=filename,
            location=f"document:{filename}",
        )
    return _fail_finding(
        rule,
        f"Declaration requirement not satisfied for '{filename}'.",
        evidence="declaration_present=false",
        document_filename=filename,
        location=f"document:{filename}",
    )


_RULE_EVALUATORS = {
    "required_document": lambda package, rule: [_evaluate_required_document(package, rule)],
    "filename_pattern": _evaluate_filename_pattern,
    "document_order": lambda package, rule: [_evaluate_document_order(package, rule)],
    "allowed_content_types": _evaluate_allowed_content_types,
    "max_file_size": _evaluate_max_file_size,
    "requires_signature": lambda package, rule: [_evaluate_requires_signature(package, rule)],
    "requires_declaration": lambda package, rule: [_evaluate_requires_declaration(package, rule)],
}


def evaluate_rule(package: PackageInput, rule: RuleDefinition) -> list[ValidationFinding]:
    evaluator = _RULE_EVALUATORS.get(rule.rule_type)
    if evaluator is None:
        return [
            _insufficient_evidence_finding(
                rule,
                f"Unsupported rule type '{rule.rule_type}'.",
                evidence="No deterministic evaluator is registered for this rule type",
                location="rule.type",
            )
        ]
    return evaluator(package, rule)


def validate_package(
    package: PackageInput, rules: tuple[RuleDefinition, ...]
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    for rule in rules:
        findings.extend(evaluate_rule(package, rule))
    return findings

