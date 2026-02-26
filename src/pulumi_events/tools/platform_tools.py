"""Platform-level tools: list_platforms, meetup_login."""

from __future__ import annotations

import webbrowser
from typing import Any

from fastmcp.dependencies import Depends
from fastmcp.server.context import Context

from pulumi_events.auth.oauth import build_auth_url
from pulumi_events.providers.luma.provider import LumaProvider
from pulumi_events.providers.meetup.provider import MeetupProvider
from pulumi_events.server import mcp
from pulumi_events.settings import Settings
from pulumi_events.tools._deps import get_luma_provider, get_meetup_provider, get_settings

__all__: list[str] = []


@mcp.tool(
    annotations={"readOnlyHint": True},
)
async def list_platforms(
    meetup: MeetupProvider = Depends(get_meetup_provider),
    luma: LumaProvider = Depends(get_luma_provider),
) -> dict[str, Any]:
    """List configured event platforms with their authentication status and capabilities."""
    platforms = []
    for provider in (meetup, luma):
        platforms.append(
            {
                "name": provider.name,
                "authenticated": provider.is_authenticated,
                "capabilities": sorted(c.value for c in provider.capabilities),
            }
        )
    return {"platforms": platforms}


@mcp.tool()
async def meetup_login(
    ctx: Context,
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    """Start Meetup OAuth2 login.

    Returns an authorization URL. Open it in a browser to authenticate.
    The redirect goes to the MCP server's ``/auth/meetup/callback`` route,
    which exchanges the code and caches the token automatically.
    """
    url = await build_auth_url(settings.meetup_client_id, settings)
    webbrowser.open(url)
    await ctx.info("Opened browser for Meetup authorization.")
    return {
        "auth_url": url,
        "instruction": (
            "A browser window has been opened. Authorize the app and the server "
            "will automatically receive and cache your token."
        ),
    }
