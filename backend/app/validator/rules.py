import json
from pathlib import Path

from app.validator.types import RuleDefinition


AUTHORITIES_DIR = (
    Path(__file__).resolve().parents[2] / "config" / "authorities"
)


def _load_authority_rules(authority_code: str) -> tuple[RuleDefinition, ...]:
    config_path = AUTHORITIES_DIR / f"{authority_code}.json"

    if not config_path.exists():
        raise ValueError(f"Unknown authority code: {authority_code}")

    try:
        with config_path.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid authority configuration: {authority_code}"
        ) from exc

    if config.get("authority_code") != authority_code:
        raise ValueError(
            f"Authority configuration mismatch: {authority_code}"
        )

    raw_rules = config.get("rules")

    if not isinstance(raw_rules, list):
        raise ValueError(
            f"Invalid rules configuration for authority: {authority_code}"
        )

    rules: list[RuleDefinition] = []

    required_fields = {
        "rule_id",
        "category",
        "description",
        "severity",
        "is_hard_rejection",
        "rule_type",
        "parameters",
    }

    for raw_rule in raw_rules:
        missing_fields = required_fields - raw_rule.keys()

        if missing_fields:
            raise ValueError(
                f"Rule {raw_rule.get('rule_id', '<unknown>')} "
                f"is missing fields: {sorted(missing_fields)}"
            )

        rules.append(
            RuleDefinition(
                rule_id=raw_rule["rule_id"],
                category=raw_rule["category"],
                description=raw_rule["description"],
                severity=raw_rule["severity"],
                is_hard_rejection=raw_rule["is_hard_rejection"],
                rule_type=raw_rule["rule_type"],
                parameters=raw_rule["parameters"],
            )
        )

    return tuple(rules)


def get_rules_for_authority(
    authority_code: str,
) -> tuple[RuleDefinition, ...]:
    return _load_authority_rules(authority_code)