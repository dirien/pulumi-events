"""Luma resource templates — read-only URI-based lookups."""

from __future__ import annotations

import json

from fastmcp.dependencies import Depends

from pulumi_events.exceptions import ProviderError
from pulumi_events.providers.luma.provider import LumaProvider
from pulumi_events.server import mcp
from pulumi_events.tools._deps import get_luma_provider

__all__: list[str] = []


@mcp.resource("luma://self")
async def luma_self(
    provider: LumaProvider = Depends(get_luma_provider),
) -> str:
    """Authenticated Luma user profile."""
    try:
        data = await provider.get_self()
        return json.dumps(data, indent=2)
    except ProviderError as exc:
        return json.dumps({"error": str(exc)})


@mcp.resource("luma://event/{event_id}")
async def luma_event(
    event_id: str,
    provider: LumaProvider = Depends(get_luma_provider),
) -> str:
    """Luma event details by API ID."""
    try:
        data = await provider.get_event(event_id)
        return json.dumps(data, indent=2)
    except ProviderError as exc:
        return json.dumps({"error": str(exc)})
