"""OAuth2 authorization flow helpers."""

from __future__ import annotations

import logging
import urllib.parse
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from pulumi_events.settings import Settings

__all__ = ["build_auth_url", "exchange_code"]

logger = logging.getLogger(__name__)


async def build_auth_url(client_id: str, settings: Settings) -> str:
    """Build the Meetup OAuth2 authorization URL."""
    params = urllib.parse.urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": settings.meetup_redirect_uri,
        }
    )
    return f"{settings.meetup_auth_endpoint}?{params}"


async def exchange_code(
    code: str,
    client_id: str,
    client_secret: str,
    settings: Settings,
) -> dict[str, object]:
    """Exchange an authorization code for an access token."""
    async with httpx.AsyncClient() as http:
        resp = await http.post(
            settings.meetup_token_endpoint,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "authorization_code",
                "redirect_uri": settings.meetup_redirect_uri,
                "code": code,
            },
        )
        resp.raise_for_status()
        return resp.json()
