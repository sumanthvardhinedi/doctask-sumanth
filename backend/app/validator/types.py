from dataclasses import dataclass


@dataclass(frozen=True)
class DocumentInput:
    filename: str
    content_type: str
    file_size_bytes: int | None = None
    sort_order: int = 0
    has_signature: bool | None = None
    declaration_present: bool | None = None


@dataclass(frozen=True)
class PackageInput:
    authority_code: str
    name: str
    documents: tuple[DocumentInput, ...]


@dataclass(frozen=True)
class RuleDefinition:
    rule_id: str
    category: str
    description: str
    severity: str
    is_hard_rejection: bool
    rule_type: str
    parameters: dict[str, object]


@dataclass(frozen=True)
class ValidationFinding:
    rule_id: str
    rule_category: str
    severity: str
    result: str
    message: str
    evidence: str | None = None
    document_filename: str | None = None
    location: str | None = None
    is_hard_rejection: bool = True
