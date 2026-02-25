"""Exception hierarchy for pulumi-events."""

from __future__ import annotations

__all__ = [
    "AuthenticationError",
    "ConfigurationError",
    "MeetupGraphQLError",
    "ProviderError",
    "PulumiEventsError",
]


class PulumiEventsError(Exception):
    """Base exception for all pulumi-events errors."""


class AuthenticationError(PulumiEventsError):
    """Not authenticated or token expired."""


class ProviderError(PulumiEventsError):
    """Base for provider-level errors."""


class MeetupGraphQLError(ProviderError):
    """Meetup GraphQL API returned errors."""

    def __init__(self, message: str, errors: list[dict[str, object]]) -> None:
        super().__init__(message)
        self.errors = errors


class ConfigurationError(PulumiEventsError):
    """Missing or invalid configuration / credentials."""
