"""Luma event tools: list, create, update, cancel, guests, hosts, ticket types."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Literal

import httpx
from fastmcp.dependencies import Depends
from fastmcp.exceptions import ToolError
from fastmcp.server.context import Context
from pydantic import BaseModel, Field

from pulumi_events.exceptions import ProviderError
from pulumi_events.providers.luma.provider import LumaProvider
from pulumi_events.server import mcp
from pulumi_events.settings import Settings
from pulumi_events.tools._deps import get_luma_provider, get_settings
from pulumi_events.tools._errors import handle_provider_errors
from pulumi_events.utils import download_image_to_temp

__all__: list[str] = []

logger = logging.getLogger(__name__)


class GuestInvite(BaseModel):
    """A person to invite to a Luma event."""

    email: str = Field(description="Email address of the person to invite.")
    name: str | None = Field(
        default=None,
        description=(
            "Display name for the guest. Ignored if the person already has a "
            "name on their Luma account."
        ),
    )


QuestionType = Literal[
    "text",
    "long-text",
    "dropdown",
    "multi-select",
    "url",
    "phone-number",
    "company",
    "agree-check",
    "linkedin",
    "twitter",
    "instagram",
    "github",
    "youtube",
    "telegram",
]

_OPTION_QUESTION_TYPES = {"dropdown", "multi-select"}
_MAX_QUESTION_OPTIONS = 250


class RegistrationQuestion(BaseModel):
    """A registration-form question for a Luma event."""

    label: str = Field(description="Question text shown to registrants.")
    required: bool = Field(default=False, description="Whether an answer is mandatory.")
    question_type: QuestionType = Field(
        default="text",
        description=(
            "Question kind. 'dropdown' and 'multi-select' also need 'options'. "
            "Luma's 'terms' type (rich-text terms with signature) is not "
            "supported via this tool."
        ),
    )
    id: str | None = Field(
        default=None,
        description=(
            "Stable question ID (Luma requires one; auto-generated from the "
            "label when omitted). When updating an event, reuse the IDs "
            "returned by luma_get_event to edit questions in place."
        ),
    )
    options: list[str] | None = Field(
        default=None,
        description="Choices for dropdown/multi-select questions (max 250).",
    )
    collect_job_title: bool | None = Field(
        default=None,
        description="For 'company' questions only: also collect the job title.",
    )
    job_title_label: str | None = Field(
        default=None,
        description="For 'company' questions only: custom label for the job title field.",
    )


def _question_id_from_label(label: str, index: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:40].rstrip("-")
    return f"q-{slug}" if slug else f"q-{index + 1}"


def _prepare_registration_questions(
    questions: list[RegistrationQuestion],
) -> list[dict[str, Any]]:
    """Validate questions and build the Luma payload, auto-generating IDs.

    Luma rejects questions without an ``id`` ("Invalid input"), so a stable
    slug is derived from the label when the caller does not supply one.
    """
    payload: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for i, q in enumerate(questions):
        if q.question_type in _OPTION_QUESTION_TYPES:
            if not q.options:
                raise ToolError(
                    f"Registration question '{q.label}': question_type "
                    f"'{q.question_type}' requires a non-empty 'options' list."
                )
            if len(q.options) > _MAX_QUESTION_OPTIONS:
                raise ToolError(
                    f"Registration question '{q.label}': at most "
                    f"{_MAX_QUESTION_OPTIONS} options are allowed."
                )
        elif q.options is not None:
            raise ToolError(
                f"Registration question '{q.label}': 'options' is only valid "
                "for dropdown and multi-select questions."
            )
        if q.question_type != "company" and (
            q.collect_job_title is not None or q.job_title_label is not None
        ):
            raise ToolError(
                f"Registration question '{q.label}': collect_job_title and "
                "job_title_label are only valid for 'company' questions."
            )

        qid = q.id or _question_id_from_label(q.label, i)
        base, n = qid, 2
        while qid in seen_ids:
            qid = f"{base}-{n}"
            n += 1
        seen_ids.add(qid)

        item: dict[str, Any] = {
            "id": qid,
            "label": q.label,
            "required": q.required,
            "question_type": q.question_type,
        }
        if q.options is not None:
            item["options"] = q.options
        if q.collect_job_title is not None:
            item["collect_job_title"] = q.collect_job_title
        if q.job_title_label is not None:
            item["job_title_label"] = q.job_title_label
        payload.append(item)
    return payload


def _apply_optional_event_fields(
    payload: dict[str, Any],
    *,
    max_capacity: int | None,
    waitlist_status: str | None,
    registration_questions: list[RegistrationQuestion] | None,
    show_guest_list: bool | None,
    slug: str | None,
    location_visibility: str | None,
    name_requirement: str | None,
    phone_number_requirement: str | None,
    reminders_disabled: bool | None,
    feedback_email_enabled: bool | None,
    feedback_email_delay: str | None,
) -> None:
    """Validate and merge the shared optional create/update fields into *payload*."""
    if max_capacity is not None:
        if max_capacity < 0:
            raise ToolError("max_capacity must be >= 0 (0 removes the capacity limit).")
        payload["max_capacity"] = max_capacity if max_capacity > 0 else None
    if waitlist_status is not None:
        payload["waitlist_status"] = waitlist_status
    if registration_questions is not None:
        payload["registration_questions"] = _prepare_registration_questions(registration_questions)
    if show_guest_list is not None:
        payload["show_guest_list"] = show_guest_list
    if slug is not None:
        if not 3 <= len(slug) <= 50:
            raise ToolError("slug must be between 3 and 50 characters.")
        payload["slug"] = slug
    if location_visibility is not None:
        payload["location_visibility"] = location_visibility
    if name_requirement is not None:
        payload["name_requirement"] = name_requirement
    if phone_number_requirement is not None:
        payload["phone_number_requirement"] = phone_number_requirement
    if reminders_disabled is not None:
        payload["reminders_disabled"] = reminders_disabled
    if feedback_email_delay is not None and feedback_email_enabled is None:
        raise ToolError("feedback_email_delay requires feedback_email_enabled to be set as well.")
    if feedback_email_enabled is not None:
        feedback: dict[str, Any] = {"enabled": feedback_email_enabled}
        if feedback_email_delay is not None:
            feedback["delay"] = feedback_email_delay
        payload["feedback_email"] = feedback


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
    location, cover image, visibility, require_approval (derived from ticket
    types, refreshed asynchronously), waitlist_status, registration_questions
    (with their IDs), spots_remaining, and the hosts array (visible hosts
    only — hosts with is_visible=false are never returned by the API).

    Note: max_capacity, show_guest_list, name_requirement, and
    phone_number_requirement are write-only in Luma's API and read as null
    here even when set.

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
            "visibility": {"type": "string"},
            "require_approval": {"type": "boolean"},
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
    visibility: Literal["public", "members-only", "private"] = "public",
    cover_image_path: str | None = None,
    cover_image_url: str | None = None,
    tint_color: str | None = None,
    require_approval: bool | None = None,
    max_capacity: int | None = None,
    waitlist_status: Literal["disabled", "enabled"] | None = None,
    registration_questions: list[RegistrationQuestion] | None = None,
    show_guest_list: bool | None = None,
    slug: str | None = None,
    location_visibility: Literal["public", "guests-only"] | None = None,
    name_requirement: Literal["full-name", "first-last"] | None = None,
    phone_number_requirement: Literal["optional", "required"] | None = None,
    reminders_disabled: bool | None = None,
    feedback_email_enabled: bool | None = None,
    feedback_email_delay: str | None = None,
    provider: LumaProvider = Depends(get_luma_provider),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Create a Luma event, including invite-only events (approval, capacity,
    waitlist, registration questions) — no Luma UI steps needed.

    For physical events, ALWAYS look up the Google Maps place ID for the venue
    and pass it as geo_address_json. Do NOT pass raw Meetup venue objects or
    manually constructed address dicts -- they are unreliable with Luma's API.

    Returns the full event fetched back after creation (so most settings can
    be verified from the response). Note two API quirks: the event-level
    require_approval flag is derived from ticket types and refreshed
    asynchronously (may read false for a few seconds), and max_capacity is
    write-only (verify via spots_remaining, also refreshed asynchronously).

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
        visibility: Event visibility -- public, members-only (calendar members
            only), or private (invite/link only).
        cover_image_path: Local file path to a cover image (only useful when
            the MCP server runs on the same machine as the caller). Uploaded
            to Luma CDN automatically.
        cover_image_url: Public HTTP(S) URL of a cover image. The server
            downloads and uploads it to Luma — use this for remote servers.
            Mutually exclusive with ``cover_image_path``.
        tint_color: Theme color for the event page as a hex string
            (e.g. "#bb2dc7"). Luma derives the page theme from it;
            alpha channels are stripped automatically. When omitted, the
            server-configured default (PULUMI_EVENTS_LUMA_DEFAULT_TINT_COLOR)
            is applied.
        require_approval: True gates every registration behind host approval
            (request-to-join). Luma stores this on ticket types, not the event,
            so the server sets it on all of the event's ticket types (new
            events have one "Standard" type). The response's ticket_types list
            confirms the applied state immediately.
        max_capacity: Registration capacity (e.g. 12). Once reached the event
            shows as sold out; combine with waitlist_status="enabled" to
            collect a waitlist. Not returned by GET — check spots_remaining,
            which is populated asynchronously (null for up to ~a minute
            right after creation).
        waitlist_status: "enabled" or "disabled". Only meaningful together
            with max_capacity; overflow registrations join the waitlist.
        registration_questions: Custom registration form questions. Replaces
            Luma's default form. Question IDs are auto-generated when omitted.
        show_guest_list: Whether approved guests can see who else is going.
            WRITE-ONLY via the API — applied, but GET always returns null,
            so it cannot be verified without the Luma UI.
        slug: Custom URL slug (3-50 chars): the event URL becomes
            https://luma.com/<slug>. Must be unique across all of Luma.
        location_visibility: "guests-only" hides the precise address from
            people who have not been approved (they see only city/region).
        name_requirement: "full-name" (single field) or "first-last" (two
            fields). WRITE-ONLY via the API (GET returns null).
        phone_number_requirement: "optional" or "required" phone collection
            at registration. WRITE-ONLY via the API (GET returns null).
        reminders_disabled: True turns off Luma's automatic pre-event
            reminder emails.
        feedback_email_enabled: Whether to send the post-event feedback email.
        feedback_email_delay: ISO 8601 duration after event end (default PT0M,
            max P7D, e.g. "PT2H"). Requires feedback_email_enabled.
    """
    if cover_image_path is not None and cover_image_url is not None:
        raise ToolError("Provide either cover_image_path or cover_image_url, not both.")

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
    tint = tint_color or settings.luma_default_tint_color
    if tint:
        input_data["tint_color"] = tint
    _apply_optional_event_fields(
        input_data,
        max_capacity=max_capacity,
        waitlist_status=waitlist_status,
        registration_questions=registration_questions,
        show_guest_list=show_guest_list,
        slug=slug,
        location_visibility=location_visibility,
        name_requirement=name_requirement,
        phone_number_requirement=phone_number_requirement,
        reminders_disabled=reminders_disabled,
        feedback_email_enabled=feedback_email_enabled,
        feedback_email_delay=feedback_email_delay,
    )

    temp_image: Path | None = None
    image_requested = cover_image_path is not None or cover_image_url is not None
    try:
        if image_requested:
            await ctx.report_progress(0, total=2)
            if cover_image_url is not None:
                await ctx.info(f"Downloading cover image from {cover_image_url}...")
                try:
                    temp_image = await download_image_to_temp(cover_image_url)
                except (ValueError, httpx.HTTPError) as exc:
                    raise ToolError(f"Failed to download cover_image_url: {exc}") from exc
                image_path = temp_image
            else:
                assert cover_image_path is not None  # noqa: S101 — narrowed by image_requested
                image_path = Path(cover_image_path)

            await ctx.info("Uploading cover image to Luma CDN...")
            cover_url = await provider.upload_image(image_path)
            input_data["cover_url"] = cover_url
            await ctx.report_progress(1, total=2)

        await ctx.info(f"Creating Luma event '{name}'...")
        created = await provider.create_event(**input_data)
        event_id = created.get("api_id") or created.get("id")
        if not event_id:
            return created

        ticket_types: list[dict[str, Any]] | None = None
        if require_approval is not None:
            await ctx.info("Setting require_approval on ticket types...")
            try:
                ticket_types = await provider.set_require_approval(event_id, require_approval)
            except (ProviderError, KeyError) as exc:
                raise ToolError(
                    f"Event {event_id} was created, but setting require_approval failed: {exc}"
                ) from exc

        try:
            result = await provider.get_event(event_id)
        except ProviderError as exc:
            raise ToolError(
                f"Event {event_id} was created, but fetching it back failed: {exc}"
            ) from exc
        if ticket_types is not None:
            result = {**result, "ticket_types": ticket_types}

        if image_requested:
            await ctx.report_progress(2, total=2)
        return result
    finally:
        if temp_image is not None:
            temp_image.unlink(missing_ok=True)


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
    visibility: Literal["public", "members-only", "private"] | None = None,
    cover_image_path: str | None = None,
    cover_image_url: str | None = None,
    tint_color: str | None = None,
    require_approval: bool | None = None,
    max_capacity: int | None = None,
    waitlist_status: Literal["disabled", "enabled"] | None = None,
    registration_questions: list[RegistrationQuestion] | None = None,
    show_guest_list: bool | None = None,
    slug: str | None = None,
    location_visibility: Literal["public", "guests-only"] | None = None,
    name_requirement: Literal["full-name", "first-last"] | None = None,
    phone_number_requirement: Literal["optional", "required"] | None = None,
    reminders_disabled: bool | None = None,
    feedback_email_enabled: bool | None = None,
    feedback_email_delay: str | None = None,
    suppress_notifications: bool | None = None,
    provider: LumaProvider = Depends(get_luma_provider),
) -> dict[str, Any]:
    """Update a Luma event. Only provided fields are changed.

    Returns the full event fetched back after the update, so changes can be
    verified from the response (see quirks on individual fields below).

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
        visibility: New visibility -- public, members-only, or private.
        cover_image_path: Local file path to a cover image (only useful when
            the MCP server runs on the same machine as the caller). Uploaded
            to Luma CDN automatically.
        cover_image_url: Public HTTP(S) URL of a cover image. The server
            downloads and uploads it to Luma — use this for remote servers.
            Mutually exclusive with ``cover_image_path``.
        tint_color: New theme color for the event page as a hex string
            (e.g. "#bb2dc7"). Luma derives the page theme from it;
            alpha channels are stripped automatically. Unlike create, no
            default is applied — the color only changes when provided.
        require_approval: True gates registration behind host approval;
            False removes the gate. Stored on the event's ticket types (all of
            them), not the event itself; the event-level flag in GET responses
            is derived and may lag a few seconds. The response's ticket_types
            list confirms the applied state immediately.
        max_capacity: New registration capacity. Pass 0 to remove the limit.
            Not returned by GET — verify via spots_remaining (refreshed
            asynchronously, so it may lag a minute or so).
        waitlist_status: "enabled" or "disabled". Only meaningful together
            with a capacity; overflow registrations join the waitlist.
        registration_questions: REPLACES the entire question set. To edit or
            keep existing questions, first call luma_get_event and resend them
            with their existing IDs (answers stay attached to the ID).
        show_guest_list: Whether approved guests can see who else is going.
            WRITE-ONLY via the API (GET always returns null).
        slug: New URL slug (3-50 chars, unique across Luma) — the event URL
            becomes https://luma.com/<slug>.
        location_visibility: "guests-only" hides the precise address from
            unapproved guests; "public" shows it to everyone.
        name_requirement: "full-name" or "first-last". WRITE-ONLY via the API.
        phone_number_requirement: "optional" or "required". WRITE-ONLY via
            the API.
        reminders_disabled: True turns off automatic pre-event reminders.
        feedback_email_enabled: Whether to send the post-event feedback email.
        feedback_email_delay: ISO 8601 duration after event end (default PT0M,
            max P7D). Requires feedback_email_enabled.
        suppress_notifications: True prevents Luma from emailing/notifying
            guests about changes to the event name, time, or location made in
            this update.
    """
    if cover_image_path is not None and cover_image_url is not None:
        raise ToolError("Provide either cover_image_path or cover_image_url, not both.")

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
    if tint_color is not None:
        kwargs["tint_color"] = tint_color
    if suppress_notifications is not None:
        kwargs["suppress_notifications"] = suppress_notifications
    _apply_optional_event_fields(
        kwargs,
        max_capacity=max_capacity,
        waitlist_status=waitlist_status,
        registration_questions=registration_questions,
        show_guest_list=show_guest_list,
        slug=slug,
        location_visibility=location_visibility,
        name_requirement=name_requirement,
        phone_number_requirement=phone_number_requirement,
        reminders_disabled=reminders_disabled,
        feedback_email_enabled=feedback_email_enabled,
        feedback_email_delay=feedback_email_delay,
    )

    temp_image: Path | None = None
    image_requested = cover_image_path is not None or cover_image_url is not None
    try:
        if image_requested:
            await ctx.report_progress(0, total=2)
            if cover_image_url is not None:
                await ctx.info(f"Downloading cover image from {cover_image_url}...")
                try:
                    temp_image = await download_image_to_temp(cover_image_url)
                except (ValueError, httpx.HTTPError) as exc:
                    raise ToolError(f"Failed to download cover_image_url: {exc}") from exc
                image_path = temp_image
            else:
                assert cover_image_path is not None  # noqa: S101 — narrowed by image_requested
                image_path = Path(cover_image_path)

            await ctx.info("Uploading cover image to Luma CDN...")
            cover_url = await provider.upload_image(image_path)
            kwargs["cover_url"] = cover_url
            await ctx.report_progress(1, total=2)

        if kwargs:
            await ctx.info(f"Updating Luma event {event_id}...")
            await provider.update_event(event_id, **kwargs)

        ticket_types: list[dict[str, Any]] | None = None
        if require_approval is not None:
            await ctx.info("Setting require_approval on ticket types...")
            try:
                ticket_types = await provider.set_require_approval(event_id, require_approval)
            except (ProviderError, KeyError) as exc:
                raise ToolError(
                    f"Event {event_id} was updated, but setting require_approval failed: {exc}"
                ) from exc

        result = await provider.get_event(event_id)
        if ticket_types is not None:
            result = {**result, "ticket_types": ticket_types}

        if image_requested:
            await ctx.report_progress(2, total=2)
        return result
    finally:
        if temp_image is not None:
            temp_image.unlink(missing_ok=True)


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
    tags={"luma", "hosts"},
)
@handle_provider_errors
async def luma_add_host(
    event_id: str,
    email: str,
    ctx: Context,
    name: str | None = None,
    access_level: Literal["manager", "check-in", "none"] | None = None,
    is_visible: bool | None = None,
    provider: LumaProvider = Depends(get_luma_provider),
) -> dict[str, Any]:
    """Add a host (e.g. a co-host) to a Luma event by email.

    If the email has no Luma account yet, Luma creates a placeholder profile
    using the given name. Returns the event's host list fetched back after
    the change for verification — note the API only ever returns VISIBLE
    hosts, so a host added with is_visible=false will not appear in it, and
    access_level is not readable back at all.

    Args:
        event_id: The Luma event API ID (evt-...).
        email: Email address of the host to add.
        name: Display name for the host. Ignored if they already have a
            Luma profile.
        access_level: Host permissions — "manager" (full event management,
            the default), "check-in" (can only check guests in), or "none"
            (listed as host without management access).
        is_visible: Whether the host is shown on the event page
            (default true).
    """
    await ctx.info(f"Adding host {email} to Luma event {event_id}...")
    await provider.add_host(
        event_id, email, name=name, access_level=access_level, is_visible=is_visible
    )
    event = await provider.get_event(event_id)
    return {
        "event_id": event_id,
        "added_email": email,
        "hosts": event.get("hosts", []),
    }


