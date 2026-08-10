from fastapi import FastAPI

from app.api import health

app = FastAPI(title="SuperDocs Regulatory Validator")

app.include_router(health.router)
