"""Meetup member tools: list group members, get member details."""

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
async def meetup_list_group_members(
    group_urlname: str,
    ctx: Context,
    status: str | None = None,
    limit: int | None = None,
    all_pages: bool = True,
    provider: MeetupProvider = Depends(get_meetup_provider),
) -> dict[str, Any]:
    """List members of a Meetup group with their roles and join dates.

    Auto-paginates through all results by default.

    Args:
        group_urlname: URL name of the group (e.g. berlin-pulumi-user-group).
        status: Filter by membership status (ACTIVE, BLOCKED, PENDING).
        limit: Maximum total number of members to return.
        all_pages: Fetch all pages automatically (default True).
    """
    await ctx.info(f"Fetching members of '{group_urlname}'...")
    try:
        if all_pages:
            return await provider.list_all_group_members(group_urlname, status=status, limit=limit)
        variables: dict[str, Any] = {"first": 200}
        if status is not None:
            variables["status"] = [status]
        return await provider.list_group_members(group_urlname, **variables)
    except ProviderError as exc:
        from fastmcp.exceptions import ToolError

        raise ToolError(str(exc)) from exc


@mcp.tool(
    annotations={"readOnlyHint": True},
)
async def meetup_get_member(
    group_urlname: str,
    member_id: str,
    ctx: Context,
    provider: MeetupProvider = Depends(get_meetup_provider),
) -> dict[str, Any]:
    """Get details of a specific member within a Meetup group.

    Returns the member's profile (name, bio, city, photo) and their
    membership metadata (role, join time, status) for the given group.

    Args:
        group_urlname: URL name of the group.
        member_id: The Meetup member ID.
    """
    await ctx.info(f"Fetching member {member_id} in '{group_urlname}'...")
    try:
        return await provider.get_group_member(group_urlname, member_id)
    except ProviderError as exc:
        from fastmcp.exceptions import ToolError

        raise ToolError(str(exc)) from exc


@mcp.tool(
    annotations={"readOnlyHint": True},
)
async def meetup_find_member(
    member_id: str,
    ctx: Context,
    provider: MeetupProvider = Depends(get_meetup_provider),
) -> dict[str, Any]:
    """Find a member across all your Meetup groups.

    Searches every group you belong to for the given member ID and returns
    their profile plus a list of shared groups with per-group membership
    metadata (role, join time, status).

    This is useful when you know a member ID but not which group(s) they're in.

    Args:
        member_id: The Meetup member ID to search for.
    """
    await ctx.info(f"Searching for member {member_id} across all your groups...")
    try:
        return await provider.find_member_across_groups(member_id)
    except ProviderError as exc:
        from fastmcp.exceptions import ToolError

        raise ToolError(str(exc)) from exc
