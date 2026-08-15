from app.models.enums import FindingResult


_UNOBSERVED = {
    "result": FindingResult.INSUFFICIENT_EVIDENCE,
    "value": None,
    "evidence": "Not present on persisted document metadata; file bytes were not read",
}


def extract_structure(
    *,
    documents: list[dict[str, object]],
) -> dict[str, object]:
    """Extract structure from persisted metadata only. Never reads file bytes."""

    ordered = sorted(
        documents,
        key=lambda item: int(item.get("sort_order") or 0),
    )
    observed_order = [str(item.get("filename") or "") for item in ordered]

    extracted_documents: list[dict[str, object]] = []
    for item in ordered:
        filename = str(item.get("filename") or "")
        identity_result = (
            FindingResult.INSUFFICIENT_EVIDENCE if filename == "" else "observed"
        )
        extracted_documents.append(
            {
                "document_id": item.get("id"),
                "filename": filename or None,
                "identity": {
                    "result": identity_result,
                    "evidence": (
                        "Filename is missing from persisted metadata"
                        if filename == ""
                        else "Filename taken from persisted PackageDocument metadata"
                    ),
                },
                "content_type": item.get("content_type"),
                "file_size_bytes": item.get("file_size_bytes"),
                "sort_order": item.get("sort_order"),
                "signature": dict(_UNOBSERVED),
                "declaration": dict(_UNOBSERVED),
                "dates": dict(_UNOBSERVED),
                "sections": dict(_UNOBSERVED),
            }
        )

    return {
        "document_count": len(extracted_documents),
        "observed_order": observed_order,
        "documents": extracted_documents,
        "ordering": {
            "result": "observed" if extracted_documents else "observed",
            "evidence": "Document order taken from persisted sort_order",
        },
    }
