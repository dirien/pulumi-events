"""Provider registry — central access point for all event providers."""

from __future__ import annotations

from typing import TYPE_CHECKING

__all__ = ["ProviderRegistry"]

if TYPE_CHECKING:
    from pulumi_events.providers.base import EventProvider


class ProviderRegistry:
    """Stores registered providers by name."""

    def __init__(self) -> None:
        self._providers: dict[str, EventProvider] = {}

    def register(self, provider: EventProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> EventProvider | None:
        return self._providers.get(name)

    def all(self) -> dict[str, EventProvider]:
        return dict(self._providers)
