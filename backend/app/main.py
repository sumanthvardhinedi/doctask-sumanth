
from fastapi import FastAPI

from app.api import health
from app.api import packages

app = FastAPI(title="SuperDocs Regulatory Validator")

app.include_router(health.router)
app.include_router(packages.router)