"""Luma event tools: list, create, update, cancel, guests."""

from __future__ import annotations

from typing import Any

from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from pulumi_events.exceptions import ProviderError
from pulumi_events.providers.luma.provider import LumaProvider
from pulumi_events.server import mcp
from pulumi_events.tools._deps import get_luma_provider

__all__: list[str] = []


@mcp.tool(
    annotations={"readOnlyHint": True},
)
async def luma_list_events(
    ctx: Context,
    after: str | None = None,
    limit: int | None = None,
    provider: LumaProvider = Depends(get_luma_provider),
) -> dict[str, Any]:
    """List events from your Luma calendar.

    Args:
        after: Pagination cursor from a previous response.
        limit: Maximum number of events to return.
    """
    await ctx.info("Fetching Luma events...")
    try:
        return await provider.list_events(after=after, limit=limit)
    except ProviderError as exc:
        from fastmcp.exceptions import ToolError

        raise ToolError(str(exc)) from exc


@mcp.tool()
async def luma_create_event(
    name: str,
    start_at: str,
    end_at: str,
    ctx: Context,
    description: str | None = None,
    timezone: str | None = None,
    geo_address_json: dict[str, Any] | None = None,
    geo_latitude: str | None = None,
    geo_longitude: str | None = None,
    meeting_url: str | None = None,
    visibility: str = "public",
    provider: LumaProvider = Depends(get_luma_provider),
) -> dict[str, Any]:
    """Create a Luma event.

    Args:
        name: Event title.
        start_at: Start time in ISO 8601 format (UTC).
        end_at: End time in ISO 8601 format (UTC).
        description: Event description (markdown supported).
        timezone: Timezone (e.g. America/New_York). Defaults to account timezone.
        geo_address_json: Venue address object with keys: address, city, full_address, etc.
        geo_latitude: Venue latitude.
        geo_longitude: Venue longitude.
        meeting_url: Online meeting URL (for virtual events).
        visibility: Event visibility — public or private.
    """
    input_data: dict[str, Any] = {
        "name": name,
        "start_at": start_at,
        "end_at": end_at,
        "visibility": visibility,
    }
    if description is not None:
        input_data["description_md"] = description
    if timezone is not None:
        input_data["timezone"] = timezone
    if geo_address_json is not None:
        input_data["geo_address_json"] = geo_address_json
    if geo_latitude is not None:
        input_data["geo_latitude"] = geo_latitude
    if geo_longitude is not None:
        input_data["geo_longitude"] = geo_longitude
    if meeting_url is not None:
        input_data["meeting_url"] = meeting_url

    await ctx.info(f"Creating Luma event '{name}'...")
    try:
        return await provider.create_event(**input_data)
    except ProviderError as exc:
        from fastmcp.exceptions import ToolError

        raise ToolError(str(exc)) from exc


@mcp.tool(
    annotations={"idempotentHint": True},
)
async def luma_update_event(
    event_id: str,
    ctx: Context,
    name: str | None = None,
    description: str | None = None,
    start_at: str | None = None,
    end_at: str | None = None,
    timezone: str | None = None,
    geo_address_json: dict[str, Any] | None = None,
    geo_latitude: str | None = None,
    geo_longitude: str | None = None,
    meeting_url: str | None = None,
    visibility: str | None = None,
    provider: LumaProvider = Depends(get_luma_provider),
) -> dict[str, Any]:
    """Update a Luma event. Only provided fields are changed.

    Args:
        event_id: The Luma event API ID (evt-...).
        name: New event title.
        description: New description (markdown).
        start_at: New start time (ISO 8601 UTC).
        end_at: New end time (ISO 8601 UTC).
        timezone: New timezone.
        geo_address_json: New venue address object.
        geo_latitude: New latitude.
        geo_longitude: New longitude.
        meeting_url: New online meeting URL.
        visibility: New visibility (public/private).
    """
    kwargs: dict[str, Any] = {}
    if name is not None:
        kwargs["name"] = name
    if description is not None:
        kwargs["description_md"] = description
    if start_at is not None:
        kwargs["start_at"] = start_at
    if end_at is not None:
        kwargs["end_at"] = end_at
    if timezone is not None:
        kwargs["timezone"] = timezone
    if geo_address_json is not None:
        kwargs["geo_address_json"] = geo_address_json
    if geo_latitude is not None:
        kwargs["geo_latitude"] = geo_latitude
    if geo_longitude is not None:
        kwargs["geo_longitude"] = geo_longitude
    if meeting_url is not None:
        kwargs["meeting_url"] = meeting_url
    if visibility is not None:
        kwargs["visibility"] = visibility

    await ctx.info(f"Updating Luma event {event_id}...")
    try:
        return await provider.update_event(event_id, **kwargs)
    except ProviderError as exc:
        from fastmcp.exceptions import ToolError

        raise ToolError(str(exc)) from exc


@mcp.tool()
async def luma_cancel_event(
    event_id: str,
    ctx: Context,
    provider: LumaProvider = Depends(get_luma_provider),
) -> dict[str, Any]:
    """Cancel a Luma event.

    Args:
        event_id: The Luma event API ID (evt-...).
    """
    await ctx.info(f"Cancelling Luma event {event_id}...")
    try:
        return await provider.cancel_event(event_id)
    except ProviderError as exc:
        from fastmcp.exceptions import ToolError

        raise ToolError(str(exc)) from exc


@mcp.tool(
    annotations={"readOnlyHint": True},
)
async def luma_list_people(
    ctx: Context,
    after: str | None = None,
    limit: int | None = None,
    provider: LumaProvider = Depends(get_luma_provider),
) -> dict[str, Any]:
    """List all people from your Luma calendar.

    Returns contacts with their name, email, event attendance count, and tags.

    Args:
        after: Pagination cursor from a previous response.
        limit: Maximum number of people to return.
    """
    await ctx.info("Fetching Luma people...")
    try:
        return await provider.list_people(after=after, limit=limit)
    except ProviderError as exc:
        from fastmcp.exceptions import ToolError

        raise ToolError(str(exc)) from exc


@mcp.tool(
    annotations={"readOnlyHint": True},
)
async def luma_list_guests(
    event_id: str,
    ctx: Context,
    after: str | None = None,
    limit: int | None = None,
    provider: LumaProvider = Depends(get_luma_provider),
) -> dict[str, Any]:
    """List guests for a Luma event.

    Args:
        event_id: The Luma event API ID (evt-...).
        after: Pagination cursor.
        limit: Maximum number of guests to return.
    """
    await ctx.info(f"Fetching guests for Luma event {event_id}...")
    try:
        return await provider.list_guests(event_id, after=after, limit=limit)
    except ProviderError as exc:
        from fastmcp.exceptions import ToolError

        raise ToolError(str(exc)) from exc
