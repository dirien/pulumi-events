"""Unit tests for GoogleProviderWithStaticToken hybrid token verification."""

from __future__ import annotations

import pytest
from fastmcp.server.auth import StaticTokenVerifier

from pulumi_events.server import GoogleProviderWithStaticToken

STATIC_TOKEN = "test-headless-token"  # noqa: S105


def _provider(static_verifier: StaticTokenVerifier | None) -> GoogleProviderWithStaticToken:
    return GoogleProviderWithStaticToken(
        client_id="google-client-id",
        client_secret="google-client-secret",  # noqa: S106
        base_url="http://localhost:8080",
        required_scopes=["openid", "email", "profile"],
        require_authorization_consent=False,
        static_verifier=static_verifier,
    )


def _static_verifier() -> StaticTokenVerifier:
    return StaticTokenVerifier(
        tokens={STATIC_TOKEN: {"client_id": "pulumi-events-client", "scopes": ["full"]}},
    )


class TestGoogleProviderWithStaticToken:
    """Covers the headless bearer-token path layered on top of Google OAuth."""

    @pytest.mark.asyncio
    async def test_static_token_accepted(self) -> None:
        provider = _provider(_static_verifier())
        access = await provider.verify_token(STATIC_TOKEN)
        assert access is not None
        assert access.client_id == "pulumi-events-client"
        assert access.scopes == ["full"]

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
