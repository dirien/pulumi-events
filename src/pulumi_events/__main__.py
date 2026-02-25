"""Entry point for ``python -m pulumi_events``."""

from __future__ import annotations

import logging


def main() -> None:
    """Start the pulumi-events MCP server."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    from pulumi_events.server import mcp
    from pulumi_events.settings import Settings

    settings = Settings()
    mcp.run(
        transport="streamable-http",
        host=settings.server_host,
        port=settings.server_port,
    )


if __name__ == "__main__":
    main()
