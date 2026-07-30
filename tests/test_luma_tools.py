"""Unit tests for Luma tool payload construction and invite-only event features."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastmcp.exceptions import ToolError

from pulumi_events.providers.luma.client import LumaClient
from pulumi_events.providers.luma.provider import LumaProvider
from pulumi_events.settings import Settings
from pulumi_events.tools.luma_tools import (
    GuestInvite,
    RegistrationQuestion,
    _prepare_registration_questions,
    luma_add_host,
    luma_create_event,
    luma_get_event,
    luma_list_ticket_types,
    luma_remove_host,
    luma_send_invites,
    luma_update_event,
    luma_update_host,
)


class StubContext:
    async def info(self, *args: Any, **kwargs: Any) -> None: ...

    async def report_progress(self, *args: Any, **kwargs: Any) -> None: ...


class StubProvider:
    def __init__(self) -> None:
        self.payload: dict[str, Any] = {}
        self.event_id: str | None = None
        self.require_approval_calls: list[tuple[str, bool]] = []

    async def create_event(self, **kwargs: Any) -> dict[str, Any]:
        self.payload = kwargs
        return kwargs

    async def update_event(self, event_id: str, **kwargs: Any) -> dict[str, Any]:
        self.event_id = event_id
        self.payload = kwargs
        return kwargs

    async def get_event(self, event_id: str) -> dict[str, Any]:
        return {"api_id": event_id}

    async def set_require_approval(
        self, event_id: str, require_approval: bool
    ) -> list[dict[str, Any]]:
        self.require_approval_calls.append((event_id, require_approval))
        return [{"id": "ttype-1", "name": "Standard", "require_approval": require_approval}]


def wire_provider(
    captured: list[httpx.Request],
    responses: dict[str, Any] | None = None,
) -> LumaProvider:
    """Provider backed by a MockTransport that routes responses by URL path."""
    routes = {
        "/v1/event/get": {"event": {"api_id": "evt-123"}, "hosts": []},
        **(responses or {}),
    }

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json=routes.get(request.url.path, {}))

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(luma_api_key="test-key")
    return LumaProvider(LumaClient(http, settings))


class TestTintColor:
    async def test_create_explicit_tint_color_wins_over_default(self) -> None:
        provider = StubProvider()
        await luma_create_event(
            name="Test",
            start_at="2026-08-01T16:00:00Z",
            end_at="2026-08-01T18:00:00Z",
            ctx=StubContext(),
            tint_color="#bb2dc7",
            provider=provider,
            settings=Settings(),
        )
        assert provider.payload["tint_color"] == "#bb2dc7"

    async def test_create_applies_configured_default(self) -> None:
        provider = StubProvider()
        await luma_create_event(
            name="Test",
            start_at="2026-08-01T16:00:00Z",
            end_at="2026-08-01T18:00:00Z",
            ctx=StubContext(),
            provider=provider,
            settings=Settings(),
        )
        assert provider.payload["tint_color"] == "#2f2356"

    async def test_create_empty_default_omits_tint_color(self) -> None:
        provider = StubProvider()
        await luma_create_event(
            name="Test",
            start_at="2026-08-01T16:00:00Z",
            end_at="2026-08-01T18:00:00Z",
            ctx=StubContext(),
            provider=provider,
            settings=Settings(luma_default_tint_color=""),
        )
        assert "tint_color" not in provider.payload

    async def test_update_passes_tint_color(self) -> None:
        provider = StubProvider()
        await luma_update_event(
            event_id="evt-123",
            ctx=StubContext(),
            tint_color="#bb2dc7",
            provider=provider,
        )
        assert provider.event_id == "evt-123"
        assert provider.payload == {"tint_color": "#bb2dc7"}

    async def test_update_applies_no_default_tint_color(self) -> None:
        # Partial updates must never clobber a manually-set color with the default.
        provider = StubProvider()
        await luma_update_event(
            event_id="evt-123",
            ctx=StubContext(),
            name="Renamed",
            provider=provider,
        )
        assert provider.payload == {"name": "Renamed"}


class TestRegistrationQuestions:
    def test_auto_generates_id_from_label(self) -> None:
        payload = _prepare_registration_questions(
            [RegistrationQuestion(label="Tell us more about you.", required=True)]
        )
        assert payload == [
            {
                "id": "q-tell-us-more-about-you",
                "label": "Tell us more about you.",
                "required": True,
                "question_type": "text",
            }
        ]

    def test_explicit_id_is_preserved(self) -> None:
        payload = _prepare_registration_questions(
            [RegistrationQuestion(id="q-custom", label="Anything?")]
        )
        assert payload[0]["id"] == "q-custom"

    def test_duplicate_labels_get_unique_ids(self) -> None:
        payload = _prepare_registration_questions(
            [
                RegistrationQuestion(label="Company"),
                RegistrationQuestion(label="Company"),
            ]
        )
        assert [q["id"] for q in payload] == ["q-company", "q-company-2"]

    def test_dropdown_requires_options(self) -> None:
        with pytest.raises(ToolError, match="requires a non-empty 'options'"):
            _prepare_registration_questions(
                [RegistrationQuestion(label="Diet", question_type="dropdown")]
            )

    def test_options_rejected_for_text(self) -> None:
        with pytest.raises(ToolError, match="only valid for dropdown and multi-select"):
            _prepare_registration_questions([RegistrationQuestion(label="Name", options=["a"])])

    def test_too_many_options_rejected(self) -> None:
        with pytest.raises(ToolError, match="at most 250 options"):
            _prepare_registration_questions(
                [
                    RegistrationQuestion(
                        label="Pick",
                        question_type="dropdown",
                        options=[str(i) for i in range(251)],
                    )
                ]
            )

    def test_company_extras_pass_through(self) -> None:
        payload = _prepare_registration_questions(
            [
                RegistrationQuestion(
                    label="Company",
                    question_type="company",
                    collect_job_title=True,
                    job_title_label="Role",
                )
            ]
        )
        assert payload[0]["collect_job_title"] is True
        assert payload[0]["job_title_label"] == "Role"

    def test_company_extras_rejected_for_text(self) -> None:
        with pytest.raises(ToolError, match="only valid for 'company'"):
            _prepare_registration_questions(
                [RegistrationQuestion(label="X", collect_job_title=True)]
            )


class TestCreateInviteOnlyFields:
    async def test_new_fields_reach_the_payload(self) -> None:
        provider = StubProvider()
        await luma_create_event(
            name="Dinner",
            start_at="2026-08-01T16:00:00Z",
            end_at="2026-08-01T18:00:00Z",
            ctx=StubContext(),
            visibility="private",
            max_capacity=12,
            waitlist_status="enabled",
            registration_questions=[
                RegistrationQuestion(label="Tell us more about you.", required=True)
            ],
            show_guest_list=False,
            location_visibility="guests-only",
            name_requirement="first-last",
            phone_number_requirement="required",
            reminders_disabled=True,
            feedback_email_enabled=False,
            provider=provider,
            settings=Settings(),
        )
        assert provider.payload["visibility"] == "private"
        assert provider.payload["max_capacity"] == 12
        assert provider.payload["waitlist_status"] == "enabled"
        assert provider.payload["registration_questions"][0]["id"] == "q-tell-us-more-about-you"
        assert provider.payload["show_guest_list"] is False
        assert provider.payload["location_visibility"] == "guests-only"
        assert provider.payload["name_requirement"] == "first-last"
        assert provider.payload["phone_number_requirement"] == "required"
        assert provider.payload["reminders_disabled"] is True
        assert provider.payload["feedback_email"] == {"enabled": False}

    async def test_require_approval_delegates_to_ticket_types(self) -> None:
        provider = StubProvider()

        async def create_event(**kwargs: Any) -> dict[str, Any]:
            provider.payload = kwargs
            return {"id": "evt-9"}

        provider.create_event = create_event  # type: ignore[method-assign]
        result = await luma_create_event(
            name="Dinner",
            start_at="2026-08-01T16:00:00Z",
            end_at="2026-08-01T18:00:00Z",
            ctx=StubContext(),
            require_approval=True,
            provider=provider,
            settings=Settings(),
        )
        assert provider.require_approval_calls == [("evt-9", True)]
        assert "require_approval" not in provider.payload  # never sent to /events/create
        assert result["ticket_types"] == [
            {"id": "ttype-1", "name": "Standard", "require_approval": True}
        ]

    async def test_slug_length_validated(self) -> None:
        provider = StubProvider()
        with pytest.raises(ToolError, match="between 3 and 50"):
            await luma_create_event(
                name="Dinner",
                start_at="2026-08-01T16:00:00Z",
                end_at="2026-08-01T18:00:00Z",
                ctx=StubContext(),
                slug="ab",
                provider=provider,
                settings=Settings(),
            )

    async def test_feedback_delay_requires_enabled(self) -> None:
        provider = StubProvider()
        with pytest.raises(ToolError, match="feedback_email_enabled"):
            await luma_create_event(
                name="Dinner",
                start_at="2026-08-01T16:00:00Z",
                end_at="2026-08-01T18:00:00Z",
                ctx=StubContext(),
                feedback_email_delay="PT2H",
                provider=provider,
                settings=Settings(),
            )


class TestCreateWire:
    """Full-stack: tool -> provider -> real client -> captured HTTP requests."""

    async def test_create_posts_documented_endpoint_then_fetches_back(self) -> None:
        captured: list[httpx.Request] = []
        provider = wire_provider(
            captured,
            {
                "/v1/events/create": {"id": "evt-123"},
                "/v1/event/get": {
                    "event": {"api_id": "evt-123", "visibility": "private"},
                    "hosts": [{"email": "a@b.c"}],
                },
            },
        )
        result = await luma_create_event(
            name="Test",
            start_at="2026-08-01T16:00:00Z",
            end_at="2026-08-01T18:00:00Z",
            ctx=StubContext(),
            visibility="private",
            max_capacity=12,
            waitlist_status="enabled",
            tint_color="#bb2dc7",
            provider=provider,
            settings=Settings(),
        )
        create, get = captured
        assert create.url.path == "/v1/events/create"
        assert create.headers["x-luma-api-key"] == "test-key"
        body = json.loads(create.content)
        assert body["visibility"] == "private"
        assert body["max_capacity"] == 12
        assert body["waitlist_status"] == "enabled"
        assert body["tint_color"] == "#bb2dc7"
        assert get.url.path == "/v1/event/get"
        assert get.url.params["api_id"] == "evt-123"
        # Response is the fetched-back event with hosts merged in.
        assert result["visibility"] == "private"
        assert result["hosts"] == [{"email": "a@b.c"}]

    async def test_create_require_approval_updates_all_ticket_types(self) -> None:
        captured: list[httpx.Request] = []
        provider = wire_provider(
            captured,
            {
                "/v1/events/create": {"id": "evt-123"},
                "/v1/events/ticket-types/list": {
                    "entries": [
                        {"id": "ttype-1", "name": "Standard", "require_approval": False},
                        {"id": "ttype-2", "name": "VIP", "require_approval": True},
                    ]
                },
                "/v1/events/ticket-types/update": {
                    "id": "ttype-1",
                    "name": "Standard",
                    "require_approval": True,
                },
            },
        )
        result = await luma_create_event(
            name="Test",
            start_at="2026-08-01T16:00:00Z",
            end_at="2026-08-01T18:00:00Z",
            ctx=StubContext(),
            require_approval=True,
            provider=provider,
            settings=Settings(),
        )
        paths = [r.url.path for r in captured]
        # ttype-2 already had approval on, so only ttype-1 is updated.
        assert paths == [
            "/v1/events/create",
            "/v1/events/ticket-types/list",
            "/v1/events/ticket-types/update",
            "/v1/event/get",
        ]
        update_body = json.loads(captured[2].content)
        assert update_body == {"event_ticket_type_id": "ttype-1", "require_approval": True}
        assert result["ticket_types"] == [
            {"id": "ttype-1", "name": "Standard", "require_approval": True},
            {"id": "ttype-2", "name": "VIP", "require_approval": True},
        ]


class TestUpdateWire:
    async def test_update_uses_documented_endpoint_and_event_id(self) -> None:
        captured: list[httpx.Request] = []
        result = await luma_update_event(
            event_id="evt-123",
            ctx=StubContext(),
            tint_color="#bb2dc7",
            suppress_notifications=True,
            provider=wire_provider(captured),
        )
        update, get = captured
        assert update.url.path == "/v1/events/update"
        assert update.headers["x-luma-api-key"] == "test-key"
        assert json.loads(update.content) == {
            "event_id": "evt-123",
            "tint_color": "#bb2dc7",
            "suppress_notifications": True,
        }
        assert get.url.path == "/v1/event/get"
        assert result["api_id"] == "evt-123"

    async def test_update_max_capacity_zero_uncaps(self) -> None:
        captured: list[httpx.Request] = []
        await luma_update_event(
            event_id="evt-123",
            ctx=StubContext(),
            max_capacity=0,
            provider=wire_provider(captured),
        )
        body = json.loads(captured[0].content)
        assert body["max_capacity"] is None

    async def test_update_only_require_approval_skips_event_update(self) -> None:
        captured: list[httpx.Request] = []
        provider = wire_provider(
            captured,
            {
                "/v1/events/ticket-types/list": {
                    "entries": [{"id": "ttype-1", "name": "Standard", "require_approval": True}]
                },
                "/v1/events/ticket-types/update": {
                    "id": "ttype-1",
                    "name": "Standard",
                    "require_approval": False,
                },
            },
        )
        result = await luma_update_event(
            event_id="evt-123",
            ctx=StubContext(),
            require_approval=False,
            provider=provider,
        )
        paths = [r.url.path for r in captured]
        assert paths == [
            "/v1/events/ticket-types/list",
            "/v1/events/ticket-types/update",
            "/v1/event/get",
        ]
        assert json.loads(captured[1].content) == {
            "event_ticket_type_id": "ttype-1",
            "require_approval": False,
        }
        assert result["ticket_types"][0]["require_approval"] is False


class TestGetEvent:
    async def test_hosts_merged_into_event(self) -> None:
        captured: list[httpx.Request] = []
        provider = wire_provider(
            captured,
            {
                "/v1/event/get": {
                    "event": {"api_id": "evt-123", "name": "Dinner"},
                    "hosts": [{"email": "host@example.com", "name": "Host"}],
                },
            },
        )
        result = await luma_get_event(event_id="evt-123", ctx=StubContext(), provider=provider)
        assert result["name"] == "Dinner"
        assert result["hosts"] == [{"email": "host@example.com", "name": "Host"}]


class TestHostTools:
    async def test_add_host_posts_and_returns_hosts(self) -> None:
        captured: list[httpx.Request] = []
        provider = wire_provider(
            captured,
            {
                "/v1/event/get": {
                    "event": {"api_id": "evt-123"},
                    "hosts": [{"email": "cohost@example.com", "name": "Co Host"}],
                },
            },
        )
        result = await luma_add_host(
            event_id="evt-123",
            email="cohost@example.com",
            ctx=StubContext(),
            name="Co Host",
            access_level="manager",
            is_visible=True,
            provider=provider,
        )
        add, get = captured
        assert add.url.path == "/v1/events/hosts/add"
        assert json.loads(add.content) == {
            "event_id": "evt-123",
            "email": "cohost@example.com",
            "name": "Co Host",
            "access_level": "manager",
            "is_visible": True,
        }
        assert get.url.path == "/v1/event/get"
        assert result == {
            "event_id": "evt-123",
            "added_email": "cohost@example.com",
            "hosts": [{"email": "cohost@example.com", "name": "Co Host"}],
        }

    async def test_add_host_omits_unset_fields(self) -> None:
        captured: list[httpx.Request] = []
        await luma_add_host(
            event_id="evt-123",
            email="cohost@example.com",
            ctx=StubContext(),
            provider=wire_provider(captured),
        )
        assert json.loads(captured[0].content) == {
            "event_id": "evt-123",
            "email": "cohost@example.com",
        }

    async def test_update_host_requires_a_change(self) -> None:
        captured: list[httpx.Request] = []
        with pytest.raises(ToolError, match="at least one"):
            await luma_update_host(
                event_id="evt-123",
                email="cohost@example.com",
                ctx=StubContext(),
                provider=wire_provider(captured),
            )
        assert captured == []

    async def test_update_host_posts_changes(self) -> None:
        captured: list[httpx.Request] = []
        await luma_update_host(
            event_id="evt-123",
            email="cohost@example.com",
            ctx=StubContext(),
            access_level="check-in",
            is_visible=False,
            provider=wire_provider(captured),
        )
        assert captured[0].url.path == "/v1/events/hosts/update"
        assert json.loads(captured[0].content) == {
            "event_id": "evt-123",
            "email": "cohost@example.com",
            "access_level": "check-in",
            "is_visible": False,
        }

    async def test_remove_host_posts_and_returns_remaining(self) -> None:
        captured: list[httpx.Request] = []
        result = await luma_remove_host(
            event_id="evt-123",
            email="cohost@example.com",
            ctx=StubContext(),
            provider=wire_provider(captured),
        )
        assert captured[0].url.path == "/v1/events/hosts/remove"
        assert json.loads(captured[0].content) == {
            "event_id": "evt-123",
            "email": "cohost@example.com",
        }
        assert result["removed_email"] == "cohost@example.com"
        assert result["hosts"] == []


class TestListTicketTypes:
    async def test_lists_ticket_types(self) -> None:
        captured: list[httpx.Request] = []
        provider = wire_provider(
            captured,
            {
                "/v1/events/ticket-types/list": {
                    "entries": [{"id": "ttype-1", "name": "Standard", "require_approval": True}]
                },
            },
        )
        result = await luma_list_ticket_types(
            event_id="evt-123", ctx=StubContext(), provider=provider
        )
        assert captured[0].url.path == "/v1/events/ticket-types/list"
        assert captured[0].url.params["event_id"] == "evt-123"
        assert result["total"] == 1
        assert result["ticket_types"][0]["require_approval"] is True


class TestSendInvites:
    """Full-stack: tool -> provider -> real client -> captured HTTP request."""

    async def test_sends_guests_with_names_and_batch_message(self) -> None:
        captured: list[httpx.Request] = []
        result = await luma_send_invites(
            event_id="evt-123",
            guests=[
                GuestInvite(email="a@example.com", name="Ada"),
                GuestInvite(email="b@example.com"),
            ],
            ctx=StubContext(),
            message="See you there",
            provider=wire_provider(captured),
        )
        (request,) = captured
        assert request.url.path == "/v1/events/guests/send-invites"
        assert request.headers["x-luma-api-key"] == "test-key"
        # message is a top-level field, not a per-guest one, and a guest
        # without a name omits the key rather than sending null.
        assert json.loads(request.content) == {
            "event_id": "evt-123",
            "guests": [
                {"email": "a@example.com", "name": "Ada"},
                {"email": "b@example.com"},
            ],
            "message": "See you there",
        }
        assert result == {
            "event_id": "evt-123",
            "invited": 2,
            "emails": ["a@example.com", "b@example.com"],
        }

    async def test_omits_message_when_not_provided(self) -> None:
        captured: list[httpx.Request] = []
        await luma_send_invites(
            event_id="evt-123",
            guests=[GuestInvite(email="a@example.com")],
            ctx=StubContext(),
            provider=wire_provider(captured),
        )
        (request,) = captured
        assert json.loads(request.content) == {
            "event_id": "evt-123",
            "guests": [{"email": "a@example.com"}],
        }

    async def test_empty_guests_rejected(self) -> None:
        captured: list[httpx.Request] = []
        with pytest.raises(ToolError):
            await luma_send_invites(
                event_id="evt-123",
                guests=[],
                ctx=StubContext(),
                provider=wire_provider(captured),
            )
        assert captured == []

    async def test_message_over_200_chars_rejected(self) -> None:
        captured: list[httpx.Request] = []
        with pytest.raises(ToolError):
            await luma_send_invites(
                event_id="evt-123",
                guests=[GuestInvite(email="a@example.com")],
                ctx=StubContext(),
                message="x" * 201,
                provider=wire_provider(captured),
            )
        assert captured == []
