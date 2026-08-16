from app.models.enums import FindingResult

ROUTE_CONTINUE = "continue"
ROUTE_FINDING = "finding"
ROUTE_HUMAN_ESCALATION = "human_escalation"
ROUTE_HUMAN_REVIEW = "human_review"
ROUTE_FAILED = "failed"

_EVIDENCE_FIELDS = {
    "requires_signature": "signature",
    "requires_declaration": "declaration",
}


def detect_conflicts(
    *,
    rules: list[dict[str, object]],
    interpretations: list[dict[str, object]],
    extracted_documents: list[dict[str, object]],
    findings: list[dict[str, object]],
) -> dict[str, object]:
    """Detect requirement vs extraction vs finding mismatches. Do not invent conflicts."""

    interpretation_by_rule = {
        item.get("rule_id"): item for item in interpretations if item.get("rule_id")
    }
    finding_by_rule = {
        item.get("rule_id"): item for item in findings if item.get("rule_id")
    }
    documents_by_filename = {
        str(item.get("filename") or ""): item
        for item in extracted_documents
        if item.get("filename")
    }

    conflicts: list[dict[str, object]] = []
    routes: list[dict[str, object]] = []

    for rule in rules:
        rule_id = rule.get("rule_id")
        if not rule_id:
            continue
        finding = finding_by_rule.get(rule_id) or {}
        finding_result = finding.get("result")
        interpretation = interpretation_by_rule.get(rule_id) or {}
        conflict = _requirement_extraction_conflict(
            rule=rule,
            interpretation=interpretation,
            finding_result=finding_result,
            documents_by_filename=documents_by_filename,
        )
        if conflict is not None:
            conflicts.append(conflict)
            routes.append(
                {
                    "rule_id": rule_id,
                    "finding_result": finding_result,
                    "route": ROUTE_HUMAN_REVIEW,
                }
            )
            continue

        routes.append(
            {
                "rule_id": rule_id,
                "finding_result": finding_result,
                "route": _route_for_finding(finding_result),
            }
        )

    requires_human_review = any(
        item["route"] in {ROUTE_HUMAN_REVIEW, ROUTE_HUMAN_ESCALATION}
        or item["finding_result"]
        in {FindingResult.FAIL, FindingResult.INSUFFICIENT_EVIDENCE}
        for item in routes
    )

    return {
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "routes": routes,
        "requires_human_review": requires_human_review,
    }


def _route_for_finding(finding_result: object) -> str:
    if finding_result == FindingResult.PASS:
        return ROUTE_CONTINUE
    if finding_result == FindingResult.FAIL:
        return ROUTE_FINDING
    if finding_result == FindingResult.INSUFFICIENT_EVIDENCE:
        return ROUTE_HUMAN_ESCALATION
    if finding_result is None:
        return ROUTE_FAILED
    return ROUTE_CONTINUE


def _requirement_extraction_conflict(
    *,
    rule: dict[str, object],
    interpretation: dict[str, object],
    finding_result: object,
    documents_by_filename: dict[str, dict[str, object]],
) -> dict[str, object] | None:
    evidence_field = _EVIDENCE_FIELDS.get(str(rule.get("rule_type") or ""))
    if evidence_field is None:
        return None

    parameters = dict(rule.get("parameters") or {})
    filename = str(parameters.get("filename") or "")
    extracted = documents_by_filename.get(filename)
    extracted_field = (extracted or {}).get(evidence_field)
    extract_result = (
        extracted_field.get("result") if isinstance(extracted_field, dict) else None
    )

    interpretation_ok = interpretation.get("result") == "interpreted"
    extract_unobserved = (
        extracted is None
        or extract_result == FindingResult.INSUFFICIENT_EVIDENCE
    )
    finding_pass_without_evidence = (
        finding_result == FindingResult.PASS and extract_unobserved
    )
    requirement_without_evidence = (
        interpretation_ok
        and extract_unobserved
        and finding_result == FindingResult.INSUFFICIENT_EVIDENCE
    )

    if not finding_pass_without_evidence and not requirement_without_evidence:
        return None

    return {
        "rule_id": rule.get("rule_id"),
        "rule_type": rule.get("rule_type"),
        "filename": filename or None,
        "kind": "requirement_vs_extraction",
        "interpretation_result": interpretation.get("result"),
        "extraction_result": extract_result,
        "finding_result": finding_result,
        "evidence": (
            "Published rule requires evidence that extraction did not observe"
        ),
    }
