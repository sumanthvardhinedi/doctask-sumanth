import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.regulatory_rule import IndexedRule

AUTHORITIES_DIR = (
    Path(__file__).resolve().parents[2] / "config" / "authorities"
)


def load_raw_authority_config(authority_code: str) -> dict:
    config_path = AUTHORITIES_DIR / f"{authority_code}.json"
    if not config_path.exists():
        raise ValueError(f"Unknown authority code: {authority_code}")

    try:
        with config_path.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid authority configuration JSON: {authority_code}") from exc

    if config.get("authority_code") != authority_code:
        raise ValueError(f"Authority configuration mismatch for: {authority_code}")

    return config


def index_authority_rules(authority_code: str, db: Session) -> list[IndexedRule]:
    config = load_raw_authority_config(authority_code)
    raw_rules = config.get("rules", [])

    if not isinstance(raw_rules, list):
        raise ValueError(f"Invalid rules list in authority config: {authority_code}")

    indexed_records: list[IndexedRule] = []

    for raw_rule in raw_rules:
        rule_id = raw_rule["rule_id"]
        category = raw_rule["category"]
        description = raw_rule.get("description")
        severity = raw_rule["severity"]
        is_hard_rejection = raw_rule.get("is_hard_rejection", True)
        rule_type = raw_rule["rule_type"]
        parameters = raw_rule.get("parameters", {})
        source_citation = raw_rule.get("source_citation")
        if not source_citation:
            raise ValueError(
        f"Missing source_citation for rule {rule_id} "
        f"in authority {authority_code}"
    )
        effective_date = raw_rule.get("effective_date")
        keywords = raw_rule.get("keywords")
        if not isinstance(keywords, list) or not keywords:
            raise ValueError(
        f"Missing keywords for rule {rule_id} "
        f"in authority {authority_code}"
    )

        existing_stmt = select(IndexedRule).where(
            IndexedRule.authority_code == authority_code,
            IndexedRule.rule_id == rule_id,
        )
        rule_record = db.execute(existing_stmt).scalar_one_or_none()

        if rule_record is None:
            rule_record = IndexedRule(
                authority_code=authority_code,
                rule_id=rule_id,
                category=category,
                description=description,
                severity=severity,
                is_hard_rejection=is_hard_rejection,
                rule_type=rule_type,
                parameters=parameters,
                source_citation=source_citation,
                effective_date=effective_date,
                keywords=keywords,
            )
            db.add(rule_record)
        else:
            rule_record.category = category
            rule_record.description = description
            rule_record.severity = severity
            rule_record.is_hard_rejection = is_hard_rejection
            rule_record.rule_type = rule_type
            rule_record.parameters = parameters
            rule_record.source_citation = source_citation
            rule_record.effective_date = effective_date
            rule_record.keywords = keywords

        indexed_records.append(rule_record)

    db.commit()
    for rec in indexed_records:
        db.refresh(rec)

    return indexed_records


def index_all_authorities(db: Session) -> dict[str, list[IndexedRule]]:
    results: dict[str, list[IndexedRule]] = {}
    if not AUTHORITIES_DIR.exists():
        return results

    for config_file in sorted(AUTHORITIES_DIR.glob("*.json")):
        authority_code = config_file.stem
        results[authority_code] = index_authority_rules(authority_code, db)
    return results
