from __future__ import annotations

"""
Daily WFH notification scheduler — run as a cron job at 09:00 Europe/London.
Usage: python -m app.notifications.scheduler
"""

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
import pytz
from jose import jwt

from app.config import settings
from app.db.database import supabase

logger = logging.getLogger(__name__)

_LONDON_TZ = pytz.timezone("Europe/London")
_WEEKDAY_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_MON_WED = {"Monday", "Tuesday", "Wednesday"}
_THU_FRI = {"Thursday", "Friday"}

_NOTIFICATION_TITLE = "Working from home today?"
_NOTIFICATION_BODY = "Find a great spot near you on qwip."


def _build_apns_jwt(key_content: str, key_id: str, team_id: str) -> str:
    payload = {"iss": team_id, "iat": int(time.time())}
    return jwt.encode(payload, key_content, algorithm="ES256", headers={"kid": key_id})


def _should_notify(wfh_days: Optional[list[str]], today: str) -> bool:
    if not wfh_days:
        return today in ("Saturday", "Sunday")
    sorted_days = sorted(wfh_days, key=lambda d: _WEEKDAY_ORDER.index(d) if d in _WEEKDAY_ORDER else 99)
    early = next((d for d in sorted_days if d in _MON_WED), None)
    late = next((d for d in sorted_days if d in _THU_FRI), None)
    return today == early or today == late


def run() -> None:
    if not all([settings.apns_key_content, settings.apns_key_id, settings.apns_team_id, settings.apns_bundle_id]):
        logger.error("APNs config incomplete — set APNS_KEY_CONTENT, APNS_KEY_ID, APNS_TEAM_ID, APNS_BUNDLE_ID")
        return

    today = datetime.now(_LONDON_TZ).strftime("%A")
    logger.info("Notification scheduler running for %s", today)

    result = (
        supabase.table("user_profiles")
        .select("user_id, wfh_days, push_token")
        .not_.is_("push_token", "null")
        .execute()
    )
    users = result.data or []
    logger.info("Found %d users with push tokens", len(users))

    apns_host = (
        "https://api.sandbox.push.apple.com" if settings.apns_sandbox else "https://api.push.apple.com"
    )

    # Cache the APNs JWT — regenerate every 55 minutes (valid for 1 hour)
    _jwt_cache: dict[str, object] = {}

    def get_apns_jwt() -> str:
        now = time.time()
        issued_at = _jwt_cache.get("issued_at", 0)
        if now - issued_at < 55 * 60 and "token" in _jwt_cache:
            return _jwt_cache["token"]  # type: ignore[return-value]
        token = _build_apns_jwt(settings.apns_key_content, settings.apns_key_id, settings.apns_team_id)
        _jwt_cache["token"] = token
        _jwt_cache["issued_at"] = now
        return token

    with httpx.Client(http2=True) as client:
        for user in users:
            user_id: str = user["user_id"]
            wfh_days: Optional[list[str]] = user.get("wfh_days") or None
            push_token: str = user["push_token"]

            if not _should_notify(wfh_days, today):
                continue

            notification_payload = {
                "aps": {
                    "alert": {"title": _NOTIFICATION_TITLE, "body": _NOTIFICATION_BODY},
                    "sound": "default",
                }
            }

            try:
                resp = client.post(
                    f"{apns_host}/3/device/{push_token}",
                    json=notification_payload,
                    headers={
                        "authorization": f"bearer {get_apns_jwt()}",
                        "apns-topic": settings.apns_bundle_id,
                        "apns-push-type": "alert",
                        "apns-priority": "10",
                    },
                )
                if resp.status_code == 410:
                    logger.info("Stale APNs token for user %s — clearing", user_id)
                    supabase.table("user_profiles").update(
                        {
                            "push_token": None,
                            "push_token_updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                    ).eq("user_id", user_id).execute()
                elif resp.status_code not in (200, 204):
                    logger.error(
                        "APNs error for user %s: HTTP %s — %s", user_id, resp.status_code, resp.text
                    )
                else:
                    logger.info("Notification sent to user %s", user_id)
            except Exception as exc:
                logger.error("Failed to send notification to user %s: %s", user_id, exc)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
