import base64
from unittest.mock import Mock

from app.integrations.superdocs.client import SuperDocsClient


def test_client_exposes_four_required_operations():
    http_client = Mock()

    client = SuperDocsClient(
        base_url="https://api.superdocs.app",
        api_key="test-key",
        http_client=http_client,
    )

    assert callable(client.upload)
    assert callable(client.chat)
    assert callable(client.approve)
    assert callable(client.export)


def test_upload_sends_base64_document():
    http_client = Mock()

    response = Mock()
    response.json.return_value = {
        "session_id": "session-123",
        "version_id": "version-1",
    }
    http_client.post.return_value = response

    client = SuperDocsClient(
        base_url="https://api.superdocs.app",
        api_key="test-key",
        http_client=http_client,
    )

    result = client.upload(
        filename="filing.html",
        content=b"<html><body>Hello</body></html>",
        session_id="session-123",
    )

    expected_base64 = base64.b64encode(
        b"<html><body>Hello</body></html>"
    ).decode("ascii")

    http_client.post.assert_called_once_with(
        "https://api.superdocs.app/v1/documents/upload-base64",
        headers={
            "Authorization": "Bearer test-key",
            "Content-Type": "application/json",
        },
        json={
            "filename": "filing.html",
            "file_base64": expected_base64,
            "session_id": "session-123",
            "return_html": False,
        },
    )

    assert result == {
        "session_id": "session-123",
        "version_id": "version-1",
    }


def test_chat_sends_edit_instruction():
    http_client = Mock()

    response = Mock()
    response.json.return_value = {
        "response": "I updated the document.",
        "session_id": "session-123",
        "document_changes": {
            "requires_approval": True,
        },
    }
    http_client.post.return_value = response

    client = SuperDocsClient(
        base_url="https://api.superdocs.app",
        api_key="test-key",
        http_client=http_client,
    )

    result = client.chat(
        session_id="session-123",
        message="Fix the missing filing date.",
    )

    http_client.post.assert_called_once_with(
        "https://api.superdocs.app/v1/chat",
        headers={
            "Authorization": "Bearer test-key",
            "Content-Type": "application/json",
        },
        json={
            "message": "Fix the missing filing date.",
            "session_id": "session-123",
        },
    )

    assert result == {
        "response": "I updated the document.",
        "session_id": "session-123",
        "document_changes": {
            "requires_approval": True,
        },
    }


def test_approve_sends_change_decision():
    http_client = Mock()

    response = Mock()
    response.json.return_value = {
        "status": "approved",
        "job_id": "job-123",
    }
    http_client.post.return_value = response

    client = SuperDocsClient(
        base_url="https://api.superdocs.app",
        api_key="test-key",
        http_client=http_client,
    )

    result = client.approve(
        session_id="session-123",
        job_id="job-123",
        approved=True,
        change_id="change-456",
    )

    http_client.post.assert_called_once_with(
        "https://api.superdocs.app/v1/chat/session-123/approve",
        headers={
            "Authorization": "Bearer test-key",
            "Content-Type": "application/json",
        },
        json={
            "job_id": "job-123",
            "approved": True,
            "change_id": "change-456",
        },
    )

    assert result == {
        "status": "approved",
        "job_id": "job-123",
    }


def test_export_sends_session_export_request():
    http_client = Mock()

    response = Mock()
    response.json.return_value = {
        "status": "completed",
        "download_url": "https://example.com/file.docx",
    }
    http_client.post.return_value = response

    client = SuperDocsClient(
        base_url="https://api.superdocs.app",
        api_key="test-key",
        http_client=http_client,
    )

    result = client.export(
        session_id="session-123",
        format="docx",
    )

    http_client.post.assert_called_once_with(
        "https://api.superdocs.app/v1/documents/export",
        headers={
            "Authorization": "Bearer test-key",
            "Content-Type": "application/json",
        },
        json={
            "session_id": "session-123",
            "format": "docx",
        },
    )

    assert result == {
        "status": "completed",
        "download_url": "https://example.com/file.docx",
    }


def test_export_sends_html_export_request():
    http_client = Mock()

    response = Mock()
    response.json.return_value = {
        "status": "completed",
        "download_url": "https://example.com/file.pdf",
    }
    http_client.post.return_value = response

    client = SuperDocsClient(
        base_url="https://api.superdocs.app",
        api_key="test-key",
        http_client=http_client,
    )

    result = client.export(
        html="<html><body>Filing</body></html>",
        format="pdf",
    )

    http_client.post.assert_called_once_with(
        "https://api.superdocs.app/v1/documents/export",
        headers={
            "Authorization": "Bearer test-key",
            "Content-Type": "application/json",
        },
        json={
            "html": "<html><body>Filing</body></html>",
            "format": "pdf",
        },
    )

    assert result == {
        "status": "completed",
        "download_url": "https://example.com/file.pdf",
    }
