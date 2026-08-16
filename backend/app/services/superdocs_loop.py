from app.models.enums import SuperDocsReviewStatus
from app.models.finding import Finding
from app.models.superdocs_review import SuperDocsReviewSession

_PENDING_DECISION_STATUSES = {
    SuperDocsReviewStatus.CREATING,
    SuperDocsReviewStatus.UPLOADED,
    SuperDocsReviewStatus.PROPOSED,
}

def evaluate_superdocs_loop(
    *,
    findings: list[Finding],
    reviews: list[SuperDocsReviewSession],
) -> dict[str, object]:
    """Route approved document-backed findings through SuperDocs. Do not invent exports."""

    review_by_finding = {str(review.finding_id): review for review in reviews}
    eligible: list[dict[str, object]] = []
    skipped: list[dict[str, object]] = []
    pending_start: list[str] = []
    pending_decision: list[str] = []
    pending_export: list[str] = []
    pending_retry: list[str] = []
    exported: list[str] = []
    rejected: list[str] = []

    for finding in findings:
        decision = finding.approval_decision
        if decision is None or decision.approved is not True:
            skipped.append(
                {
                    "finding_id": str(finding.id),
                    "reason": "not_approved_for_superdocs",
                }
            )
            continue
        if finding.package_document_id is None:
            skipped.append(
                {
                    "finding_id": str(finding.id),
                    "reason": "no_package_document",
                }
            )
            continue

        finding_id = str(finding.id)
        review = review_by_finding.get(finding_id)
        item = {
            "finding_id": finding_id,
            "review_id": str(review.id) if review is not None else None,
            "status": review.status if review is not None else None,
        }
        eligible.append(item)

        if review is None:
            pending_start.append(finding_id)
            continue
        if review.status == SuperDocsReviewStatus.FAILED:
            pending_retry.append(finding_id)
            continue
        if review.status in _PENDING_DECISION_STATUSES:
            pending_decision.append(finding_id)
            continue
        if review.status == SuperDocsReviewStatus.APPROVED:
            pending_export.append(finding_id)
            continue
        if review.status == SuperDocsReviewStatus.EXPORTED:
            exported.append(finding_id)
            continue
        if review.status == SuperDocsReviewStatus.REJECTED:
            rejected.append(finding_id)
            continue
        pending_retry.append(finding_id)

    waiting = bool(pending_start or pending_decision or pending_retry)
    return {
        "eligible_count": len(eligible),
        "skipped": skipped,
        "eligible": eligible,
        "pending_start": pending_start,
        "pending_decision": pending_decision,
        "pending_export": pending_export,
        "pending_retry": pending_retry,
        "exported": exported,
        "rejected": rejected,
        "loop_waiting": waiting,
        "ready_to_finalize": not waiting,
    }


def is_unreadable_document_error(message: str) -> bool:
    lowered = message.lower()
    return "not found" in lowered or "escapes" in lowered or "no associated package document" in lowered
