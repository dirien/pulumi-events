"""LumaProvider — implements event management via the Luma REST API."""

from __future__ import annotations

from typing import Any

from pulumi_events.providers.base import ProviderCapability
from pulumi_events.providers.luma.client import LumaClient

__all__ = ["LumaProvider"]


class LumaProvider:
    """Luma event-platform adapter."""

    def __init__(self, client: LumaClient) -> None:
        self._client = client

    # ------------------------------------------------------------------
    # Protocol properties
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "luma"

    @property
    def capabilities(self) -> set[ProviderCapability]:
        return {
            ProviderCapability.LIST_EVENTS,
            ProviderCapability.CREATE_EVENT,
            ProviderCapability.EDIT_EVENT,
            ProviderCapability.CANCEL_EVENT,
            ProviderCapability.LIST_GUESTS,
            ProviderCapability.USER_PROFILE,
            ProviderCapability.LIST_PEOPLE,
        }

    @property
    def is_authenticated(self) -> bool:
        return self._client.is_authenticated

    # ------------------------------------------------------------------
    # User
    # ------------------------------------------------------------------

    async def get_self(self) -> dict[str, Any]:
        data = await self._client.get("/user/get-self")
        return data.get("user", data)

    # ------------------------------------------------------------------
    # Events (calendar-level)
    # ------------------------------------------------------------------

    async def list_events(
        self,
        *,
        after: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List events from the authenticated user's calendar (single page)."""
        params: dict[str, Any] = {}
        if after is not None:
            params["pagination_cursor"] = after
        if limit is not None:
            params["limit"] = limit
        return await self._client.get("/calendar/list-events", params or None)

    async def list_all_events(
        self,
        *,
        limit: int | None = None,
        max_pages: int = 10,
    ) -> list[dict[str, Any]]:
        """Auto-paginate through all events."""
        return await self._client.get_all_pages(
            "/calendar/list-events", max_pages=max_pages, limit=limit
        )

    # ------------------------------------------------------------------
    # Single event
    # ------------------------------------------------------------------

    async def get_event(self, event_id: str) -> dict[str, Any]:
        data = await self._client.get("/event/get", {"api_id": event_id})
        return data.get("event", data)

    async def create_event(self, **kwargs: Any) -> dict[str, Any]:
        data = await self._client.post("/event/create", kwargs)
        return data.get("event", data)

    async def update_event(self, event_id: str, **kwargs: Any) -> dict[str, Any]:
        kwargs["event_id"] = event_id
        data = await self._client.post("/event/update", kwargs)
        return data.get("event", data)

    async def cancel_event(self, event_id: str) -> dict[str, Any]:
        return await self._client.post("/event/cancel", {"event_id": event_id})

    # ------------------------------------------------------------------
    # People
    # ------------------------------------------------------------------

    async def list_people(
        self,
        *,
        after: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List people from the authenticated user's calendar (single page)."""
        params: dict[str, Any] = {}
        if after is not None:
            params["pagination_cursor"] = after
        if limit is not None:
            params["limit"] = limit
        return await self._client.get("/calendar/list-people", params or None)

    async def list_all_people(
        self,
        *,
        limit: int | None = None,
        max_pages: int = 10,
    ) -> list[dict[str, Any]]:
        """Auto-paginate through all people."""
        return await self._client.get_all_pages(
            "/calendar/list-people", max_pages=max_pages, limit=limit
        )

    # ------------------------------------------------------------------
    # Guests
    # ------------------------------------------------------------------

    async def list_guests(
        self,
        event_id: str,
        *,
        after: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """List guests for a specific event (single page)."""
        params: dict[str, Any] = {"event_api_id": event_id}
        if after is not None:
            params["pagination_cursor"] = after
        if limit is not None:
            params["limit"] = limit
        return await self._client.get("/event/get-guests", params)

    async def list_all_guests(
        self,
        event_id: str,
        *,
        limit: int | None = None,
        max_pages: int = 10,
    ) -> list[dict[str, Any]]:
        """Auto-paginate through all guests for an event."""
        return await self._client.get_all_pages(
            "/event/get-guests",
            {"event_api_id": event_id},
            max_pages=max_pages,
            limit=limit,
        )
