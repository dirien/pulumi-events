"""Shared dependency factories for tool injection."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastmcp.server.dependencies import get_context

if TYPE_CHECKING:
    from pulumi_events.auth.token_store import TokenStore
    from pulumi_events.providers.luma.provider import LumaProvider
    from pulumi_events.providers.meetup.provider import MeetupProvider
    from pulumi_events.settings import Settings

__all__ = ["get_luma_provider", "get_meetup_provider", "get_settings", "get_token_store"]


def _lifespan_ctx() -> dict[str, Any]:
    ctx = get_context()
    return ctx.request_context.lifespan_context


async def get_luma_provider() -> LumaProvider:
    """Resolve the LumaProvider from the lifespan context."""
    return _lifespan_ctx()["providers"]["luma"]


async def get_meetup_provider() -> MeetupProvider:
    """Resolve the MeetupProvider from the lifespan context."""
    return _lifespan_ctx()["providers"]["meetup"]


async def get_settings() -> Settings:
    """Resolve Settings from the lifespan context."""
    return _lifespan_ctx()["settings"]


async def get_token_store() -> TokenStore:
    """Resolve TokenStore from the lifespan context."""
    return _lifespan_ctx()["token_store"]
