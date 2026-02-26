"""MeetupProvider — implements EventProvider for Meetup.com."""

from __future__ import annotations

import asyncio
from typing import Any

from pulumi_events.providers.base import ProviderCapability
from pulumi_events.providers.meetup import queries
from pulumi_events.providers.meetup.client import MeetupGraphQLClient

__all__ = ["MeetupProvider"]

DEFAULT_MAX_PAGES = 10


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
            ProviderCapability.LIST_MEMBERS,
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
        return data["groupSearch"]

    async def list_my_groups(self, **kwargs: Any) -> dict[str, Any]:
        data = await self._client.execute(queries.LIST_MY_GROUPS, kwargs)
        return data["self"]["memberships"]

    async def list_all_my_groups(
        self,
        *,
        first: int = 50,
        limit: int | None = None,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> dict[str, Any]:
        """Auto-paginate through all groups the user belongs to."""
        all_edges: list[dict[str, Any]] = []
        cursor: str | None = None

        for _ in range(max_pages):
            variables: dict[str, Any] = {"first": first}
            if cursor is not None:
                variables["after"] = cursor

            data = await self._client.execute(queries.LIST_MY_GROUPS, variables)
            connection = data["self"]["memberships"]
            edges = connection.get("edges", [])
            all_edges.extend(edges)

            if limit is not None and len(all_edges) >= limit:
                all_edges = all_edges[:limit]
                break

            page_info = connection.get("pageInfo", {})
            if not page_info.get("hasNextPage", False):
                break

            cursor = page_info.get("endCursor")
            if not cursor:
                break

        groups = [edge["node"] for edge in all_edges]
        return {"total": len(groups), "groups": groups}

    # ------------------------------------------------------------------
    # Members
    # ------------------------------------------------------------------

    async def list_group_members(self, urlname: str, **kwargs: Any) -> dict[str, Any]:
        variables: dict[str, Any] = {"urlname": urlname, **kwargs}
        data = await self._client.execute(queries.GROUP_MEMBERS, variables)
        return data["groupByUrlname"]["memberships"]

    async def list_all_group_members(
        self,
        urlname: str,
        *,
        first: int = 200,
        status: str | None = None,
        limit: int | None = None,
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> dict[str, Any]:
        """Auto-paginate through all members of a group."""
        all_edges: list[dict[str, Any]] = []
        cursor: str | None = None

        for _ in range(max_pages):
            variables: dict[str, Any] = {"urlname": urlname, "first": first}
            if cursor is not None:
                variables["after"] = cursor
            if status is not None:
                variables["status"] = [status]

            data = await self._client.execute(queries.GROUP_MEMBERS, variables)
            connection = data["groupByUrlname"]["memberships"]
            edges = connection.get("edges", [])
            all_edges.extend(edges)

            if limit is not None and len(all_edges) >= limit:
                all_edges = all_edges[:limit]
                break

            page_info = connection.get("pageInfo", {})
            if not page_info.get("hasNextPage", False):
                break

            cursor = page_info.get("endCursor")
            if not cursor:
                break

        members = [
            {
                "id": edge["node"].get("id"),
                "name": edge["node"].get("name"),
                "city": edge["node"].get("city"),
                "country": edge["node"].get("country"),
                "role": edge.get("metadata", {}).get("role"),
                "status": edge.get("metadata", {}).get("status"),
                "joinTime": edge.get("metadata", {}).get("joinTime"),
            }
            for edge in all_edges
        ]
        return {"total": len(members), "members": members}

    async def get_group_member(self, urlname: str, member_id: str) -> dict[str, Any]:
        variables = {"urlname": urlname, "memberIds": [member_id]}
        data = await self._client.execute(queries.GROUP_MEMBER_BY_ID, variables)
        edges = data["groupByUrlname"]["memberships"]["edges"]
        if not edges:
            from pulumi_events.exceptions import ProviderError

            msg = f"Member {member_id} not found in group {urlname}"
            raise ProviderError(msg)
        edge = edges[0]
        return {**edge["node"], "membership": edge["metadata"]}

    async def find_member_across_groups(
        self,
        member_id: str,
        *,
        concurrency: int = 5,
    ) -> dict[str, Any]:
        """Find a member across all groups the authenticated user belongs to.

        Fetches all user groups, then checks each group for the member in
        parallel (bounded by *concurrency*). Returns the member profile plus
        a list of groups they belong to with per-group membership metadata.
        """
        result = await self.list_all_my_groups()
        groups = result["groups"]

        sem = asyncio.Semaphore(concurrency)
        found_in: list[dict[str, Any]] = []
        member_profile: dict[str, Any] | None = None

        async def _check_group(group: dict[str, Any]) -> None:
            nonlocal member_profile
            async with sem:
                urlname = group["urlname"]
                variables = {"urlname": urlname, "memberIds": [member_id]}
                try:
                    data = await self._client.execute(queries.GROUP_MEMBER_BY_ID, variables)
                except Exception:
                    return
                edges = data["groupByUrlname"]["memberships"]["edges"]
                if edges:
                    edge = edges[0]
                    if member_profile is None:
                        member_profile = edge["node"]
                    found_in.append(
                        {
                            "group_urlname": urlname,
                            "group_name": group.get("name", urlname),
                            "membership": edge["metadata"],
                        }
                    )

        await asyncio.gather(*[_check_group(g) for g in groups])

        if member_profile is None:
            from pulumi_events.exceptions import ProviderError

            msg = f"Member {member_id} not found in any of your {len(groups)} groups"
            raise ProviderError(msg)

        return {**member_profile, "groups": found_in}

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    async def get_event(self, event_id: str) -> dict[str, Any]:
        data = await self._client.execute(queries.EVENT_BY_ID, {"eventId": event_id})
        return data["event"]

    async def search_events(self, **kwargs: Any) -> dict[str, Any]:
        data = await self._client.execute(queries.SEARCH_EVENTS, kwargs)
        return data["eventSearch"]

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
        return data["proNetwork"]

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
        return data["proNetwork"][result_key]


def _check_mutation_errors(result: dict[str, Any]) -> None:
    """Raise MeetupGraphQLError if the mutation response contains errors."""
    from pulumi_events.exceptions import MeetupGraphQLError

    errors = result.get("errors")
    if errors:
        messages = "; ".join(e.get("message", str(e)) for e in errors)
        raise MeetupGraphQLError(f"Mutation failed: {messages}", errors)
