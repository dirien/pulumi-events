"""Resource handlers turn provider and auth failures into JSON errors."""

from __future__ import annotations

import json

import pytest

from pulumi_events.exceptions import AuthenticationError, ProviderError
from pulumi_events.resources.luma_resources import luma_self
from pulumi_events.resources.meetup_resources import meetup_self


class _Failing:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def get_self(self) -> dict[str, object]:
        raise self._exc


@pytest.mark.asyncio
@pytest.mark.parametrize("exc", [AuthenticationError("no key"), ProviderError("boom")])
@pytest.mark.parametrize("handler", [luma_self, meetup_self])
async def test_resource_returns_json_error(handler: object, exc: Exception) -> None:
    result = await handler(provider=_Failing(exc))  # type: ignore[operator]
    assert json.loads(result) == {"error": str(exc)}
