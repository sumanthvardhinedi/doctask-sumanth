from collections.abc import Generator

import httpx
from fastapi import Depends

from app.core.config import settings
from app.integrations.superdocs.client import SuperDocsClient
from app.storage.document_store import DocumentStore


def get_document_store() -> DocumentStore:
    return DocumentStore(settings.uploads_root)


def get_superdocs_client() -> Generator[SuperDocsClient, None, None]:
    with httpx.Client(timeout=30.0) as http_client:
        yield SuperDocsClient(
            base_url=settings.superdocs_base_url,
            api_key=settings.superdocs_api_key,
            http_client=http_client,
        )
