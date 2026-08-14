from sqlalchemy.orm import Session

from app.services.regulatory_rule_adapter import indexed_rule_to_definition
from app.services.rule_indexer import load_raw_authority_config
from app.services.rule_retrieval import retrieve_rules
from app.validator.types import RuleDefinition


def get_indexed_rule_definitions(
    db: Session,
    authority_code: str,
) -> tuple[RuleDefinition, ...]:
    """Load persisted regulatory rules for a known authority."""

    # Validate that the authority is actually configured.
    # retrieve_rules() intentionally returns an empty list when
    # no indexed records exist, so authority validation belongs here.
    load_raw_authority_config(authority_code)

    indexed_rules = retrieve_rules(
        db,
        authority_code,
    )

    return tuple(
        indexed_rule_to_definition(rule)
        for rule in indexed_rules
    )