from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Supabase
    supabase_url: str
    supabase_jwt_secret: str
    supabase_service_role_key: str
    supabase_db_url: str  # postgresql+asyncpg://... port 6543 for PgBouncer

    # Google Places API (New)
    google_places_api_key: str

    # App
    app_env: str = "development"


settings = Settings()
