from app.models.regulatory_rule import IndexedRule
from app.validator.types import RuleDefinition


def indexed_rule_to_definition(rule: IndexedRule) -> RuleDefinition:
    """Convert a persisted indexed rule into a validator rule definition."""

    required_fields = {
        "rule_id": rule.rule_id,
        "category": rule.category,
        "description": rule.description,
        "severity": rule.severity,
        "rule_type": rule.rule_type,
        "parameters": rule.parameters,
    }

    missing_fields = [
        field
        for field, value in required_fields.items()
        if value is None
    ]

    if missing_fields:
        raise ValueError(
            "Indexed rule is missing required fields: "
            + ", ".join(missing_fields)
        )

    return RuleDefinition(
        rule_id=rule.rule_id,
        category=rule.category,
        description=rule.description,
        severity=rule.severity,
        is_hard_rejection=rule.is_hard_rejection,
        rule_type=rule.rule_type,
        parameters=dict(rule.parameters),
    )