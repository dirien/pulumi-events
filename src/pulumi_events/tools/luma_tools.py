"""Luma event tools: list, create, update, cancel, guests."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from pulumi_events.providers.luma.provider import LumaProvider
from pulumi_events.server import mcp
from pulumi_events.tools._deps import get_luma_provider
from pulumi_events.tools._errors import handle_provider_errors

__all__: list[str] = []

logger = logging.getLogger(__name__)


def _sanitize_geo_address(geo: dict[str, Any]) -> dict[str, Any]:
    """Strip fields from geo_address_json that Luma rejects.

    LLMs frequently include a ``"type"`` key (e.g. copied from Meetup venue
    data).  Luma only accepts ``"type": "google"`` (for Google Maps place-ID
    lookups); any other value causes a 422 "Invalid input" error.  Rather than
    relying solely on docstrings, we fix it server-side.
    """
    addr = dict(geo)  # shallow copy — don't mutate caller's dict
    addr_type = addr.get("type")
    if addr_type is not None and addr_type != "google":
        logger.info(
            "Stripping invalid 'type' field (%r) from geo_address_json",
            addr_type,
        )
        del addr["type"]
    return addr


@mcp.tool(
    tags={"luma", "events"},
    annotations={"readOnlyHint": True},
    timeout=120.0,
    output_schema={
        "type": "object",
        "properties": {
            "total": {"type": "integer"},
            "events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "api_id": {"type": "string"},
                        "name": {"type": "string"},
                        "start_at": {"type": "string"},
                        "end_at": {"type": "string"},
                        "url": {"type": "string"},
                        "visibility": {"type": "string"},
                    },
                },
            },
        },
    },
)
@handle_provider_errors
async def luma_list_events(
    ctx: Context,
    limit: int | None = None,
    provider: LumaProvider = Depends(get_luma_provider),
) -> dict[str, Any]:
    """List events from your Luma calendar.

    Returns compact summaries with auto-pagination.

    Args:
        limit: Maximum total number of events to return.
    """
    await ctx.info("Fetching Luma events...")
    return await provider.list_all_events(limit=limit)


@mcp.tool(
    tags={"luma", "events"},
    annotations={"readOnlyHint": True},
)
@handle_provider_errors
async def luma_get_event(
    event_id: str,
    ctx: Context,
    provider: LumaProvider = Depends(get_luma_provider),
) -> dict[str, Any]:
    """Get full details of a Luma event by API ID.

    Returns the complete event including name, description, date/time,
    location, cover image, and visibility settings.

    Args:
        event_id: The Luma event API ID (evt-...).
    """
    await ctx.info(f"Fetching Luma event {event_id}...")
    return await provider.get_event(event_id)


@mcp.tool(
    tags={"luma", "events"},
    timeout=120.0,
    output_schema={
        "type": "object",
        "properties": {
            "api_id": {"type": "string"},
            "name": {"type": "string"},
            "start_at": {"type": "string"},
            "end_at": {"type": "string"},
            "url": {"type": "string"},
            "cover_url": {"type": "string"},
        },
    },
)
@handle_provider_errors
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
    cover_image_path: str | None = None,
    provider: LumaProvider = Depends(get_luma_provider),
) -> dict[str, Any]:
    """Create a Luma event.

    For physical events, ALWAYS look up the Google Maps place ID for the venue
    and pass it as geo_address_json. Do NOT pass raw Meetup venue objects or
    manually constructed address dicts -- they are unreliable with Luma's API.

    Args:
        name: Event title.
        start_at: Start time in ISO 8601 format (UTC).
        end_at: End time in ISO 8601 format (UTC).
        description: Event description (markdown supported).
        timezone: Timezone (e.g. America/New_York). Defaults to account timezone.
        geo_address_json: Luma venue address object. Use Google Maps place ID
            (recommended -- most reliable):
            {"type": "google", "place_id": "ChIJ..."}
            First search for the venue to get its place_id, then pass it here.
            Luma resolves the full address, coordinates, and map pin from the
            place_id automatically.
            Fallback -- plain address (less reliable, may fail):
            {"address": "123 Main St", "city": "Munich", "region": "Bavaria",
             "country": "Germany", "full_address": "123 Main St, Munich, Germany"}
            Do NOT include a "type" field with the plain address format.
        geo_latitude: Venue latitude as string (e.g. "48.1351").
        geo_longitude: Venue longitude as string (e.g. "11.5820").
        meeting_url: Online meeting URL (for virtual events).
        visibility: Event visibility -- public or private.
        cover_image_path: Local file path to a cover image. Uploaded to Luma CDN automatically.
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
        input_data["geo_address_json"] = _sanitize_geo_address(geo_address_json)
    if geo_latitude is not None:
        input_data["geo_latitude"] = geo_latitude
    if geo_longitude is not None:
        input_data["geo_longitude"] = geo_longitude
    if meeting_url is not None:
        input_data["meeting_url"] = meeting_url

    if cover_image_path is not None:
        await ctx.report_progress(0, total=2)
        await ctx.info("Uploading cover image to Luma CDN...")
        cover_url = await provider.upload_image(Path(cover_image_path))
        input_data["cover_url"] = cover_url
        await ctx.report_progress(1, total=2)

    await ctx.info(f"Creating Luma event '{name}'...")
    result = await provider.create_event(**input_data)

    if cover_image_path is not None:
        await ctx.report_progress(2, total=2)
    return result


