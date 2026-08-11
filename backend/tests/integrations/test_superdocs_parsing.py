import pytest

from app.integrations.superdocs.parsing import (
    parse_final_result,
    parse_proposed_changes,
)


def test_parse_proposed_changes_from_json_string():
    value = '{"changes": [{"type": "replace", "text": "updated"}]}'

    result = parse_proposed_changes(value)

    assert result == {
        "changes": [
            {
                "type": "replace",
                "text": "updated",
            }
        ]
    }


def test_parse_proposed_changes_keeps_object():
    value = {"changes": []}

    result = parse_proposed_changes(value)

    assert result is value


def test_parse_final_result_keeps_object():
    value = {"status": "approved", "document_id": "doc-123"}

    result = parse_final_result(value)

    assert result is value


def test_parse_proposed_changes_rejects_invalid_json():
    with pytest.raises(ValueError):
        parse_proposed_changes("not valid json")