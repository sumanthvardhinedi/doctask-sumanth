from unittest.mock import Mock

from app.integrations.superdocs.client import SuperDocsClient
from app.integrations.superdocs.parsing import parse_proposed_changes


def test_superdocs_edit_flow_uses_upload_chat_approve_and_export():
    http_client = Mock()

    upload_response = Mock()
    upload_response.json.return_value = {
        "session_id": "session-123",
        "version_id": "version-1",
    }

    chat_response = Mock()
    chat_response.json.return_value = {
        "job_id": "job-123",
        "proposed_changes": '{"changes": [{"change_id": "change-456"}]}',
    }

    approve_response = Mock()
    approve_response.json.return_value = {
        "status": "approved",
        "job_id": "job-123",
    }

    export_response = Mock()
    export_response.json.return_value = {
        "status": "completed",
        "download_url": "https://example.com/file.docx",
    }

    http_client.post.side_effect = [
        upload_response,
        chat_response,
        approve_response,
        export_response,
    ]

    client = SuperDocsClient(
        base_url="https://api.superdocs.app",
        api_key="test-key",
        http_client=http_client,
    )

    uploaded = client.upload(
        filename="filing.html",
        content=b"<html><body>Filing</body></html>",
    )

    assert uploaded["session_id"] == "session-123"

    chat_result = client.chat(
        session_id=uploaded["session_id"],
        message="Fix the missing filing date.",
    )

    assert chat_result["job_id"] == "job-123"

    proposed_changes = parse_proposed_changes(
        chat_result["proposed_changes"]
    )

    assert proposed_changes == {
        "changes": [
            {
                "change_id": "change-456",
            }
        ]
    }

    approved = client.approve(
        session_id=uploaded["session_id"],
        job_id=chat_result["job_id"],
        approved=True,
        change_id="change-456",
    )

    assert approved["status"] == "approved"

    exported = client.export(session_id=uploaded["session_id"])

    assert exported["status"] == "completed"
    assert exported["download_url"] == "https://example.com/file.docx"
