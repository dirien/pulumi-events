"""MeetupProvider — implements EventProvider for Meetup.com."""

from __future__ import annotations

from typing import Any

from pulumi_events.providers.base import ProviderCapability
from pulumi_events.providers.meetup import queries
from pulumi_events.providers.meetup.client import MeetupGraphQLClient

__all__ = ["MeetupProvider"]


class MeetupProvider:
    """Meetup.com adapter implementing the EventProvider protocol."""

    def __init__(self, client: MeetupGraphQLClient) -> None:
        self._client = client

    # ------------------------------------------------------------------
    # Protocol properties
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "meetup"

    @property
    def capabilities(self) -> set[ProviderCapability]:
        return {
            ProviderCapability.SEARCH_EVENTS,
            ProviderCapability.SEARCH_GROUPS,
            ProviderCapability.LIST_GROUPS,
            ProviderCapability.CREATE_EVENT,
            ProviderCapability.EDIT_EVENT,
            ProviderCapability.DELETE_EVENT,
            ProviderCapability.PUBLISH_EVENT,
            ProviderCapability.ANNOUNCE_EVENT,
            ProviderCapability.MANAGE_RSVPS,
            ProviderCapability.CREATE_VENUE,
            ProviderCapability.NETWORK_SEARCH,
            ProviderCapability.USER_PROFILE,
        }

    @property
    def is_authenticated(self) -> bool:
        return self._client.is_authenticated

    # ------------------------------------------------------------------
    # User
    # ------------------------------------------------------------------

    async def get_self(self) -> dict[str, Any]:
        data = await self._client.execute(queries.SELF_QUERY)
        return data["self"]

    # ------------------------------------------------------------------
    # Groups
    # ------------------------------------------------------------------

    async def get_group(self, urlname: str) -> dict[str, Any]:
        data = await self._client.execute(queries.GROUP_BY_URLNAME, {"urlname": urlname})
        return data["groupByUrlname"]

    async def search_groups(self, **kwargs: Any) -> dict[str, Any]:
        data = await self._client.execute(queries.SEARCH_GROUPS, kwargs)
        return data["searchGroups"]

    async def list_my_groups(self, **kwargs: Any) -> dict[str, Any]:
        data = await self._client.execute(queries.LIST_MY_GROUPS, kwargs)
        return data["self"]["memberships"]

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    async def get_event(self, event_id: str) -> dict[str, Any]:
        data = await self._client.execute(queries.EVENT_BY_ID, {"eventId": event_id})
        return data["event"]

    async def search_events(self, **kwargs: Any) -> dict[str, Any]:
        data = await self._client.execute(queries.SEARCH_EVENTS, kwargs)
        return data["searchEvents"]

    async def create_event(self, **kwargs: Any) -> dict[str, Any]:
        data = await self._client.execute(queries.CREATE_EVENT, {"input": kwargs})
        result = data["createEvent"]
        _check_mutation_errors(result)
        return result["event"]

    async def edit_event(self, event_id: str, **kwargs: Any) -> dict[str, Any]:
        kwargs["eventId"] = event_id
        data = await self._client.execute(queries.UPDATE_EVENT, {"input": kwargs})
        result = data["editEvent"]
        _check_mutation_errors(result)
        return result["event"]

    async def event_action(self, event_id: str, action: str) -> dict[str, Any]:
        action_map: dict[str, tuple[str, str]] = {
            "delete": (queries.DELETE_EVENT, "deleteEvent"),
            "publish": (queries.PUBLISH_EVENT, "publishEvent"),
            "announce": (queries.ANNOUNCE_EVENT, "announceEvent"),
            "close_rsvps": (queries.CLOSE_EVENT_RSVPS, "closeEventRsvps"),
            "open_rsvps": (queries.OPEN_EVENT_RSVPS, "openEventRsvps"),
        }
        if action not in action_map:
            msg = f"Unknown action: {action}. Must be one of {list(action_map)}"
            raise ValueError(msg)

        query, result_key = action_map[action]
        data = await self._client.execute(query, {"input": {"eventId": event_id}})
        result = data[result_key]
        _check_mutation_errors(result)
        return result

    # ------------------------------------------------------------------
    # Venues
    # ------------------------------------------------------------------

    async def create_venue(self, **kwargs: Any) -> dict[str, Any]:
        data = await self._client.execute(queries.CREATE_VENUE, {"input": kwargs})
        result = data["createVenue"]
        _check_mutation_errors(result)
        return result["venue"]

    # ------------------------------------------------------------------
    # Network
    # ------------------------------------------------------------------

    async def get_network(self, urlname: str) -> dict[str, Any]:
        data = await self._client.execute(queries.NETWORK_BY_URLNAME, {"urlname": urlname})
        return data["proNetworkByUrlname"]

    async def network_search(self, network_urlname: str, **kwargs: Any) -> dict[str, Any]:
        search_type = kwargs.pop("search_type", "events")
        variables: dict[str, Any] = {"urlname": network_urlname, **kwargs}

        query_map: dict[str, tuple[str, str]] = {
            "events": (queries.NETWORK_SEARCH_EVENTS, "eventsSearch"),
            "groups": (queries.NETWORK_SEARCH_GROUPS, "groupsSearch"),
            "members": (queries.NETWORK_SEARCH_MEMBERS, "membersSearch"),
        }
        if search_type not in query_map:
            msg = f"Unknown search_type: {search_type}. Must be one of {list(query_map)}"
            raise ValueError(msg)

        query, result_key = query_map[search_type]
        data = await self._client.execute(query, variables)
        return data["proNetworkByUrlname"][result_key]


def _check_mutation_errors(result: dict[str, Any]) -> None:
    """Raise MeetupGraphQLError if the mutation response contains errors."""
    from pulumi_events.exceptions import MeetupGraphQLError

    errors = result.get("errors")
    if errors:
        messages = "; ".join(e.get("message", str(e)) for e in errors)
        raise MeetupGraphQLError(f"Mutation failed: {messages}", errors)
