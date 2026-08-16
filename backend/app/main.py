from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.api import packages
from app.core.config import cors_origin_list
import app.models  # noqa: F401 — register ORM metadata

app = FastAPI(title="SuperDocs Regulatory Validator")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origin_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(packages.router)
