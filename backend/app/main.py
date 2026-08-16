from fastapi import FastAPI

from app.api import health
from app.api import packages
import app.models  # noqa: F401 — register ORM metadata

app = FastAPI(title="SuperDocs Regulatory Validator")

app.include_router(health.router)
app.include_router(packages.router)