@mcp.tool(
    tags={"luma", "events"},
    timeout=120.0,
    annotations={"idempotentHint": True},
)
@handle_provider_errors
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
    cover_image_path: str | None = None,
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
        geo_address_json: Luma venue address object. Use Google Maps place ID
            (recommended -- most reliable):
            {"type": "google", "place_id": "ChIJ..."}
            First search for the venue to get its place_id, then pass it here.
            Luma resolves the full address automatically.
            Fallback -- plain address (less reliable, may fail):
            {"address": "123 Main St", "city": "Munich", "region": "Bavaria",
             "country": "Germany", "full_address": "123 Main St, Munich, Germany"}
            Do NOT include a "type" field with the plain address format.
        geo_latitude: New latitude as string (e.g. "48.1351").
        geo_longitude: New longitude as string (e.g. "11.5820").
        meeting_url: New online meeting URL.
        visibility: New visibility (public/private).
        cover_image_path: Local file path to a cover image. Uploaded to Luma CDN automatically.
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
        kwargs["geo_address_json"] = _sanitize_geo_address(geo_address_json)
    if geo_latitude is not None:
        kwargs["geo_latitude"] = geo_latitude
    if geo_longitude is not None:
        kwargs["geo_longitude"] = geo_longitude
    if meeting_url is not None:
        kwargs["meeting_url"] = meeting_url
    if visibility is not None:
        kwargs["visibility"] = visibility

    if cover_image_path is not None:
        await ctx.report_progress(0, total=2)
        await ctx.info("Uploading cover image to Luma CDN...")
        cover_url = await provider.upload_image(Path(cover_image_path))
        kwargs["cover_url"] = cover_url
        await ctx.report_progress(1, total=2)

    await ctx.info(f"Updating Luma event {event_id}...")
    result = await provider.update_event(event_id, **kwargs)

    if cover_image_path is not None:
        await ctx.report_progress(2, total=2)
    return result


@mcp.tool(
    tags={"luma", "events"},
)
@handle_provider_errors
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
    return await provider.cancel_event(event_id)


@mcp.tool(
    tags={"luma", "people"},
    annotations={"readOnlyHint": True},
    timeout=120.0,
)
@handle_provider_errors
async def luma_list_people(
    ctx: Context,
    limit: int | None = None,
    provider: LumaProvider = Depends(get_luma_provider),
) -> dict[str, Any]:
    """List all people from your Luma calendar.

    Returns contacts with their name, email, event attendance count, and tags.

    Args:
        limit: Maximum total number of people to return.
    """
    await ctx.info("Fetching Luma people...")
    return await provider.list_all_people(limit=limit)


@mcp.tool(
    tags={"luma", "guests"},
    annotations={"readOnlyHint": True},
    timeout=120.0,
)
@handle_provider_errors
async def luma_list_guests(
    event_id: str,
    ctx: Context,
    limit: int | None = None,
    provider: LumaProvider = Depends(get_luma_provider),
) -> dict[str, Any]:
    """List guests for a Luma event.

    Args:
        event_id: The Luma event API ID (evt-...).
        limit: Maximum total number of guests to return.
    """
    await ctx.info(f"Fetching guests for Luma event {event_id}...")
    return await provider.list_all_guests(event_id, limit=limit)
