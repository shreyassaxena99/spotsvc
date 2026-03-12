from __future__ import annotations

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.security import decode_jwt, require_admin_role

security = HTTPBearer()


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
