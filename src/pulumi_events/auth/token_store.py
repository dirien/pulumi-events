"""Persistent token cache with automatic refresh via asyncio.Lock."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import httpx

from pulumi_events.auth.backends import FileTokenBackend, TokenBackend
from pulumi_events.exceptions import AuthenticationError

if TYPE_CHECKING:
    import asyncio

    from pulumi_events.settings import Settings

__all__ = ["TokenStore"]

logger = logging.getLogger(__name__)

_REFRESH_MARGIN_SECONDS = 300  # refresh 5 min before expiry


class TokenStore:
    """Thread-safe OAuth2 token store with pluggable backend and auto-refresh."""

    def __init__(
        self,
        settings: Settings,
        *,
        backend: TokenBackend | None = None,
        lock: asyncio.Lock | None = None,
    ) -> None:
        import asyncio as _asyncio

        self._settings = settings
        self._lock = lock or _asyncio.Lock()
        self._backend = backend or FileTokenBackend(
            settings.token_cache_dir / "meetup_token.json"
        )
        self._token_data: dict[str, object] | None = None
        self._token_data = self._backend.load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_authenticated(self) -> bool:
        """Return True if a token is available (may still be expired)."""
        return self._token_data is not None

    async def get_access_token(self, http: httpx.AsyncClient) -> str:
        """Return a valid access token, refreshing if needed.

        Raises:
            AuthenticationError: When no token is stored or refresh fails.
        """
        async with self._lock:
            if self._token_data is None:
                msg = "Not authenticated — run meetup_login first"
                raise AuthenticationError(msg)

            if self._is_expired():
                await self._refresh(http)

            token = self._token_data.get("access_token")
            if not isinstance(token, str):
                msg = "Corrupt token cache — re-authenticate with meetup_login"
                raise AuthenticationError(msg)
            return token

    def store_token(self, token_data: dict[str, object]) -> None:
        """Persist a new token response (from initial auth or refresh)."""
        token_data["obtained_at"] = time.time()
        self._token_data = token_data
        self._backend.save(token_data)
        logger.info("Meetup token stored via %s", type(self._backend).__name__)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _is_expired(self) -> bool:
        if self._token_data is None:
            return True
        obtained = float(self._token_data.get("obtained_at", 0))
        expires_in = float(self._token_data.get("expires_in", 0))
        return time.time() > obtained + expires_in - _REFRESH_MARGIN_SECONDS

    async def _refresh(self, http: httpx.AsyncClient) -> None:
        # Prefer JWT re-authentication if configured (fully headless)
        if self._settings.meetup_jwt_signing_key.get_secret_value():
            from pulumi_events.auth.jwt_auth import authenticate_jwt

            token_data = await authenticate_jwt(self._settings, http)
            self.store_token(token_data)
            logger.info("Meetup token refreshed via JWT")
            return

        refresh_token = (self._token_data or {}).get("refresh_token")
        if not isinstance(refresh_token, str):
            msg = "No refresh token available — re-authenticate with meetup_login"
            raise AuthenticationError(msg)

        client_id = self._settings.meetup_client_id.get_secret_value()
        client_secret = self._settings.meetup_client_secret.get_secret_value()

        resp = await http.post(
            self._settings.meetup_token_endpoint,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
        if resp.status_code != 200:
            msg = f"Token refresh failed ({resp.status_code}): {resp.text}"
            raise AuthenticationError(msg)

        self.store_token(resp.json())
        logger.info("Meetup token refreshed successfully")

