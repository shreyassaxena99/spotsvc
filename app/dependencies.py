from __future__ import annotations

from typing import AsyncGenerator

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_jwt, require_admin_role
from app.db.database import AsyncSessionLocal

security = HTTPBearer()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    return decode_jwt(credentials.credentials)


async def get_admin_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    payload = decode_jwt(credentials.credentials)
    require_admin_role(payload)
    return payload


async def no_auth() -> dict:
    return {}
