"""Search tools: meetup_search_events, meetup_network_search."""

from __future__ import annotations

from typing import Any, Literal

from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from pulumi_events.exceptions import ProviderError
from pulumi_events.providers.meetup.provider import MeetupProvider
from pulumi_events.server import mcp
from pulumi_events.settings import Settings
from pulumi_events.tools._deps import get_meetup_provider, get_settings

__all__: list[str] = []


@mcp.tool(
    annotations={"readOnlyHint": True},
)
async def meetup_search_events(
    query: str,
    lat: float,
    lon: float,
    ctx: Context,
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
        lat: Latitude for location-based search (required).
        lon: Longitude for location-based search (required).
        start_date: Start of date range (ISO 8601 DateTime).
        end_date: End of date range (ISO 8601 DateTime).
        event_type: Event type filter (e.g. PHYSICAL, ONLINE).
        first: Number of results per page (max 200).
        after: Cursor for pagination.
    """
    search_filter: dict[str, Any] = {"query": query, "lat": lat, "lon": lon}
    if start_date is not None:
        search_filter["startDateRange"] = start_date
    if end_date is not None:
        search_filter["endDateRange"] = end_date
    if event_type is not None:
        search_filter["eventType"] = event_type

    variables: dict[str, Any] = {"filter": search_filter, "first": first}
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
    search_type: Literal["events", "groups", "members"],
    ctx: Context,
    network_urlname: str | None = None,
    query: str | None = None,
    roles: list[str] | None = None,
    events_attended_min: int | None = None,
    sort: str | None = None,
    desc: bool = True,
    first: int = 20,
    after: str | None = None,
    provider: MeetupProvider = Depends(get_meetup_provider),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Search within a Meetup Pro network.

    For member searches, results include metadata (groupsCount,
    eventsAttended, role, isOrganizer). Note: Meetup's sort by
    groupsCount is unreliable — use role filters instead to find
    key members (e.g. roles=["ORGANIZER"]).

    Args:
        search_type: What to search for — events, groups, or members.
        network_urlname: Pro network URL name (defaults to configured setting).
        query: Optional search term (name for members, title for events).
        roles: Member role filter (ORGANIZER, COORGANIZER, MEMBER).
        events_attended_min: Minimum events attended (members only).
        sort: Sort field (members: groupsCount, eventsAttended).
        desc: Sort descending (default True).
        first: Number of results per page.
        after: Cursor for pagination.
    """
    urlname = network_urlname or settings.meetup_pro_network_urlname
    variables: dict[str, Any] = {"search_type": search_type, "first": first}

    if search_type == "members":
        member_filter: dict[str, Any] = {}
        if query is not None:
            member_filter["query"] = query
        if roles is not None:
            member_filter["roles"] = roles
        if events_attended_min is not None:
            member_filter["eventsAttendedMin"] = events_attended_min
        if member_filter:
            variables["filter"] = member_filter
        if sort is not None:
            variables["sort"] = sort
            variables["desc"] = desc
    else:
        if query is not None:
            variables["query"] = query

    if after is not None:
        variables["after"] = after

    await ctx.info(f"Searching {search_type} in network '{urlname}'...")
    try:
        return await provider.network_search(urlname, **variables)
    except ProviderError as exc:
        from fastmcp.exceptions import ToolError

        raise ToolError(str(exc)) from exc
