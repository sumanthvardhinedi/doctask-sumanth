from sqlalchemy.orm import Session

from app.models.regulatory_rule import IndexedRule
from app.services.rule_retrieval import retrieve_rules


def retrieve_rule_context(
    db: Session,
    authority_code: str,
    *,
    classified_rule_ids: list[str] | None = None,
) -> dict[str, object]:
    """Retrieve published rules with deterministic metadata lookup. No embeddings."""

    indexed_rules = retrieve_rules(db, authority_code)
    records = [
        _rule_record(rule)
        for rule in indexed_rules
    ]
    classified = set(classified_rule_ids or [])
    focused_rule_ids = [
        record["rule_id"]
        for record in records
        if record["rule_id"] in classified
    ]

    return {
        "authority_code": authority_code,
        "retrieval_method": "deterministic_metadata",
        "rule_count": len(records),
        "rule_ids": [record["rule_id"] for record in records],
        "focused_rule_ids": focused_rule_ids,
        "rules": records,
    }


def _rule_record(rule: IndexedRule) -> dict[str, object]:
    return {
        "rule_id": rule.rule_id,
        "category": rule.category,
        "rule_type": rule.rule_type,
        "description": rule.description,
        "source_citation": rule.source_citation,
        "parameters": dict(rule.parameters or {}),
    }
