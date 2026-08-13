import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.database import Base, engine, ensure_extensions
from app.models.regulatory_rule import IndexedRule
from app.services.rule_indexer import index_all_authorities, index_authority_rules


@pytest.fixture()
def db() -> Session:
    ensure_extensions()
    Base.metadata.create_all(bind=engine)

    try:
        with Session(engine) as session:
            yield session
    finally:
        Base.metadata.drop_all(bind=engine)


def test_index_authority_a_rules(db: Session) -> None:
    indexed = index_authority_rules("authority_a", db)
    assert len(indexed) > 0

    stmt = select(IndexedRule).where(IndexedRule.authority_code == "authority_a")
    db_rules = db.execute(stmt).scalars().all()
    assert len(db_rules) == len(indexed)

    cover_letter_rule = next(
        (r for r in db_rules if r.rule_id == "mandatory.cover_letter"), None
    )
    assert cover_letter_rule is not None
    assert cover_letter_rule.authority_code == "authority_a"
    assert cover_letter_rule.category == "mandatory_sections"
    assert cover_letter_rule.severity == "error"
    assert cover_letter_rule.is_hard_rejection is True
    assert cover_letter_rule.rule_type == "required_document"
    assert cover_letter_rule.parameters == {"filename": "cover_letter.pdf"}
    assert cover_letter_rule.source_citation is not None


def test_index_authority_b_rules(db: Session) -> None:
    indexed = index_authority_rules("authority_b", db)
    assert len(indexed) > 0

    stmt = select(IndexedRule).where(IndexedRule.authority_code == "authority_b")
    db_rules = db.execute(stmt).scalars().all()
    assert len(db_rules) == len(indexed)

    exec_summary_rule = next(
        (r for r in db_rules if r.rule_id == "mandatory.executive_summary"), None
    )
    assert exec_summary_rule is not None
    assert exec_summary_rule.authority_code == "authority_b"
    assert exec_summary_rule.parameters == {"filename": "ES_executive_summary.pdf"}


def test_index_all_authorities(db: Session) -> None:
    results = index_all_authorities(db)
    assert "authority_a" in results
    assert "authority_b" in results
    assert len(results["authority_a"]) > 0
    assert len(results["authority_b"]) > 0


def test_repeated_indexing_is_idempotent(db: Session) -> None:
    first_pass = index_authority_rules("authority_a", db)
    count_first = len(first_pass)

    second_pass = index_authority_rules("authority_a", db)
    count_second = len(second_pass)

    assert count_first == count_second

    stmt = select(IndexedRule).where(IndexedRule.authority_code == "authority_a")
    all_records = db.execute(stmt).scalars().all()
    assert len(all_records) == count_first


def test_authority_and_rule_id_uniqueness(db: Session) -> None:
    index_authority_rules("authority_a", db)

    duplicate_rule = IndexedRule(
        authority_code="authority_a",
        rule_id="mandatory.cover_letter",
        category="mandatory_sections",
        severity="error",
        is_hard_rejection=True,
        rule_type="required_document",
        parameters={"filename": "cover_letter.pdf"},
    )
    db.add(duplicate_rule)

    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_source_citation_and_parameters_preserved(db: Session) -> None:
    index_authority_rules("authority_a", db)

    stmt = select(IndexedRule).where(
        IndexedRule.authority_code == "authority_a",
        IndexedRule.rule_id == "naming.lowercase_underscore",
    )
    rule = db.execute(stmt).scalar_one()

    assert rule.parameters == {"pattern": "^[a-z0-9_]+.[a-z0-9]+$"}
    assert "Authority A" in rule.source_citation
    assert rule.category == "naming_conventions"
    assert rule.keywords is not None