@mcp.tool(
    tags={"luma", "hosts"},
    annotations={"idempotentHint": True},
)
@handle_provider_errors
async def luma_update_host(
    event_id: str,
    email: str,
    ctx: Context,
    access_level: Literal["manager", "check-in", "none"] | None = None,
    is_visible: bool | None = None,
    provider: LumaProvider = Depends(get_luma_provider),
) -> dict[str, Any]:
    """Change an existing host's access level and/or visibility on a Luma event.

    The event creator's access level cannot be changed (the API rejects it).
    Returns the visible host list after the change — a host set to
    is_visible=false disappears from it (that is how Luma's API behaves),
    and access_level changes are applied but not readable back.

    Args:
        event_id: The Luma event API ID (evt-...).
        email: Email of the host to update.
        access_level: New permissions — "manager", "check-in", or "none".
        is_visible: Whether the host is shown on the event page.
    """
    if access_level is None and is_visible is None:
        raise ToolError("Provide at least one of access_level or is_visible to change.")
    await ctx.info(f"Updating host {email} on Luma event {event_id}...")
    await provider.update_host(event_id, email, access_level=access_level, is_visible=is_visible)
    event = await provider.get_event(event_id)
    return {
        "event_id": event_id,
        "email": email,
        "hosts": event.get("hosts", []),
    }


