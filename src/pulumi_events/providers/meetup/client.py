"""Async GraphQL client for the Meetup API with automatic token refresh."""

from __future__ import annotations

import asyncio
import logging
import webbrowser
from typing import TYPE_CHECKING, Any

from pulumi_events.auth.oauth import build_auth_url
from pulumi_events.exceptions import AuthenticationError, MeetupGraphQLError

if TYPE_CHECKING:
    import httpx

    from pulumi_events.auth.token_store import TokenStore
    from pulumi_events.settings import Settings

__all__ = ["MeetupGraphQLClient"]

logger = logging.getLogger(__name__)

_AUTH_POLL_INTERVAL = 1.0  # seconds between token checks
_AUTH_TIMEOUT = 120.0  # max seconds to wait for browser auth


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

    async def _ensure_authenticated(self) -> str:
        """Return a valid access token, triggering browser login if needed."""
        try:
            return await self._token_store.get_access_token(self._http)
        except AuthenticationError:
            pass

        # No token — kick off browser auth automatically
        logger.info("Not authenticated with Meetup — opening browser for login")
        url = await build_auth_url(self._settings.meetup_client_id, self._settings)
        webbrowser.open(url)

        # Poll until the OAuth callback stores a token
        elapsed = 0.0
        while elapsed < _AUTH_TIMEOUT:
            await asyncio.sleep(_AUTH_POLL_INTERVAL)
            elapsed += _AUTH_POLL_INTERVAL
            if self._token_store.is_authenticated:
                return await self._token_store.get_access_token(self._http)

        msg = f"Meetup login timed out after {_AUTH_TIMEOUT:.0f}s. Please try again."
        raise AuthenticationError(msg)

    async def execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query/mutation and return the ``data`` dict.

        Automatically triggers browser-based OAuth login if not authenticated.

        Raises:
            MeetupGraphQLError: If the response contains ``errors``.
        """
        token = await self._ensure_authenticated()
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
