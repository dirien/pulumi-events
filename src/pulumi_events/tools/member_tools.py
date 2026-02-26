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
    first: int = 20,
    after: str | None = None,
    status: str | None = None,
    provider: MeetupProvider = Depends(get_meetup_provider),
) -> dict[str, Any]:
    """List members of a Meetup group with their roles and join dates.

    Args:
        group_urlname: URL name of the group (e.g. berlin-pulumi-user-group).
        first: Number of results per page (max 200).
        after: Cursor for pagination.
        status: Filter by membership status (ACTIVE, BLOCKED, PENDING).
    """
    variables: dict[str, Any] = {"first": first}
    if after is not None:
        variables["after"] = after
    if status is not None:
        variables["status"] = [status]

    await ctx.info(f"Fetching members of '{group_urlname}'...")
    try:
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
