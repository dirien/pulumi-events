"""Meetup JWT authentication for headless server-to-server access."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import httpx
import jwt

from pulumi_events.exceptions import AuthenticationError

if TYPE_CHECKING:
    from pulumi_events.settings import Settings

__all__ = ["authenticate_jwt"]

logger = logging.getLogger(__name__)


async def authenticate_jwt(settings: Settings, http: httpx.AsyncClient) -> dict:
    """Exchange a signed JWT for a Meetup access token (no browser needed).

    Uses the JWT Bearer grant flow for Meetup Pro administrators.
    See: https://www.meetup.com/api/authentication/#p04-jwt-flow-for-pro-administrators
    """
    now = int(time.time())
    payload = {
        "sub": settings.meetup_member_id,
        "iss": settings.meetup_client_id.get_secret_value(),
        "aud": "api.meetup.com",
        "exp": now + 120,
    }
    headers = {"kid": settings.meetup_jwt_key_id}

    private_key = settings.meetup_jwt_signing_key.get_secret_value()
    signed_jwt = jwt.encode(payload, private_key, algorithm="RS256", headers=headers)

    resp = await http.post(
        settings.meetup_token_endpoint,
        data={
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "assertion": signed_jwt,
        },
    )
    if resp.status_code != 200:
        msg = f"Meetup JWT auth failed ({resp.status_code}): {resp.text}"
        raise AuthenticationError(msg)

    token_data = resp.json()
    logger.info("Meetup JWT authentication succeeded")
    return token_data
