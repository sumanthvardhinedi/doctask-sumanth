import pytest

from app.models.regulatory_rule import IndexedRule
from app.services.regulatory_rule_adapter import indexed_rule_to_definition


def test_indexed_rule_converts_to_rule_definition():
    rule = IndexedRule(
        authority_code="authority_a",
        rule_id="A-001",
        category="mandatory_sections",
        description="Required filing document",
        severity="ERROR",
        is_hard_rejection=True,
        rule_type="required_document",
        parameters={
            "filename": "application.pdf",
        },
        source_citation="https://example.com/rules/A-001",
    )

    definition = indexed_rule_to_definition(rule)

    assert definition.rule_id == "A-001"
    assert definition.category == "mandatory_sections"
    assert definition.description == "Required filing document"
    assert definition.severity == "ERROR"
    assert definition.is_hard_rejection is True
    assert definition.rule_type == "required_document"
    assert definition.parameters == {
        "filename": "application.pdf",
    }


def test_indexed_rule_preserves_parameters():
    rule = IndexedRule(
        authority_code="authority_a",
        rule_id="A-002",
        category="file_size",
        description="File must not exceed limit",
        severity="ERROR",
        is_hard_rejection=True,
        rule_type="max_file_size",
        parameters={
            "max_bytes": 5000000,
            "unit": "bytes",
        },
    )

    definition = indexed_rule_to_definition(rule)

    assert definition.parameters == {
        "max_bytes": 5000000,
        "unit": "bytes",
    }


def test_indexed_rule_preserves_discretionary_status():
    rule = IndexedRule(
        authority_code="authority_a",
        rule_id="A-003",
        category="declarations",
        description="Declaration should be present",
        severity="WARNING",
        is_hard_rejection=False,
        rule_type="requires_declaration",
        parameters={
            "required": True,
        },
    )

    definition = indexed_rule_to_definition(rule)

    assert definition.severity == "WARNING"
    assert definition.is_hard_rejection is False


def test_indexed_rule_requires_description():
    rule = IndexedRule(
        authority_code="authority_a",
        rule_id="A-004",
        category="mandatory_sections",
        description=None,
        severity="ERROR",
        is_hard_rejection=True,
        rule_type="required_document",
        parameters={
            "filename": "application.pdf",
        },
    )

    with pytest.raises(ValueError, match="missing required fields"):
        indexed_rule_to_definition(rule)


def test_indexed_rule_requires_rule_type():
    rule = IndexedRule(
        authority_code="authority_a",
        rule_id="A-005",
        category="mandatory_sections",
        description="Required filing document",
        severity="ERROR",
        is_hard_rejection=True,
        rule_type=None,
        parameters={
            "filename": "application.pdf",
        },
    )

    with pytest.raises(ValueError, match="missing required fields"):
        indexed_rule_to_definition(rule)