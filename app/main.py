from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.admin.router import router as admin_router
from app.config import settings
from app.db.database import supabase
from app.google_places.client import google_places_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    google_places_client.close()


app = FastAPI(
    title="Spotsvc API",
    description="Backend for the London Work Spots app",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url="/redoc" if settings.app_env != "production" else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router, prefix="/admin", tags=["admin"])


@app.get("/health", tags=["meta"])
async def health_check():
    try:
        supabase.table("spots").select("id").limit(1).execute()
        db_status = "ok"
    except Exception as exc:
        logger.error("Health check DB ping failed: %s", exc, exc_info=True)
        db_status = str(exc)
    return {"status": "ok", "db": db_status}
