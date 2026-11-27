"""Entry point for ``python -m pulumi_events``."""

from __future__ import annotations

import logging

_APP_LOGGER = "pulumi-events"
_LOG_FMT = "%(asctime)s %(levelname)-5s %(name)s: %(message)s"


class _UnifyNameFilter(logging.Filter):
    """Rewrite every log record's name so all output uses a single logger name."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.name = _APP_LOGGER
        return True


def main() -> None:
    """Start the pulumi-events MCP server."""
    import fastmcp  # noqa: PLC0415  # deferred so logging is configured first

    # Disable FastMCP's Rich logging so it propagates to root like everything else.
    fastmcp.settings.enable_rich_logging = False

    # Set up a single root handler with a unified format.
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    logging.basicConfig(level=logging.INFO, format=_LOG_FMT)
    for handler in root.handlers:
        handler.addFilter(_UnifyNameFilter())

    # Make the fastmcp logger propagate to root instead of using its own handlers.
    fmcp_logger = logging.getLogger("fastmcp")
    fmcp_logger.handlers.clear()
    fmcp_logger.propagate = True

    # Deferred: importing the server reads settings and registers tools at import time.
    from pulumi_events.server import mcp  # noqa: PLC0415
    from pulumi_events.settings import Settings  # noqa: PLC0415

    settings = Settings()
    mcp.run(
        transport="streamable-http",
        host=settings.server_host,
        port=settings.server_port,
        stateless_http=True,
        uvicorn_config={"log_config": None},
    )


if __name__ == "__main__":
    main()
