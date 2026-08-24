import base64
from typing import Any


class SuperDocsClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        http_client: Any,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.http_client = http_client

    def upload(
        self,
        filename: str,
        content: bytes,
        session_id: str | None = None,
        return_html: bool = False,
    ) -> Any:
        file_base64 = base64.b64encode(content).decode("ascii")

        payload: dict[str, Any] = {
            "filename": filename,
            "file_base64": file_base64,
            "return_html": return_html,
        }

        if session_id is not None:
            payload["session_id"] = session_id

        response = self.http_client.post(
            f"{self.base_url}/v1/documents/upload-base64",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

        response.raise_for_status()
        print("[SuperDocsClient.upload] status=", response.status_code)
        print("[SuperDocsClient.upload] response=", response.text)

        return response.json()

    def chat(
        self,
        session_id: str,
        message: str,
    ) -> Any:
        response = self.http_client.post(
            f"{self.base_url}/v1/chat",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "message": message,
                "session_id": session_id,
            },
        )

        response.raise_for_status()

        response.raise_for_status()
        result = response.json()
        print("[SuperDocs upload response]", result)
        return result

    def approve(
        self,
        session_id: str,
        job_id: str,
        approved: bool,
        change_id: str | None = None,
        feedback: str | None = None,
        changes: list[dict[str, Any]] | None = None,
    ) -> Any:
        payload: dict[str, Any] = {
            "job_id": job_id,
            "approved": approved,
        }

        if change_id is not None:
            payload["change_id"] = change_id

        if feedback is not None:
            payload["feedback"] = feedback

        if changes is not None:
            payload["changes"] = changes

        response = self.http_client.post(
            f"{self.base_url}/v1/chat/{session_id}/approve",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

        response.raise_for_status()

        return response.json()

    def export(
        self,
        session_id: str | None = None,
        html: str | None = None,
        format: str = "docx",
    ) -> Any:
        payload: dict[str, Any] = {
            "format": format,
        }

        if session_id is not None:
            payload["session_id"] = session_id

        if html is not None:
            payload["html"] = html

        if session_id is None and html is None:
            raise ValueError("Either session_id or html must be provided")

        response = self.http_client.post(
            f"{self.base_url}/v1/documents/export",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

        response.raise_for_status()

        return response.json()