"""Shared error-handling decorator for MCP tool functions."""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Any

from fastmcp.exceptions import ToolError

from pulumi_events.exceptions import AuthenticationError, ProviderError

if TYPE_CHECKING:
    from collections.abc import Callable, Coroutine


def handle_provider_errors(
    fn: Callable[..., Coroutine[Any, Any, Any]],
) -> Callable[..., Coroutine[Any, Any, Any]]:
    """Catch provider errors and re-raise as :class:`ToolError`.

    Handles :class:`AuthenticationError`, :class:`ProviderError`, and
    ``ValueError``.  Apply this decorator to any ``@mcp.tool`` async function
    that delegates to a provider method.  It removes the need for repetitive
    ``try / except`` blocks in every tool.
    """

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return await fn(*args, **kwargs)
        except AuthenticationError as exc:
            msg = f"Authentication required: {exc}"
            raise ToolError(msg) from exc
        except ProviderError as exc:
            raise ToolError(str(exc)) from exc
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    return wrapper
