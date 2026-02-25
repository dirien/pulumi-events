"""Venue tools: create_venue."""

from __future__ import annotations

from typing import Any

from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from pulumi_events.exceptions import ProviderError
from pulumi_events.providers.meetup.provider import MeetupProvider
from pulumi_events.server import mcp
from pulumi_events.tools._deps import get_meetup_provider

__all__: list[str] = []


@mcp.tool()
async def meetup_create_venue(
    group_urlname: str,
    name: str,
    address: str,
    city: str,
    country: str,
    ctx: Context,
    state: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    provider: MeetupProvider = Depends(get_meetup_provider),
) -> dict[str, Any]:
    """Create a venue for use in Meetup events.

    Args:
        group_urlname: URL name of the group.
        name: Venue name.
        address: Street address.
        city: City name.
        country: Two-letter country code (e.g. US, DE).
        state: State/province (if applicable).
        lat: Latitude.
        lon: Longitude.
    """
    input_data: dict[str, Any] = {
        "groupUrlname": group_urlname,
        "name": name,
        "address": address,
        "city": city,
        "country": country,
    }
    if state is not None:
        input_data["state"] = state
    if lat is not None:
        input_data["lat"] = lat
    if lon is not None:
        input_data["lng"] = lon

    await ctx.info(f"Creating venue '{name}' in {city}...")
    try:
        return await provider.create_venue(**input_data)
    except ProviderError as exc:
        from fastmcp.exceptions import ToolError

        raise ToolError(str(exc)) from exc
