from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_posthog_client = None


def _get_client():
    global _posthog_client
    if _posthog_client is None:
        from app.config import settings
        if settings.posthog_api_key:
            from posthog import Posthog
            _posthog_client = Posthog(
                project_api_key=settings.posthog_api_key,
                host="https://eu.i.posthog.com",
            )
    return _posthog_client


def identify(distinct_id: str, properties: dict) -> None:
    """Call PostHog identify. No-ops silently if PostHog is not configured."""
    client = _get_client()
    if client is None:
        logger.debug("PostHog not configured, skipping identify for %s", distinct_id)
        return
    try:
        client.identify(distinct_id=distinct_id, properties=properties)
    except Exception as exc:
        logger.warning("PostHog identify failed: %s", exc)
