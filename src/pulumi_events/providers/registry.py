"""Provider registry — central access point for all event providers."""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = ["ProviderRegistry"]

if TYPE_CHECKING:
    from pulumi_events.providers.base import EventProvider


class ProviderRegistry:
    """Stores registered providers by name."""

    def __init__(self) -> None:
        """Initialise the instance."""
        self._providers: dict[str, EventProvider] = {}

    def register(self, provider: EventProvider) -> None:
        """Register a provider under its name."""
        self._providers[provider.name] = provider

    def get(self, name: str) -> EventProvider | None:
        """Return the provider with the given name, if registered."""
        return self._providers.get(name)

    def all(self) -> dict[str, EventProvider]:
        """Return all registered providers by name."""
        return dict(self._providers)
