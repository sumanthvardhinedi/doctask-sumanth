from pathlib import Path

import pytest

from app.validator.rules import get_rules_for_authority


def test_authority_a_loads_from_configuration():
    rules = get_rules_for_authority("authority_a")

    assert len(rules) == 8
    assert rules[0].rule_id == "mandatory.cover_letter"
    assert rules[0].rule_type == "required_document"
    assert rules[0].parameters["filename"] == "cover_letter.pdf"


def test_authority_b_loads_from_configuration():
    rules = get_rules_for_authority("authority_b")

    assert len(rules) == 7
    assert rules[0].rule_id == "mandatory.executive_summary"
    assert rules[0].rule_type == "required_document"
    assert rules[0].parameters["filename"] == "ES_executive_summary.pdf"


def test_unknown_authority_fails_clearly():
    with pytest.raises(
        ValueError,
        match="Unknown authority code: unknown_authority",
    ):
        get_rules_for_authority("unknown_authority")


def test_authority_configuration_files_exist():
    authorities_dir = (
        Path(__file__).resolve().parents[1]
        / "config"
        / "authorities"
    )

    assert (authorities_dir / "authority_a.json").exists()
    assert (authorities_dir / "authority_b.json").exists()