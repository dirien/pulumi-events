"""LumaProvider — implements event management via the Luma REST API."""

from __future__ import annotations

from typing import Any

from pulumi_events.providers.base import ProviderCapability
from pulumi_events.providers.luma.client import LumaClient

__all__ = ["LumaProvider"]


def _summarize_event(entry: dict[str, Any]) -> dict[str, Any]:
    """Extract compact event summary from a list-events entry."""
    event = entry.get("event", entry)
    return {
        "api_id": event.get("api_id"),
        "name": event.get("name"),
        "start_at": event.get("start_at"),
        "end_at": event.get("end_at"),
        "url": event.get("url"),
        "visibility": event.get("visibility"),
        "geo_address_json": event.get("geo_address_json"),
    }


def _summarize_person(entry: dict[str, Any]) -> dict[str, Any]:
    """Extract compact person summary from a list-people entry."""
    user = entry.get("user", {})
    return {
        "api_id": entry.get("api_id"),
        "name": user.get("name"),
        "email": user.get("email") or entry.get("email"),
        "avatar_url": user.get("avatar_url"),
        "event_approved_count": entry.get("event_approved_count"),
        "tags": entry.get("tags"),
    }


def _summarize_guest(entry: dict[str, Any]) -> dict[str, Any]:
    """Extract compact guest summary from a get-guests entry."""
    guest = entry.get("guest", entry)
    user = guest.get("user_generated_by") or guest.get("user", {})
    return {
        "api_id": guest.get("api_id"),
        "name": guest.get("name") or user.get("name"),
        "email": guest.get("email") or user.get("email"),
        "approval_status": guest.get("approval_status"),
        "check_in_qr_code": guest.get("check_in_qr_code"),
        "registered_at": guest.get("created_at"),
    }


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
    ) -> dict[str, Any]:
        """Auto-paginate through all events, returning compact summaries."""
        entries = await self._client.get_all_pages(
            "/calendar/list-events", max_pages=max_pages, limit=limit
        )
        return {
            "total": len(entries),
            "events": [_summarize_event(e) for e in entries],
        }

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
    ) -> dict[str, Any]:
        """Auto-paginate through all people, returning compact summaries."""
        entries = await self._client.get_all_pages(
            "/calendar/list-people", max_pages=max_pages, limit=limit
        )
        return {
            "total": len(entries),
            "people": [_summarize_person(e) for e in entries],
        }

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
    ) -> dict[str, Any]:
        """Auto-paginate through all guests for an event."""
        entries = await self._client.get_all_pages(
            "/event/get-guests",
            {"event_api_id": event_id},
            max_pages=max_pages,
            limit=limit,
        )
        return {
            "total": len(entries),
            "guests": [_summarize_guest(e) for e in entries],
        }
