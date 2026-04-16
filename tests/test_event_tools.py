"""Unit tests for start-time normalization and network-timezone validation.

Regression coverage for the 2026-04-15 network event incident, where 31 of
38 Pro network sub-groups were published at the wrong absolute UTC moment
because the start time was not anchored to a timezone.
"""

from __future__ import annotations

import pytest
from fastmcp.exceptions import ToolError

from pulumi_events.tools.event_tools import (
    _normalize_start_datetime,
    _require_naive_local_datetime,
    _require_network_timezone,
)

# ---------------------------------------------------------------------------
# _normalize_start_datetime
# ---------------------------------------------------------------------------


class TestNormalizeStartDatetime:
    def test_utc_z_passes_through_unchanged(self) -> None:
        assert _normalize_start_datetime("2026-04-15T16:00:00Z") == "2026-04-15T16:00:00Z"

    def test_offset_aware_is_converted_to_utc(self) -> None:
        # 11:00 US/Central (CDT, -05:00) == 16:00 UTC
        assert _normalize_start_datetime("2026-04-15T11:00:00-05:00") == "2026-04-15T16:00:00Z"

    def test_positive_offset_is_converted_to_utc(self) -> None:
        # 18:00 Berlin (CEST, +02:00) == 16:00 UTC
        assert _normalize_start_datetime("2026-04-15T18:00:00+02:00") == "2026-04-15T16:00:00Z"

    def test_naive_datetime_is_rejected(self) -> None:
        # Exactly the footgun that caused the Apr 15 incident.
        with pytest.raises(ToolError, match="no timezone offset"):
            _normalize_start_datetime("2026-04-15T11:00:00")

    def test_naive_datetime_without_seconds_is_rejected(self) -> None:
        with pytest.raises(ToolError, match="no timezone offset"):
            _normalize_start_datetime("2026-04-15T11:00")

    def test_invalid_string_is_rejected(self) -> None:
        with pytest.raises(ToolError, match="not valid ISO 8601"):
            _normalize_start_datetime("tomorrow at noon")

    def test_empty_string_is_rejected(self) -> None:
        with pytest.raises(ToolError, match="not valid ISO 8601"):
            _normalize_start_datetime("")

    def test_fractional_seconds_are_preserved_as_utc(self) -> None:
        # Luma returns microsecond precision; we normalize to whole-second Z form.
        assert _normalize_start_datetime("2026-04-15T16:00:00.000+00:00") == "2026-04-15T16:00:00Z"

    # -- target_timezone (Pro network events) --

    def test_network_event_converts_utc_to_target_timezone(self) -> None:
        # 16:00 UTC == 11:00 CDT (US/Central in summer)
        result = _normalize_start_datetime("2026-05-20T16:00:00Z", target_timezone="US/Central")
        assert result == "2026-05-20T11:00:00"

    def test_network_event_converts_offset_to_target_timezone(self) -> None:
        # 11:00 CDT (-05:00) == 18:00 CEST (Europe/Berlin in summer)
        result = _normalize_start_datetime(
            "2026-05-20T11:00:00-05:00", target_timezone="Europe/Berlin"
        )
        assert result == "2026-05-20T18:00:00"

    def test_network_event_same_timezone_strips_offset(self) -> None:
        # 11:00 CDT → naive 11:00 when target is US/Central
        result = _normalize_start_datetime(
            "2026-05-20T11:00:00-05:00", target_timezone="US/Central"
        )
        assert result == "2026-05-20T11:00:00"

    def test_network_event_naive_still_rejected(self) -> None:
        with pytest.raises(ToolError, match="no timezone offset"):
            _normalize_start_datetime("2026-05-20T11:00:00", target_timezone="US/Central")

    def test_network_event_invalid_timezone_is_rejected(self) -> None:
        with pytest.raises(ToolError, match="Unknown timezone"):
            _normalize_start_datetime("2026-05-20T16:00:00Z", target_timezone="Not/Real")


# ---------------------------------------------------------------------------
# _require_network_timezone
# ---------------------------------------------------------------------------


class TestRequireNetworkTimezone:
    def test_non_network_event_does_not_require_timezone(self) -> None:
        # Single-group event; no network involvement.
        _require_network_timezone(None, None)

    def test_non_network_event_ignores_stray_timezone(self) -> None:
        # Passing a timezone without a network urlname is harmless.
        _require_network_timezone(None, "US/Central")

    def test_network_event_with_timezone_is_allowed(self) -> None:
        _require_network_timezone("pugs", "US/Central")

    def test_network_event_without_timezone_is_rejected(self) -> None:
        # Exactly the combination that broke the Apr 15 network event.
        with pytest.raises(ToolError, match="pro_network_timezone is required"):
            _require_network_timezone("pugs", None)


# ---------------------------------------------------------------------------
# _require_naive_local_datetime
# ---------------------------------------------------------------------------


class TestRequireNaiveLocalDatetime:
    """Meetup's EditEventInput wants naive local wall-clock, not offset-aware.

    Asymmetric with CreateEventInput on purpose — documented here so a
    future refactor doesn't accidentally share a single normalizer between
    the two paths and re-introduce the "Invalid event edit params" error.
    """

    def test_naive_wall_clock_passes_through(self) -> None:
        assert _require_naive_local_datetime("2026-05-13T18:00") == "2026-05-13T18:00"

    def test_naive_with_seconds_passes_through(self) -> None:
        assert _require_naive_local_datetime("2026-05-13T18:00:00") == "2026-05-13T18:00:00"

    def test_utc_z_is_rejected(self) -> None:
        # Exactly the format _normalize_start_datetime produces for create —
        # sending it to edit would trip Meetup's opaque rejection.
        with pytest.raises(ToolError, match="naive local wall-clock"):
            _require_naive_local_datetime("2026-05-13T16:00:00Z")

    def test_offset_aware_is_rejected(self) -> None:
        with pytest.raises(ToolError, match="naive local wall-clock"):
            _require_naive_local_datetime("2026-05-13T18:00:00+02:00")

    def test_invalid_string_is_rejected(self) -> None:
        with pytest.raises(ToolError, match="not valid ISO 8601"):
            _require_naive_local_datetime("not a date")
