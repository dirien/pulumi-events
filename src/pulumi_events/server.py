"""FastMCP server instance with lifespan and tool/resource registration."""

from __future__ import annotations

import html
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from fastmcp import FastMCP
from fastmcp.server.auth import StaticTokenVerifier
from fastmcp.server.auth.providers.google import GoogleProvider as GoogleProvider
from fastmcp.server.middleware.caching import ResponseCachingMiddleware
from fastmcp.server.middleware.error_handling import ErrorHandlingMiddleware, RetryMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response

from pulumi_events.auth.oauth import exchange_code
from pulumi_events.auth.token_store import TokenStore
from pulumi_events.providers.luma.client import LumaClient
from pulumi_events.providers.luma.provider import LumaProvider
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

    # Reuse the module-level Settings instance (already created for auth setup).
    settings = _settings
    assert settings is not None  # populated before lifespan runs  # noqa: S101
    settings.token_cache_dir.mkdir(parents=True, exist_ok=True)

    token_store = TokenStore(settings)
    _token_store = token_store

    async with httpx.AsyncClient(timeout=30.0) as http:
        meetup_client = MeetupGraphQLClient(http, token_store, settings)
        meetup_provider = MeetupProvider(meetup_client)

        luma_client = LumaClient(http, settings)
        luma_provider = LumaProvider(luma_client)

        registry = ProviderRegistry()
        registry.register(meetup_provider)
        registry.register(luma_provider)

        logger.info(
            "pulumi-events server ready (meetup auth=%s, luma auth=%s)",
            meetup_provider.is_authenticated,
            luma_provider.is_authenticated,
        )

        yield {
            "providers": {
                "meetup": meetup_provider,
                "luma": luma_provider,
            },
            "registry": registry,
            "settings": settings,
            "token_store": token_store,
        }


_settings = Settings()
_auth: StaticTokenVerifier | GoogleProvider | None = None
if (
    _settings.google_client_id.get_secret_value()
    and _settings.google_client_secret.get_secret_value()
):
    _host = "localhost" if _settings.server_host == "127.0.0.1" else _settings.server_host
    _base_url = f"http://{_host}:{_settings.server_port}"
    _auth = GoogleProvider(
        client_id=_settings.google_client_id.get_secret_value(),
        client_secret=_settings.google_client_secret.get_secret_value(),
        base_url=_base_url,
        required_scopes=[
            "openid",
            "email",
            "profile",
        ],
        require_authorization_consent=False,
    )
elif _settings.auth_token.get_secret_value():
    _auth = StaticTokenVerifier(
        tokens={
            _settings.auth_token.get_secret_value(): {
                "client_id": "pulumi-events-client",
                "scopes": ["full"],
            },
        },
    )

mcp = FastMCP(
    "pulumi-events",
    auth=_auth,
    instructions=(
        "MCP server for managing events on Meetup.com and Luma. "
        "Use meetup_login to authenticate with Meetup. "
        "Luma uses an API key (pre-configured). "
        "Tools prefixed with meetup_ or luma_ target each platform. "
        "Resources: meetup://self, meetup://group/{urlname}, "
        "luma://self, luma://event/{event_id}, etc."
    ),
    lifespan=app_lifespan,
    middleware=[
        ErrorHandlingMiddleware(
            logger=logger,
            include_traceback=False,
            transform_errors=True,
        ),
        RetryMiddleware(
            max_retries=2,
            base_delay=1.0,
            max_delay=10.0,
            retry_exceptions=(ConnectionError, TimeoutError),
        ),
        ResponseCachingMiddleware(
            call_tool_settings={
                "enabled": True,
                "ttl": 300,
                "included_tools": [
                    "luma_list_events",
                    "luma_get_event",
                    "luma_list_people",
                    "luma_list_guests",
                    "meetup_get_event",
                    "meetup_list_group_events",
                    "meetup_search_events",
                    "meetup_search_groups",
                    "meetup_list_my_groups",
                    "meetup_list_group_members",
                    "meetup_get_member",
                    "meetup_find_member",
                    "meetup_network_search",
                    "list_platforms",
                ],
            },
        ),
    ],
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
        safe_error = html.escape(error)
        return HTMLResponse(f"<h1>OAuth Error</h1><p>{safe_error}</p>", status_code=400)
    if not code:
        return HTMLResponse("<h1>Missing code parameter</h1>", status_code=400)

    try:
        if _token_store is None or _settings is None:
            return HTMLResponse(
                "<h1>Server not ready</h1><p>Please try again.</p>", status_code=503
            )
        token_data = await exchange_code(
            code,
            _settings.meetup_client_id.get_secret_value(),
            _settings.meetup_client_secret.get_secret_value(),
            _settings,
        )
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
import pulumi_events.resources.luma_resources as _lres  # noqa: E402
import pulumi_events.resources.meetup_resources as _mres  # noqa: E402
import pulumi_events.tools.event_tools as _evt  # noqa: E402
import pulumi_events.tools.group_tools as _grp  # noqa: E402
import pulumi_events.tools.luma_tools as _ltools  # noqa: E402
import pulumi_events.tools.member_tools as _mem  # noqa: E402
import pulumi_events.tools.platform_tools as _plt  # noqa: E402
import pulumi_events.tools.search_tools as _src  # noqa: E402
import pulumi_events.tools.venue_tools as _ven  # noqa: E402

__all__ = [  # keep side-effect imports from being flagged as unused
    "mcp",
    "_lres",
    "_mres",
    "_evt",
    "_grp",
    "_ltools",
    "_mem",
    "_plt",
    "_src",
    "_ven",
]
