from fastapi import FastAPI

from app.api import health
from app.api import packages
import app.models  # noqa: F401 — register ORM metadata
from app.db.database import Base, engine, ensure_extensions

ensure_extensions()
Base.metadata.create_all(bind=engine)

app = FastAPI(title="SuperDocs Regulatory Validator")

app.include_router(health.router)
app.include_router(packages.router)