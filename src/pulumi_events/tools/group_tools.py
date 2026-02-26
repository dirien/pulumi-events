"""Group-related tools: search_groups, list_my_groups."""

from __future__ import annotations

from typing import Any

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
async def meetup_search_groups(
    query: str,
    ctx: Context,
    lat: float | None = None,
    lon: float | None = None,
    first: int = 20,
    after: str | None = None,
    provider: MeetupProvider = Depends(get_meetup_provider),
) -> dict[str, Any]:
    """Search Meetup groups by keyword with optional geo filter.

    Args:
        query: Search term.
        lat: Latitude for location-based search.
        lon: Longitude for location-based search.
        first: Number of results per page (max 200).
        after: Cursor for pagination.
    """
    variables: dict[str, Any] = {"query": query, "first": first}
    if lat is not None:
        variables["lat"] = lat
    if lon is not None:
        variables["lon"] = lon
    if after is not None:
        variables["after"] = after

    await ctx.info(f"Searching Meetup groups for '{query}'...")
    try:
        return await provider.search_groups(**variables)
    except ProviderError as exc:
        from fastmcp.exceptions import ToolError

        raise ToolError(str(exc)) from exc


@mcp.tool(
    annotations={"readOnlyHint": True},
)
async def meetup_list_my_groups(
    ctx: Context,
    limit: int | None = None,
    all_pages: bool = True,
    provider: MeetupProvider = Depends(get_meetup_provider),
) -> list[dict[str, Any]] | dict[str, Any]:
    """List all Meetup groups the authenticated user belongs to.

    Auto-paginates through all results by default.

    Args:
        limit: Maximum total number of groups to return.
        all_pages: Fetch all pages automatically (default True).
    """
    await ctx.info("Fetching your Meetup groups...")
    try:
        if all_pages:
            return await provider.list_all_my_groups(limit=limit)
        return await provider.list_my_groups(first=50)
    except ProviderError as exc:
        from fastmcp.exceptions import ToolError

        raise ToolError(str(exc)) from exc
