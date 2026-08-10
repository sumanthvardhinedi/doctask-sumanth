from app.models.enums import FindingSeverity
from app.validator.types import RuleDefinition

AUTHORITY_A_RULES: tuple[RuleDefinition, ...] = (
    RuleDefinition(
        rule_id="mandatory.cover_letter",
        category="mandatory_sections",
        description="Cover letter is required",
        severity=FindingSeverity.ERROR,
        is_hard_rejection=True,
        rule_type="required_document",
        parameters={"filename": "cover_letter.pdf"},
    ),
    RuleDefinition(
        rule_id="mandatory.appendix_a",
        category="mandatory_sections",
        description="Appendix A is required",
        severity=FindingSeverity.ERROR,
        is_hard_rejection=True,
        rule_type="required_document",
        parameters={"filename": "appendix_a.pdf"},
    ),
    RuleDefinition(
        rule_id="naming.lowercase_underscore",
        category="naming_conventions",
        description="Filenames must use lowercase letters, numbers, and underscores",
        severity=FindingSeverity.ERROR,
        is_hard_rejection=True,
        rule_type="filename_pattern",
        parameters={"pattern": r"^[a-z0-9_]+\.[a-z0-9]+$"},
    ),
    RuleDefinition(
        rule_id="ordering.standard",
        category="ordering",
        description="Documents must follow the published filing order",
        severity=FindingSeverity.ERROR,
        is_hard_rejection=True,
        rule_type="document_order",
        parameters={"order": ["cover_letter.pdf", "appendix_a.pdf"]},
    ),
    RuleDefinition(
        rule_id="format.pdf_only",
        category="file_format",
        description="Only PDF documents are accepted",
        severity=FindingSeverity.ERROR,
        is_hard_rejection=True,
        rule_type="allowed_content_types",
        parameters={"content_types": ["application/pdf"]},
    ),
    RuleDefinition(
        rule_id="size.max_ten_mb",
        category="file_size_limits",
        description="Each file must be 10 MB or smaller",
        severity=FindingSeverity.ERROR,
        is_hard_rejection=True,
        rule_type="max_file_size",
        parameters={"max_bytes": 10_485_760},
    ),
    RuleDefinition(
        rule_id="signature.cover_letter",
        category="signature_requirements",
        description="Cover letter must include a signature",
        severity=FindingSeverity.ERROR,
        is_hard_rejection=True,
        rule_type="requires_signature",
        parameters={"filename": "cover_letter.pdf"},
    ),
    RuleDefinition(
        rule_id="declaration.cover_letter",
        category="declarations",
        description="Cover letter must include the required declaration",
        severity=FindingSeverity.WARNING,
        is_hard_rejection=False,
        rule_type="requires_declaration",
        parameters={"filename": "cover_letter.pdf"},
    ),
)

AUTHORITY_B_RULES: tuple[RuleDefinition, ...] = (
    RuleDefinition(
        rule_id="mandatory.executive_summary",
        category="mandatory_sections",
        description="Executive summary is required",
        severity=FindingSeverity.ERROR,
        is_hard_rejection=True,
        rule_type="required_document",
        parameters={"filename": "ES_executive_summary.pdf"},
    ),
    RuleDefinition(
        rule_id="mandatory.technical_schedule",
        category="mandatory_sections",
        description="Technical schedule is required",
        severity=FindingSeverity.ERROR,
        is_hard_rejection=True,
        rule_type="required_document",
        parameters={"filename": "TS_technical_schedule.pdf"},
    ),
    RuleDefinition(
        rule_id="naming.prefixed_codes",
        category="naming_conventions",
        description="Filenames must start with a section code prefix",
        severity=FindingSeverity.ERROR,
        is_hard_rejection=True,
        rule_type="filename_pattern",
        parameters={"pattern": r"^[A-Z]{2,3}_[a-z0-9_]+\.pdf$"},
    ),
    RuleDefinition(
        rule_id="ordering.authority_b",
        category="ordering",
        description="Documents must follow Authority B filing order",
        severity=FindingSeverity.ERROR,
        is_hard_rejection=True,
        rule_type="document_order",
        parameters={"order": ["ES_executive_summary.pdf", "TS_technical_schedule.pdf"]},
    ),
    RuleDefinition(
        rule_id="format.pdf_only",
        category="file_format",
        description="Only PDF documents are accepted",
        severity=FindingSeverity.ERROR,
        is_hard_rejection=True,
        rule_type="allowed_content_types",
        parameters={"content_types": ["application/pdf"]},
    ),
    RuleDefinition(
        rule_id="size.max_five_mb",
        category="file_size_limits",
        description="Each file must be 5 MB or smaller",
        severity=FindingSeverity.ERROR,
        is_hard_rejection=True,
        rule_type="max_file_size",
        parameters={"max_bytes": 5_242_880},
    ),
    RuleDefinition(
        rule_id="signature.executive_summary",
        category="signature_requirements",
        description="Executive summary must include a signature",
        severity=FindingSeverity.ERROR,
        is_hard_rejection=True,
        rule_type="requires_signature",
        parameters={"filename": "ES_executive_summary.pdf"},
    ),
)

_RULES_BY_AUTHORITY: dict[str, tuple[RuleDefinition, ...]] = {
    "authority_a": AUTHORITY_A_RULES,
    "authority_b": AUTHORITY_B_RULES,
}


def get_rules_for_authority(authority_code: str) -> tuple[RuleDefinition, ...]:
    try:
        return _RULES_BY_AUTHORITY[authority_code]
    except KeyError as exc:
        raise ValueError(f"Unknown authority code: {authority_code}") from exc
