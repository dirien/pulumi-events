"""Search tools: meetup_search_events, meetup_network_search."""

from __future__ import annotations

from typing import Any, Literal

from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from pulumi_events.exceptions import ProviderError
from pulumi_events.providers.meetup.provider import MeetupProvider
from pulumi_events.server import mcp
from pulumi_events.tools._deps import get_meetup_provider

__all__: list[str] = []


@mcp.tool(
    annotations={"readOnlyHint": True},
)
async def meetup_search_events(
    query: str,
    ctx: Context,
    lat: float | None = None,
    lon: float | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    event_type: str | None = None,
    first: int = 20,
    after: str | None = None,
    provider: MeetupProvider = Depends(get_meetup_provider),
) -> dict[str, Any]:
    """Search Meetup events with optional filters.

    Args:
        query: Search term.
        lat: Latitude for location-based search.
        lon: Longitude for location-based search.
        start_date: Start of date range (ISO 8601 / ZonedDateTime).
        end_date: End of date range (ISO 8601 / ZonedDateTime).
        event_type: Event type filter (e.g. PHYSICAL, ONLINE).
        first: Number of results per page (max 200).
        after: Cursor for pagination.
    """
    variables: dict[str, Any] = {"query": query, "first": first}
    if lat is not None:
        variables["lat"] = lat
    if lon is not None:
        variables["lon"] = lon
    if start_date is not None:
        variables["startDateRange"] = start_date
    if end_date is not None:
        variables["endDateRange"] = end_date
    if event_type is not None:
        variables["eventType"] = event_type
    if after is not None:
        variables["after"] = after

    await ctx.info(f"Searching Meetup events for '{query}'...")
    try:
        return await provider.search_events(**variables)
    except ProviderError as exc:
        from fastmcp.exceptions import ToolError

        raise ToolError(str(exc)) from exc


@mcp.tool(
    annotations={"readOnlyHint": True},
)
async def meetup_network_search(
    network_urlname: str,
    search_type: Literal["events", "groups", "members"],
    ctx: Context,
    query: str | None = None,
    status: str | None = None,
    first: int = 20,
    after: str | None = None,
    provider: MeetupProvider = Depends(get_meetup_provider),
) -> dict[str, Any]:
    """Search within a Meetup Pro network.

    Args:
        network_urlname: The URL name of the Pro network.
        search_type: What to search for — events, groups, or members.
        query: Optional search term.
        status: Event status filter (only for search_type=events).
        first: Number of results per page.
        after: Cursor for pagination.
    """
    variables: dict[str, Any] = {"search_type": search_type, "first": first}
    if query is not None:
        variables["query"] = query
    if status is not None:
        variables["status"] = status
    if after is not None:
        variables["after"] = after

    await ctx.info(f"Searching {search_type} in network '{network_urlname}'...")
    try:
        return await provider.network_search(network_urlname, **variables)
    except ProviderError as exc:
        from fastmcp.exceptions import ToolError

        raise ToolError(str(exc)) from exc
