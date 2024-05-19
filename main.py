import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import assistant
from app.core.config import settings

logging.basicConfig(level=logging.DEBUG)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
)
app.add_middleware(
  CORSMiddleware,
  allow_origins=['*'],
  allow_credentials=True,
  allow_methods=['*'],
  allow_headers=['*'],
)
app.include_router(assistant.router, prefix=settings.API_V1_STR)


@app.get("/", tags=["Root"])
async def health():
    """Check the api is running"""
    return {"status": "👌"}
