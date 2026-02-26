"""Meetup resource templates — read-only URI-based lookups."""

from __future__ import annotations

import json

from fastmcp.dependencies import Depends

from pulumi_events.exceptions import ProviderError
from pulumi_events.providers.meetup.provider import MeetupProvider
from pulumi_events.server import mcp
from pulumi_events.tools._deps import get_meetup_provider

__all__: list[str] = []


@mcp.resource("meetup://self")
async def meetup_self(
    provider: MeetupProvider = Depends(get_meetup_provider),
) -> str:
    """Authenticated Meetup user profile (id, name, group count)."""
    try:
        data = await provider.get_self()
        return json.dumps(data, indent=2)
    except ProviderError as exc:
        return json.dumps({"error": str(exc)})


@mcp.resource("meetup://group/{urlname}")
async def meetup_group(
    urlname: str,
    provider: MeetupProvider = Depends(get_meetup_provider),
) -> str:
    """Meetup group details by URL name."""
    try:
        data = await provider.get_group(urlname)
        return json.dumps(data, indent=2)
    except ProviderError as exc:
        return json.dumps({"error": str(exc)})


@mcp.resource("meetup://event/{event_id}")
async def meetup_event(
    event_id: str,
    provider: MeetupProvider = Depends(get_meetup_provider),
) -> str:
    """Meetup event details by event ID."""
    try:
        data = await provider.get_event(event_id)
        return json.dumps(data, indent=2)
    except ProviderError as exc:
        return json.dumps({"error": str(exc)})


@mcp.resource("meetup://network/{urlname}")
async def meetup_network(
    urlname: str,
    provider: MeetupProvider = Depends(get_meetup_provider),
) -> str:
    """Meetup Pro network info (name, description, status, link)."""
    try:
        data = await provider.get_network(urlname)
        return json.dumps(data, indent=2)
    except ProviderError as exc:
        return json.dumps({"error": str(exc)})
