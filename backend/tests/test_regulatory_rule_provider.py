from unittest.mock import Mock, patch

from app.models.regulatory_rule import IndexedRule
from app.services.regulatory_rule_provider import get_indexed_rule_definitions


def test_provider_returns_indexed_rules_as_rule_definitions():
    db = Mock()

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
    )

    with patch(
        "app.services.regulatory_rule_provider.retrieve_rules",
        return_value=[rule],
    ):
        definitions = get_indexed_rule_definitions(
            db,
            "authority_a",
        )

    assert len(definitions) == 1
    assert definitions[0].rule_id == "A-001"
    assert definitions[0].rule_type == "required_document"
    assert definitions[0].parameters == {
        "filename": "application.pdf",
    }


def test_provider_returns_empty_tuple_when_no_rules():
    db = Mock()

    with patch(
        "app.services.regulatory_rule_provider.retrieve_rules",
        return_value=[],
    ):
        definitions = get_indexed_rule_definitions(
            db,
            "authority_a",
        )

    assert definitions == ()