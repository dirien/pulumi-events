"""Unit tests for GoogleProviderWithStaticToken hybrid token verification."""

from __future__ import annotations

import pytest

from pulumi_events.server import GoogleProviderWithStaticToken

STATIC_TOKEN = "test-headless-token"  # noqa: S105


def _provider(*, static_token: str | None) -> GoogleProviderWithStaticToken:
    return GoogleProviderWithStaticToken(
        client_id="google-client-id",
        client_secret="google-client-secret",  # noqa: S106
        base_url="http://localhost:8080",
        required_scopes=["openid", "email", "profile"],
        require_authorization_consent=False,
        static_token=static_token,
    )


class TestGoogleProviderWithStaticToken:
    """Covers the headless bearer-token path layered on top of Google OAuth."""

    @pytest.mark.asyncio
    async def test_static_token_accepted(self) -> None:
        provider = _provider(static_token=STATIC_TOKEN)
        access = await provider.verify_token(STATIC_TOKEN)
        assert access is not None
        assert access.client_id == "pulumi-events-client"
        # Regression: the static token's scopes must cover the provider's
        # required_scopes, or RequireAuthMiddleware rejects it with 403
        # insufficient_scope at runtime even though verify_token() succeeds here.
        # GoogleProvider expands "email"/"profile" into full Google scope URLs,
        # so we assert against the provider's own (expanded) required_scopes.
        assert set(provider.required_scopes).issubset(access.scopes)

    @pytest.mark.asyncio
    async def test_unknown_token_falls_through_to_google(self) -> None:
        provider = _provider(static_token=STATIC_TOKEN)
        # Not the static token and not a Google-issued JWT -> rejected by the fallback.
        access = await provider.verify_token("not-the-static-token")
        assert access is None

    @pytest.mark.asyncio
    async def test_no_static_token_uses_google_only(self) -> None:
        provider = _provider(static_token=None)
        access = await provider.verify_token(STATIC_TOKEN)
        assert access is None
