from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(
    settings.supabase_db_url,
    echo=False,
    pool_pre_ping=True,
    connect_args={
        # Required for Supabase PgBouncer in transaction mode —
        # prepared statements are not supported across pooled connections.
        "statement_cache_size": 0,
    },
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass
