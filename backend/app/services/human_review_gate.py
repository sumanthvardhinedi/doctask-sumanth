from app.models.enums import FindingResult
from app.models.finding import Finding

_REVIEWABLE_RESULTS = {
    FindingResult.FAIL,
    FindingResult.INSUFFICIENT_EVIDENCE,
}


def finding_gate_item(finding: Finding) -> dict[str, object]:
    decision = finding.approval_decision
    return {
        "finding_id": str(finding.id),
        "rule_id": finding.rule_id,
        "result": finding.result,
        "approved": None if decision is None else decision.approved,
    }


def evaluate_human_review_gate(
    *,
    findings: list[dict[str, object]],
    conflict_rule_ids: list[str] | None = None,
) -> dict[str, object]:
    """Per-item gate: reject one finding without deciding unrelated findings."""

    conflict_ids = {rule_id for rule_id in (conflict_rule_ids or []) if rule_id}
    pending: list[dict[str, object]] = []
    decided: list[dict[str, object]] = []

    for item in findings:
        if not _is_reviewable(item, conflict_ids):
            continue
        if item.get("approved") is None:
            pending.append(item)
        else:
            decided.append(item)

    approved_ids = [
        str(item["finding_id"])
        for item in decided
        if item.get("approved") is True
    ]
    rejected_ids = [
        str(item["finding_id"])
        for item in decided
        if item.get("approved") is False
    ]

    return {
        "pending_count": len(pending),
        "decided_count": len(decided),
        "pending_finding_ids": [str(item["finding_id"]) for item in pending],
        "decided_finding_ids": [str(item["finding_id"]) for item in decided],
        "approved_finding_ids": approved_ids,
        "rejected_finding_ids": rejected_ids,
        "items": pending + decided,
        "gate_satisfied": len(pending) == 0,
    }


def _is_reviewable(
    item: dict[str, object],
    conflict_rule_ids: set[str],
) -> bool:
    result = item.get("result")
    rule_id = item.get("rule_id")
    if result in _REVIEWABLE_RESULTS:
        return True
    return bool(rule_id) and str(rule_id) in conflict_rule_ids
