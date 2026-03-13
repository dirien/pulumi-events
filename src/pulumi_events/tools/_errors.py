"""Shared error-handling decorator for MCP tool functions."""

from __future__ import annotations

import functools
from collections.abc import Callable, Coroutine
from typing import Any

from fastmcp.exceptions import ToolError

from pulumi_events.exceptions import ProviderError


def handle_provider_errors(
    fn: Callable[..., Coroutine[Any, Any, Any]],
) -> Callable[..., Coroutine[Any, Any, Any]]:
    """Catch :class:`ProviderError` (and ``ValueError``) and re-raise as :class:`ToolError`.

    Apply this decorator to any ``@mcp.tool`` async function that delegates
    to a provider method.  It removes the need for repetitive
    ``try / except ProviderError`` blocks in every tool.
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(*args, **kwargs)
        except ProviderError as exc:
            raise ToolError(str(exc)) from exc
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    return wrapper
