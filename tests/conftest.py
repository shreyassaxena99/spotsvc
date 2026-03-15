from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

# Set required env vars before any app modules are imported.
# This allows pydantic-settings Settings() to initialise without a real .env file.
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "test-service-role-key")
os.environ.setdefault("GOOGLE_PLACES_API_KEY", "test-google-key")
os.environ.setdefault("ADMIN_PWD", "test-admin-pwd")

# Patch supabase create_client at import time so no real HTTP connection is made.
_mock_supabase = MagicMock()
patch("supabase.create_client", return_value=_mock_supabase).start()
