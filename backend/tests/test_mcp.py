import asyncio
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy.orm import Session

from app.db.database import Base, engine, ensure_extensions
from app.mcp.errors import ToolFailure
from app.mcp.operations import (
    add_package_document,
    create_filing_package,
    decide_finding,
    get_agent_workflow,
    list_findings,
    validate_filing_package,
)
from app.mcp.server import TOOL_NAMES, build_mcp_server
from app.models import ApprovalDecision, AgentWorkflowStatus
from app.services.rule_indexer import index_all_authorities


@pytest.fixture()
def db() -> Session:
    ensure_extensions()
    Base.metadata.create_all(bind=engine)

    try:
        with Session(engine) as session:
            index_all_authorities(session)
            yield session
    finally:
        Base.metadata.drop_all(bind=engine)


def _call(server, tool_name: str, **arguments) -> dict:
    result = asyncio.run(server.call_tool(tool_name, arguments))
    assert result.content
    return json.loads(result.content[0].text)


def test_mcp_server_lists_machine_flow_tools() -> None:
    tools = asyncio.run(build_mcp_server().list_tools())
    assert sorted(tool.name for tool in tools) == sorted(TOOL_NAMES)


def test_create_package_rejects_unknown_authority(db: Session) -> None:
    with pytest.raises(ToolFailure) as exc:
        create_filing_package(db, "unknown_authority", "Nope")
    assert exc.value.code == "invalid_request"


def test_mcp_drives_validate_and_per_finding_decision(db: Session) -> None:
    server = build_mcp_server()

    created = _call(
        server,
        "create_filing_package",
        authority_code="authority_a",
        name="MCP package",
    )
    assert created["ok"] is True
    package_id = created["id"]

    missing = _call(server, "get_agent_workflow", package_id=package_id)
    assert missing == {
        "ok": False,
        "code": "not_found",
        "error": "Agent workflow not found",
    }

    document = _call(
        server,
        "add_package_document",
        package_id=package_id,
        filename="cover_letter.pdf",
        content_type="application/pdf",
        file_size_bytes=1024,
        storage_path="test/cover_letter.pdf",
        sort_order=1,
    )
    assert document["ok"] is True
    assert document["filename"] == "cover_letter.pdf"

    run = _call(server, "validate_filing_package", package_id=package_id)
    assert run["ok"] is True
    validation_run_id = run["id"]

    workflow = _call(server, "get_agent_workflow", package_id=package_id)
    assert workflow["ok"] is True
    assert workflow["status"] == AgentWorkflowStatus.WAITING_FOR_HUMAN
    assert workflow["token_count"] is None
    assert workflow["estimated_cost"] is None
    assert workflow["total_duration_ms"] is None

    listed = _call(
        server,
        "list_findings",
        package_id=package_id,
        validation_run_id=validation_run_id,
    )
    assert listed["ok"] is True
    findings = listed["findings"]
    assert len(findings) >= 2

    first_id = findings[0]["id"]
    second_id = findings[1]["id"]

    rejected = _call(
        server,
        "decide_finding",
        package_id=package_id,
        validation_run_id=validation_run_id,
        finding_id=first_id,
        approved=False,
        reviewer_notes="Needs a fix.",
    )
    assert rejected["ok"] is True
    assert rejected["approved"] is False

    duplicate = _call(
        server,
        "decide_finding",
        package_id=package_id,
        validation_run_id=validation_run_id,
        finding_id=first_id,
        approved=True,
    )
    assert duplicate == {
        "ok": False,
        "code": "conflict",
        "error": "Finding already has an approval decision",
    }

    second = (
        db.query(ApprovalDecision)
        .filter(ApprovalDecision.finding_id == uuid.UUID(second_id))
        .first()
    )
    assert second is None


def test_operations_unknown_package_is_not_found(db: Session) -> None:
    missing = str(uuid.uuid4())
    with pytest.raises(ToolFailure) as exc:
        add_package_document(
            db,
            missing,
            "a.pdf",
            "application/pdf",
            1,
            "a.pdf",
            0,
        )
    assert exc.value.code == "not_found"
    assert exc.value.message == "Filing package not found"

    with pytest.raises(ToolFailure) as exc:
        validate_filing_package(db, missing)
    assert exc.value.code == "not_found"

    with pytest.raises(ToolFailure) as exc:
        list_findings(db, missing, missing)
    assert exc.value.code == "not_found"

    with pytest.raises(ToolFailure) as exc:
        get_agent_workflow(db, missing)
    assert exc.value.code == "not_found"

    with pytest.raises(ToolFailure) as exc:
        decide_finding(db, missing, missing, missing, True)
    assert exc.value.code == "not_found"
