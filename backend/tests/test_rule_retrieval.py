from app.models.regulatory_rule import IndexedRule
from app.services.rule_indexer import index_all_authorities
from app.services.rule_retrieval import retrieve_rules
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.database import Base
from app.models.regulatory_rule import IndexedRule
from app.services.rule_indexer import index_all_authorities
from app.services.rule_retrieval import retrieve_rules


@pytest.fixture()
def db() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    Base.metadata.drop_all(engine)
    engine.dispose()

def test_retrieve_rules_for_authority_a(db):
    index_all_authorities(db)

    rules = retrieve_rules(db, "authority_a")

    assert rules
    assert all(rule.authority_code == "authority_a" for rule in rules)


def test_retrieve_rules_for_authority_b(db):
    index_all_authorities(db)

    rules = retrieve_rules(db, "authority_b")

    assert rules
    assert all(rule.authority_code == "authority_b" for rule in rules)


def test_retrieval_is_scoped_to_authority(db):
    index_all_authorities(db)

    authority_a_rules = retrieve_rules(db, "authority_a")
    authority_b_rules = retrieve_rules(db, "authority_b")

    assert authority_a_rules
    assert authority_b_rules
    assert all(rule.authority_code == "authority_a" for rule in authority_a_rules)
    assert all(rule.authority_code == "authority_b" for rule in authority_b_rules)


def test_category_filter(db):
    index_all_authorities(db)

    all_rules = retrieve_rules(db, "authority_a")
    category = all_rules[0].category

    rules = retrieve_rules(
        db,
        "authority_a",
        category=category,
    )

    assert rules
    assert all(rule.category == category for rule in rules)


def test_rule_type_filter(db):
    index_all_authorities(db)

    all_rules = retrieve_rules(db, "authority_a")
    rule_type = all_rules[0].rule_type

    rules = retrieve_rules(
        db,
        "authority_a",
        rule_type=rule_type,
    )

    assert rules
    assert all(rule.rule_type == rule_type for rule in rules)
def test_query_matches_rule_metadata(db):
    index_all_authorities(db)

    all_rules = retrieve_rules(db, "authority_a")
    rule = all_rules[0]

    rules = retrieve_rules(
        db,
        "authority_a",
        query=rule.rule_id,
    )

    assert rules
    assert rule.id in {retrieved.id for retrieved in rules}


def test_limit_is_respected(db):
    index_all_authorities(db)

    rules = retrieve_rules(
        db,
        "authority_a",
        limit=1,
    )

    assert len(rules) <= 1


def test_zero_or_negative_limit_returns_empty(db):
    index_all_authorities(db)

    assert retrieve_rules(db, "authority_a", limit=0) == []
    assert retrieve_rules(db, "authority_a", limit=-1) == []


def test_unknown_authority_returns_empty(db):
    index_all_authorities(db)

    assert retrieve_rules(db, "unknown_authority") == []

def test_retrieved_metadata_is_preserved(db):
    index_all_authorities(db)

    rules = retrieve_rules(db, "authority_a")

    assert rules

    rule = rules[0]

    assert isinstance(rule, IndexedRule)
    assert rule.rule_id
    assert rule.category
    assert rule.severity
    assert rule.rule_type
    assert rule.parameters is not None
    assert rule.source_citation