@mcp.tool(
    tags={"luma", "hosts"},
)
@handle_provider_errors
async def luma_remove_host(
    event_id: str,
    email: str,
    ctx: Context,
    provider: LumaProvider = Depends(get_luma_provider),
) -> dict[str, Any]:
    """Remove a host from a Luma event by email.

    The event creator cannot be removed (the API rejects it with an error).
    Returns the remaining visible host list for verification.

    Args:
        event_id: The Luma event API ID (evt-...).
        email: Email of the host to remove.
    """
    await ctx.info(f"Removing host {email} from Luma event {event_id}...")
    await provider.remove_host(event_id, email)
    event = await provider.get_event(event_id)
    return {
        "event_id": event_id,
        "removed_email": email,
        "hosts": event.get("hosts", []),
    }


@mcp.tool(
    tags={"luma", "events"},
    annotations={"readOnlyHint": True},
)
@handle_provider_errors
async def luma_list_ticket_types(
    event_id: str,
    ctx: Context,
    provider: LumaProvider = Depends(get_luma_provider),
) -> dict[str, Any]:
    """List a Luma event's ticket types, including their require_approval flags.

    Useful to verify require-approval state immediately: the event-level
    require_approval field is derived from these flags and refreshed
    asynchronously, but this list is always current. Also shows per-type
    capacity, price, and validity window. New events have one free
    "Standard" type.

    Args:
        event_id: The Luma event API ID (evt-...).
    """
    await ctx.info(f"Fetching ticket types for Luma event {event_id}...")
    entries = await provider.list_ticket_types(event_id)
    return {"event_id": event_id, "total": len(entries), "ticket_types": entries}


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


@mcp.tool(
    tags={"luma", "guests"},
    timeout=120.0,
)
@handle_provider_errors
async def luma_send_invites(
    event_id: str,
    guests: list[GuestInvite],
    ctx: Context,
    message: str | None = None,
    provider: LumaProvider = Depends(get_luma_provider),
) -> dict[str, Any]:
    """Send Luma invite emails to people for an event.

    Each guest receives an invitation to the event. People who are not
    already on the guest list are added and invited.

    Args:
        event_id: The Luma event API ID (evt-...).
        guests: People to invite (at least one), each with an ``email`` and an
            optional ``name``.
        message: Optional note included in the invites (max 200 characters).
            Applies to the whole batch, not to individual guests.
    """
    if not guests:
        raise ToolError("Provide at least one guest to invite.")
    if message is not None and len(message) > 200:
        raise ToolError("message must be 200 characters or fewer.")

    payload = [g.model_dump(exclude_none=True) for g in guests]

    await ctx.info(f"Sending {len(payload)} Luma invite(s) for event {event_id}...")
    await provider.send_invites(event_id, payload, message=message)
    return {
        "event_id": event_id,
        "invited": len(payload),
        "emails": [g["email"] for g in payload],
    }
