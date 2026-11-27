"""Abstract provider protocol and capability enum."""

from __future__ import annotations

import enum
from typing import Any, Protocol, runtime_checkable

__all__ = ["EventProvider", "ProviderCapability"]


class ProviderCapability(enum.Enum):
    """Capabilities a provider can declare."""

    SEARCH_EVENTS = "search_events"
    SEARCH_GROUPS = "search_groups"
    LIST_GROUPS = "list_groups"
    CREATE_EVENT = "create_event"
    EDIT_EVENT = "edit_event"
    DELETE_EVENT = "delete_event"
    PUBLISH_EVENT = "publish_event"
    ANNOUNCE_EVENT = "announce_event"
    MANAGE_RSVPS = "manage_rsvps"
    CREATE_VENUE = "create_venue"
    NETWORK_SEARCH = "network_search"
    USER_PROFILE = "user_profile"
    LIST_EVENTS = "list_events"
    LIST_GUESTS = "list_guests"
    SEND_INVITES = "send_invites"
    CANCEL_EVENT = "cancel_event"
    LIST_MEMBERS = "list_members"
    LIST_PEOPLE = "list_people"


@runtime_checkable
class EventProvider(Protocol):
    """Interface that every event-platform adapter must implement."""

    @property
    def name(self) -> str:
        """Return the provider name."""

    @property
    def capabilities(self) -> set[ProviderCapability]:
        """Return the capabilities this provider supports."""

    @property
    def is_authenticated(self) -> bool:
        """Return whether credentials are configured."""

    async def get_self(self) -> dict[str, Any]:
        """Return the authenticated user profile."""

    async def search_events(self, **kwargs: Any) -> dict[str, Any]:
        """Search events."""

    async def search_groups(self, **kwargs: Any) -> dict[str, Any]:
        """Search groups."""

    async def list_my_groups(self, **kwargs: Any) -> dict[str, Any]:
        """List groups the authenticated user belongs to."""

    async def get_group(self, urlname: str) -> dict[str, Any]:
        """Return a group by URL name."""

    async def get_event(self, event_id: str) -> dict[str, Any]:
        """Return an event by ID."""

    async def create_event(self, **kwargs: Any) -> dict[str, Any]:
        """Create an event."""

    async def edit_event(self, event_id: str, **kwargs: Any) -> dict[str, Any]:
        """Edit an event."""

    async def event_action(self, event_id: str, action: str) -> dict[str, Any]:
        """Apply a lifecycle action to an event."""

    async def create_venue(self, **kwargs: Any) -> dict[str, Any]:
        """Create a venue."""

    async def network_search(self, network_urlname: str, **kwargs: Any) -> dict[str, Any]:
        """Search events across a Pro network."""

    async def get_network(self, urlname: str) -> dict[str, Any]:
        """Return a Pro network by URL name."""
