"""Event mutation tools: create, edit, event_action."""

from __future__ import annotations

from typing import Any, Literal

from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from pulumi_events.exceptions import ProviderError
from pulumi_events.providers.meetup.provider import MeetupProvider
from pulumi_events.server import mcp
from pulumi_events.tools._deps import get_meetup_provider

__all__: list[str] = []


@mcp.tool()
async def meetup_create_event(
    group_urlname: str,
    title: str,
    description: str,
    start_date_time: str,
    ctx: Context,
    duration: str = "PT2H",
    event_type: str | None = None,
    venue_id: str | None = None,
    publish_status: str = "DRAFT",
    rsvp_limit: int | None = None,
    question: str | None = None,
    hosts: list[str] | None = None,
    topics: list[str] | None = None,
    pro_network_filter_id: str | None = None,
    pro_network_timezone: str | None = None,
    provider: MeetupProvider = Depends(get_meetup_provider),
) -> dict[str, Any]:
    """Create a Meetup event (defaults to DRAFT for safety).

    Args:
        group_urlname: URL name of the group hosting the event.
        title: Event title.
        description: Event description (HTML supported).
        start_date_time: Start time in ISO 8601 format.
        duration: Duration in ISO 8601 period (default PT2H = 2 hours).
        event_type: PHYSICAL or ONLINE.
        venue_id: Venue ID (from meetup_create_venue).
        publish_status: DRAFT or PUBLISHED (defaults to DRAFT).
        rsvp_limit: Maximum attendees (0 = unlimited).
        question: RSVP question.
        hosts: List of host member IDs.
        topics: List of topic IDs.
        pro_network_filter_id: Pro network filter ID for network-wide events.
        pro_network_timezone: Timezone for Pro network events.
    """
    input_data: dict[str, Any] = {
        "groupUrlname": group_urlname,
        "title": title,
        "description": description,
        "startDateTime": start_date_time,
        "duration": duration,
        "publishStatus": publish_status,
    }
    if event_type is not None:
        input_data["eventType"] = event_type
    if venue_id is not None:
        input_data["venueId"] = venue_id
    if rsvp_limit is not None:
        input_data["rsvpSettings"] = {"rsvpLimit": rsvp_limit}
    if question is not None:
        input_data["question"] = question
    if hosts is not None:
        input_data["hosts"] = hosts
    if topics is not None:
        input_data["topics"] = topics
    if pro_network_filter_id is not None:
        input_data["proNetworkFilterId"] = pro_network_filter_id
    if pro_network_timezone is not None:
        input_data["proNetworkTimezone"] = pro_network_timezone

    await ctx.info(f"Creating event '{title}' in {group_urlname} (status={publish_status})...")
    try:
        return await provider.create_event(**input_data)
    except ProviderError as exc:
        from fastmcp.exceptions import ToolError

        raise ToolError(str(exc)) from exc


@mcp.tool(
    annotations={"idempotentHint": True},
)
async def meetup_edit_event(
    event_id: str,
    ctx: Context,
    title: str | None = None,
    description: str | None = None,
    start_date_time: str | None = None,
    duration: str | None = None,
    event_type: str | None = None,
    venue_id: str | None = None,
    rsvp_limit: int | None = None,
    question: str | None = None,
    hosts: list[str] | None = None,
    topics: list[str] | None = None,
    provider: MeetupProvider = Depends(get_meetup_provider),
) -> dict[str, Any]:
    """Edit an existing Meetup event. Only provided fields are updated.

    Args:
        event_id: The event ID to edit.
        title: New event title.
        description: New description (HTML supported).
        start_date_time: New start time (ISO 8601).
        duration: New duration (ISO 8601 period).
        event_type: PHYSICAL or ONLINE.
        venue_id: New venue ID.
        rsvp_limit: New RSVP limit.
        question: New RSVP question.
        hosts: New list of host member IDs.
        topics: New list of topic IDs.
    """
    kwargs: dict[str, Any] = {}
    if title is not None:
        kwargs["title"] = title
    if description is not None:
        kwargs["description"] = description
    if start_date_time is not None:
        kwargs["startDateTime"] = start_date_time
    if duration is not None:
        kwargs["duration"] = duration
    if event_type is not None:
        kwargs["eventType"] = event_type
    if venue_id is not None:
        kwargs["venueId"] = venue_id
    if rsvp_limit is not None:
        kwargs["rsvpSettings"] = {"rsvpLimit": rsvp_limit}
    if question is not None:
        kwargs["question"] = question
    if hosts is not None:
        kwargs["hosts"] = hosts
    if topics is not None:
        kwargs["topics"] = topics

    await ctx.info(f"Editing event {event_id}...")
    try:
        return await provider.edit_event(event_id, **kwargs)
    except ProviderError as exc:
        from fastmcp.exceptions import ToolError

        raise ToolError(str(exc)) from exc


@mcp.tool()
async def meetup_event_action(
    event_id: str,
    action: Literal["delete", "publish", "announce", "close_rsvps", "open_rsvps"],
    ctx: Context,
    provider: MeetupProvider = Depends(get_meetup_provider),
) -> dict[str, Any]:
    """Perform a lifecycle action on a Meetup event.

    Args:
        event_id: The event ID.
        action: One of: delete, publish, announce, close_rsvps, open_rsvps.
    """
    await ctx.info(f"Performing '{action}' on event {event_id}...")
    try:
        return await provider.event_action(event_id, action)
    except (ProviderError, ValueError) as exc:
        from fastmcp.exceptions import ToolError

        raise ToolError(str(exc)) from exc
