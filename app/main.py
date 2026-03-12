from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.admin.router import router as admin_router
from app.config import settings
from app.db.database import engine
from app.google_places.client import google_places_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Graceful shutdown — close persistent connections
    await engine.dispose()
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
    allow_origins=["*"],  # TODO: restrict to admin panel origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_router, prefix="/admin", tags=["admin"])


@app.get("/health", tags=["meta"])
async def health_check():
    return {"status": "ok"}
