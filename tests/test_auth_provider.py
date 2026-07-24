"""Unit tests for GoogleProviderWithStaticToken hybrid token verification."""

from __future__ import annotations

import pytest
from fastmcp.server.auth import StaticTokenVerifier

from pulumi_events.server import GoogleProviderWithStaticToken

STATIC_TOKEN = "test-headless-token"  # noqa: S105
# Mirrors server.py: the static token must carry the scopes the provider requires.
REQUIRED_SCOPES = ["openid", "email", "profile"]
STATIC_SCOPES = ["openid", "email", "profile"]


def _provider(static_verifier: StaticTokenVerifier | None) -> GoogleProviderWithStaticToken:
    return GoogleProviderWithStaticToken(
        client_id="google-client-id",
        client_secret="google-client-secret",  # noqa: S106
        base_url="http://localhost:8080",
        required_scopes=REQUIRED_SCOPES,
        require_authorization_consent=False,
        static_verifier=static_verifier,
    )


def _static_verifier() -> StaticTokenVerifier:
    return StaticTokenVerifier(
        tokens={STATIC_TOKEN: {"client_id": "pulumi-events-client", "scopes": STATIC_SCOPES}},
    )


class TestGoogleProviderWithStaticToken:
    """Covers the headless bearer-token path layered on top of Google OAuth."""

    @pytest.mark.asyncio
    async def test_static_token_accepted(self) -> None:
        provider = _provider(_static_verifier())
        access = await provider.verify_token(STATIC_TOKEN)
        assert access is not None
        assert access.client_id == "pulumi-events-client"
        # Regression: the static token's scopes must cover required_scopes, or
        # RequireAuthMiddleware rejects it with 403 insufficient_scope at runtime
        # even though verify_token() returns a token here.
        assert set(REQUIRED_SCOPES).issubset(access.scopes)

    @pytest.mark.asyncio
    async def test_unknown_token_falls_through_to_google(self) -> None:
        provider = _provider(_static_verifier())
        # Not the static token and not a Google-issued JWT -> rejected by the fallback.
        access = await provider.verify_token("not-the-static-token")
        assert access is None

    @pytest.mark.asyncio
    async def test_no_static_verifier_uses_google_only(self) -> None:
        provider = _provider(None)
        access = await provider.verify_token(STATIC_TOKEN)
        assert access is None
