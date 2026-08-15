from app.models.enums import FindingResult
from app.services.rule_indexer import load_raw_authority_config


def _required_document_roles(authority_code: str) -> dict[str, dict[str, str]]:
    """Map exact filenames from published required_document rules to roles."""

    config = load_raw_authority_config(authority_code)
    raw_rules = config.get("rules", [])
    if not isinstance(raw_rules, list):
        raise ValueError(f"Invalid rules list in authority config: {authority_code}")

    roles: dict[str, dict[str, str]] = {}
    for raw_rule in raw_rules:
        if raw_rule.get("rule_type") != "required_document":
            continue
        parameters = raw_rule.get("parameters") or {}
        filename = parameters.get("filename")
        if not filename:
            continue
        roles[str(filename)] = {
            "role": str(raw_rule.get("rule_id")),
            "rule_id": str(raw_rule.get("rule_id")),
        }
    return roles


def classify_documents(
    *,
    authority_code: str,
    documents: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Classify documents from filename metadata only. Never reads file bytes."""

    roles = _required_document_roles(authority_code)
    classifications: list[dict[str, object]] = []

    for document in documents:
        filename = str(document.get("filename") or "")
        matched = roles.get(filename)
        if matched is None:
            classifications.append(
                {
                    "document_id": document.get("id"),
                    "filename": filename,
                    "result": FindingResult.INSUFFICIENT_EVIDENCE,
                    "role": None,
                    "rule_id": None,
                    "evidence": (
                        "Filename does not exactly match a published "
                        "required_document rule for this authority"
                    ),
                }
            )
            continue

        classifications.append(
            {
                "document_id": document.get("id"),
                "filename": filename,
                "result": "classified",
                "role": matched["role"],
                "rule_id": matched["rule_id"],
                "evidence": f"Exact filename match for required document '{filename}'",
            }
        )

    return classifications
