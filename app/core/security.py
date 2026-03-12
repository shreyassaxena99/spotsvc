from __future__ import annotations

from fastapi import HTTPException
from jose import jwt, JWTError

from app.config import settings


def decode_jwt(token: str) -> dict:
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated",
        )
        return {
            "user_id": payload["sub"],
            "email": payload.get("email"),
            "app_metadata": payload.get("app_metadata", {}),
        }
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


def require_admin_role(payload: dict) -> None:
    if payload.get("app_metadata", {}).get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
