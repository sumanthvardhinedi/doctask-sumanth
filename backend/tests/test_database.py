import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.core.config import settings
from app.db.database import ensure_extensions, engine


def test_database_connectivity_and_pgvector() -> None:
    try:
        with engine.connect() as conn:
            assert conn.execute(text("SELECT 1")).scalar() == 1
    except OperationalError as exc:
        pytest.fail(
            f"Could not connect to PostgreSQL at {settings.database_url}. "
            "Is Docker PostgreSQL running? Start with: docker compose up -d\n"
            f"Original error: {exc}"
        )

    ensure_extensions()

    try:
        with engine.connect() as conn:
            vector_installed = conn.execute(
                text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')")
            ).scalar()
    except OperationalError as exc:
        pytest.fail(
            f"Could not verify pgvector extension at {settings.database_url}. "
            "Is Docker PostgreSQL running? Start with: docker compose up -d\n"
            f"Original error: {exc}"
        )

    assert vector_installed is True
