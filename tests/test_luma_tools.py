"""Unit tests for Luma tool payload construction (tint_color pass-through)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from pulumi_events.providers.luma.client import LumaClient
from pulumi_events.providers.luma.provider import LumaProvider
from pulumi_events.settings import Settings
from pulumi_events.tools.luma_tools import luma_create_event, luma_update_event


class StubContext:
    async def info(self, *args: Any, **kwargs: Any) -> None: ...

    async def report_progress(self, *args: Any, **kwargs: Any) -> None: ...


class StubProvider:
    def __init__(self) -> None:
        self.payload: dict[str, Any] = {}
        self.event_id: str | None = None

    async def create_event(self, **kwargs: Any) -> dict[str, Any]:
        self.payload = kwargs
        return kwargs

    async def update_event(self, event_id: str, **kwargs: Any) -> dict[str, Any]:
        self.event_id = event_id
        self.payload = kwargs
        return kwargs


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


class TestTintColorWire:
    """Full-stack: tool -> provider -> real client -> captured HTTP request."""

    def _provider(self, captured: list[httpx.Request]) -> LumaProvider:
        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            return httpx.Response(200, json={"event": {"api_id": "evt-123"}})

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        settings = Settings(luma_api_key="test-key")
        return LumaProvider(LumaClient(http, settings))

    async def test_update_sends_tint_color_on_the_wire(self) -> None:
        captured: list[httpx.Request] = []
        await luma_update_event(
            event_id="evt-123",
            ctx=StubContext(),
            tint_color="#bb2dc7",
            provider=self._provider(captured),
        )
        (request,) = captured
        assert request.url.path == "/v1/event/update"
        assert request.headers["x-luma-api-key"] == "test-key"
        assert json.loads(request.content) == {
            "event_api_id": "evt-123",
            "tint_color": "#bb2dc7",
        }

    async def test_create_sends_tint_color_on_the_wire(self) -> None:
        captured: list[httpx.Request] = []
        await luma_create_event(
            name="Test",
            start_at="2026-08-01T16:00:00Z",
            end_at="2026-08-01T18:00:00Z",
            ctx=StubContext(),
            tint_color="#bb2dc7",
            provider=self._provider(captured),
            settings=Settings(),
        )
        (request,) = captured
        assert request.url.path == "/v1/event/create"
        assert json.loads(request.content)["tint_color"] == "#bb2dc7"

    async def test_create_sends_default_tint_color_on_the_wire(self) -> None:
        captured: list[httpx.Request] = []
        await luma_create_event(
            name="Test",
            start_at="2026-08-01T16:00:00Z",
            end_at="2026-08-01T18:00:00Z",
            ctx=StubContext(),
            provider=self._provider(captured),
            settings=Settings(),
        )
        (request,) = captured
        assert json.loads(request.content)["tint_color"] == "#2f2356"
