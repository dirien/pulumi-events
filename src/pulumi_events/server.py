"""FastMCP server instance with lifespan and tool/resource registration."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response

from pulumi_events.auth.oauth import exchange_code
from pulumi_events.auth.token_store import TokenStore
from pulumi_events.providers.meetup.client import MeetupGraphQLClient
from pulumi_events.providers.meetup.provider import MeetupProvider
from pulumi_events.providers.registry import ProviderRegistry
from pulumi_events.settings import Settings

logger = logging.getLogger(__name__)

# Lifespan state — filled during startup, read by custom routes
_token_store: TokenStore | None = None
_settings: Settings | None = None


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """Set up shared resources (HTTP client, providers, token store)."""
    global _token_store, _settings

    settings = Settings()
    settings.token_cache_dir.mkdir(parents=True, exist_ok=True)
    _settings = settings

    token_store = TokenStore(settings)
    _token_store = token_store

    async with httpx.AsyncClient(timeout=30.0) as http:
        client = MeetupGraphQLClient(http, token_store, settings)
        provider = MeetupProvider(client)

        registry = ProviderRegistry()
        registry.register(provider)

        logger.info(
            "pulumi-events server ready (meetup auth=%s)",
            provider.is_authenticated,
        )

        yield {
            "providers": {"meetup": provider},
            "registry": registry,
            "settings": settings,
            "token_store": token_store,
        }


mcp = FastMCP(
    "pulumi-events",
    instructions=(
        "MCP server for managing events on Meetup.com. "
        "Use meetup_login to authenticate, then use tools to "
        "search/create/manage events and groups. "
        "Read-only lookups are available as resources "
        "(meetup://self, meetup://group/{urlname}, etc.)."
    ),
    lifespan=app_lifespan,
)


# ---------------------------------------------------------------------------
# Custom HTTP routes (OAuth callback + health)
# ---------------------------------------------------------------------------


@mcp.custom_route("/auth/meetup/callback", methods=["GET"])
async def meetup_callback(request: Request) -> Response:
    """Handle Meetup OAuth2 callback — exchange code for token."""
    code = request.query_params.get("code")
    error = request.query_params.get("error")

    if error:
        return HTMLResponse(f"<h1>OAuth Error</h1><p>{error}</p>", status_code=400)
    if not code:
        return HTMLResponse("<h1>Missing code parameter</h1>", status_code=400)

    try:
        assert _settings is not None  # noqa: S101
        token_data = await exchange_code(
            code, _settings.meetup_client_id, _settings.meetup_client_secret, _settings
        )
        assert _token_store is not None  # noqa: S101
        _token_store.store_token(token_data)
        return HTMLResponse(
            "<html><body>"
            "<h1>Authorized!</h1>"
            "<p>You can close this tab and return to your AI assistant.</p>"
            "</body></html>"
        )
    except Exception:
        logger.exception("OAuth callback failed")
        return HTMLResponse(
            "<h1>Authorization failed</h1><p>Check server logs.</p>",
            status_code=500,
        )


@mcp.custom_route("/health", methods=["GET"])
async def health(_request: Request) -> Response:
    """Health check endpoint."""
    return JSONResponse({"status": "ok"})


# ---------------------------------------------------------------------------
# Import tool and resource modules to trigger @mcp.tool / @mcp.resource
# registration. These must come AFTER mcp is defined to avoid circular imports.
# ---------------------------------------------------------------------------
import pulumi_events.resources.meetup_resources as _res  # noqa: E402
import pulumi_events.tools.event_tools as _evt  # noqa: E402
import pulumi_events.tools.group_tools as _grp  # noqa: E402
import pulumi_events.tools.platform_tools as _plt  # noqa: E402
import pulumi_events.tools.search_tools as _src  # noqa: E402
import pulumi_events.tools.venue_tools as _ven  # noqa: E402

__all__ = [  # keep side-effect imports from being flagged as unused
    "mcp",
    "_res",
    "_evt",
    "_grp",
    "_plt",
    "_src",
    "_ven",
]
