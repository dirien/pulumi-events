"""Async GraphQL client for the Meetup API with automatic token refresh."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from pulumi_events.exceptions import MeetupGraphQLError

if TYPE_CHECKING:
    import httpx

    from pulumi_events.auth.token_store import TokenStore
    from pulumi_events.settings import Settings

__all__ = ["MeetupGraphQLClient"]

logger = logging.getLogger(__name__)


class MeetupGraphQLClient:
    """Low-level async GraphQL transport for Meetup."""

    def __init__(
        self,
        http: httpx.AsyncClient,
        token_store: TokenStore,
        settings: Settings,
    ) -> None:
        self._http = http
        self._token_store = token_store
        self._settings = settings

    @property
    def is_authenticated(self) -> bool:
        return self._token_store.is_authenticated

    async def execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query/mutation and return the ``data`` dict.

        Raises:
            MeetupGraphQLError: If the response contains ``errors``.
        """
        token = await self._token_store.get_access_token(self._http)
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        resp = await self._http.post(
            self._settings.meetup_graphql_endpoint,
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        body = resp.json()

        if "errors" in body:
            errors = body["errors"]
            messages = "; ".join(e.get("message", str(e)) for e in errors)
            msg = f"Meetup GraphQL errors: {messages}"
            raise MeetupGraphQLError(msg, errors)

        return body.get("data", {})
