"""Pluggable token storage backends for TokenStore."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Protocol, runtime_checkable

from pydantic import SecretStr

__all__ = ["TokenBackend", "FileTokenBackend", "EnvTokenBackend"]

logger = logging.getLogger(__name__)


@runtime_checkable
class TokenBackend(Protocol):
    """Interface for token persistence."""

    def load(self) -> dict[str, object] | None:
        """Load token data, or return None if unavailable."""
        ...

    def save(self, data: dict[str, object]) -> None:
        """Persist token data."""
        ...


class FileTokenBackend:
    """Read/write token JSON to a local file (default for local dev)."""

    def __init__(self, cache_file: Path) -> None:
        self._cache_file = cache_file

    def load(self) -> dict[str, object] | None:
        if self._cache_file.exists():
            try:
                return json.loads(self._cache_file.read_text())
            except (json.JSONDecodeError, OSError):
                logger.warning("Could not read token cache at %s", self._cache_file)
        return None

    def save(self, data: dict[str, object]) -> None:
        path = self._cache_file
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, indent=2)
        fd, tmp_str = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        tmp = Path(tmp_str)
        try:
            os.fchmod(fd, 0o600)
            os.write(fd, payload.encode())
            os.close(fd)
            tmp.replace(path)
        except:
            os.close(fd)
            tmp.unlink(missing_ok=True)
            raise


class EnvTokenBackend:
    """Load token JSON from an env-provided SecretStr; save is in-memory only.

    Suitable for containerised deployments where the initial token is injected
    via an environment variable and refreshed tokens live in memory for the
    lifetime of the process.
    """

    def __init__(self, token_json: SecretStr) -> None:
        self._initial = token_json
        self._in_memory: dict[str, object] | None = None

    def load(self) -> dict[str, object] | None:
        if self._in_memory is not None:
            return self._in_memory
        raw = self._initial.get_secret_value()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("PULUMI_EVENTS_MEETUP_TOKEN_JSON is not valid JSON")
            return None

    def save(self, data: dict[str, object]) -> None:
        self._in_memory = data
