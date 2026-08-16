from app.models.enums import FindingResult


def interpret_rules(
    *,
    authority_code: str,
    rules: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Restate published rule text and parameters. Never invent extra requirements."""

    interpretations: list[dict[str, object]] = []
    for rule in rules:
        description = rule.get("description")
        parameters = dict(rule.get("parameters") or {})
        source_citation = rule.get("source_citation")
        rule_id = rule.get("rule_id")

        if not description:
            interpretations.append(
                {
                    "rule_id": rule_id,
                    "authority": authority_code,
                    "rule_text": None,
                    "source_citation": source_citation,
                    "parameters": parameters,
                    "interpretation": None,
                    "result": FindingResult.INSUFFICIENT_EVIDENCE,
                    "evidence": "Published rule is missing description text",
                }
            )
            continue

        interpretations.append(
            {
                "rule_id": rule_id,
                "authority": authority_code,
                "rule_text": description,
                "source_citation": source_citation,
                "parameters": parameters,
                "interpretation": description,
                "result": "interpreted",
                "evidence": (
                    "Interpretation is the published description and parameters only"
                ),
            }
        )

    return interpretations
