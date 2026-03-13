"""Async GraphQL client for the Meetup API with automatic token refresh."""

from __future__ import annotations

import asyncio
import logging
import time
import webbrowser
from typing import TYPE_CHECKING, Any

import anyio
import httpx

from pulumi_events.auth.oauth import build_auth_url
from pulumi_events.exceptions import AuthenticationError, MeetupGraphQLError

if TYPE_CHECKING:
    from pathlib import Path

    from pulumi_events.auth.token_store import TokenStore
    from pulumi_events.settings import Settings

__all__ = ["MeetupGraphQLClient"]

logger = logging.getLogger(__name__)

_AUTH_POLL_INTERVAL = 1.0
_AUTH_TIMEOUT = 120.0

# Retry settings for transient HTTP errors (429 rate-limit and 5xx server errors).
_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 1.0  # seconds; actual delays are 1s, 2s, 4s


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

    @property
    def endpoint_v2(self) -> str:
        """The Meetup ``gql2`` endpoint URL for v2 GraphQL operations."""
        return self._settings.meetup_graphql_endpoint_v2

    async def _ensure_authenticated(self) -> str:
        """Return a valid access token, auto-opening browser if configured."""
        try:
            return await self._token_store.get_access_token(self._http)
        except AuthenticationError:
            if not self._settings.auto_open_browser:
                raise

        # Local mode — open browser and wait for OAuth callback
        logger.info("Not authenticated — opening browser for Meetup login")
        url = await build_auth_url(
            self._settings.meetup_client_id.get_secret_value(), self._settings
        )
        webbrowser.open(url)

        # Use monotonic clock for accurate wall-clock timeout measurement.
        deadline = time.monotonic() + _AUTH_TIMEOUT
        while time.monotonic() < deadline:
            await asyncio.sleep(_AUTH_POLL_INTERVAL)
            if self._token_store.is_authenticated:
                return await self._token_store.get_access_token(self._http)

        msg = f"Meetup login timed out after {_AUTH_TIMEOUT:.0f}s. Please try again."
        raise AuthenticationError(msg)

    async def execute(
        self,
        query: str,
        variables: dict[str, Any] | None = None,
        *,
        endpoint: str | None = None,
    ) -> dict[str, Any]:
        """Execute a GraphQL query/mutation and return the ``data`` dict.

        Retries automatically on transient HTTP errors (429 rate-limit and
        5xx server errors) with exponential backoff.

        Args:
            query: GraphQL query or mutation string.
            variables: Optional GraphQL variables.
            endpoint: Override the default GraphQL endpoint URL.

        Raises:
            MeetupGraphQLError: If the response contains ``errors``.
            AuthenticationError: If not authenticated (remote only).
            httpx.HTTPStatusError: If a non-retryable HTTP error persists.
        """
        token = await self._ensure_authenticated()
        payload: dict[str, Any] = {"query": query}
        if variables is not None:
            payload["variables"] = variables

        url = endpoint or self._settings.meetup_graphql_endpoint
        last_exc: httpx.HTTPStatusError | None = None
        resp: httpx.Response | None = None

        for attempt in range(_MAX_RETRIES):
            resp = await self._http.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )

            if resp.status_code == 429 or resp.status_code >= 500:
                last_exc = None
                try:
                    resp.raise_for_status()
                except httpx.HTTPStatusError as exc:
                    last_exc = exc

                if attempt < _MAX_RETRIES - 1:
                    delay = _RETRY_BACKOFF_BASE * (2**attempt)
                    logger.warning(
                        "Meetup API returned %d, retrying in %.1fs (attempt %d/%d)",
                        resp.status_code,
                        delay,
                        attempt + 1,
                        _MAX_RETRIES,
                    )
                    await asyncio.sleep(delay)
                    continue

                assert last_exc is not None  # noqa: S101
                raise last_exc

            resp.raise_for_status()
            break

        assert resp is not None  # noqa: S101 — loop always executes at least once
        body = resp.json()

        if "errors" in body:
            errors = body["errors"]
            messages = "; ".join(e.get("message", str(e)) for e in errors)
            msg = f"Meetup GraphQL errors: {messages}"
            raise MeetupGraphQLError(msg, errors)

        return body.get("data", {})

    async def upload_binary(self, upload_url: str, file_path: Path, content_type: str) -> None:
        """PUT image binary to a Meetup-provided upload URL.

        No ``Authorization`` header is included because Meetup returns
        pre-signed upload URLs from the ``createGroupEventPhoto`` mutation.
        The URL itself embeds the necessary credentials.
        """
        file_bytes = await anyio.Path(file_path).read_bytes()
        logger.info(
            "Uploading %d bytes to %s (Content-Type: %s)",
            len(file_bytes),
            upload_url,
            content_type,
        )
        resp = await self._http.put(
            upload_url,
            content=file_bytes,
            headers={"Content-Type": content_type},
        )
        logger.info(
            "Upload response: %s %s", resp.status_code, resp.text[:500] if resp.text else "(empty)"
        )
        resp.raise_for_status()
