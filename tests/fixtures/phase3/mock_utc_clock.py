"""Mock UTC Clock helper for Phase 3 standing capture tests.

Enables deterministic time simulation across UTC day boundaries, midnight resets,
and monotonic lease checks.
"""
from __future__ import annotations

import datetime
from typing import Optional


class MockUtcClock:
    """Deterministic UTC clock simulator for millisecond timestamps."""

    def __init__(self, initial_ms: Optional[int] = None):
        if initial_ms is None:
            # Default to 2026-09-07 20:00:00 UTC
            dt = datetime.datetime(2026, 9, 7, 20, 0, 0, tzinfo=datetime.timezone.utc)
            self._current_ms = int(dt.timestamp() * 1000)
        else:
            self._current_ms = int(initial_ms)
        self._last_observed_ms = self._current_ms

    def now_ms(self) -> int:
        return self._current_ms

    def now_iso(self) -> str:
        dt = datetime.datetime.fromtimestamp(self._current_ms / 1000.0, tz=datetime.timezone.utc)
        return dt.isoformat()

    def utc_day(self) -> str:
        dt = datetime.datetime.fromtimestamp(self._current_ms / 1000.0, tz=datetime.timezone.utc)
        return dt.strftime("%Y-%m-%d")

    def advance_seconds(self, seconds: float) -> int:
        return self.advance_ms(int(seconds * 1000))

    def advance_minutes(self, minutes: float) -> int:
        return self.advance_ms(int(minutes * 60 * 1000))

    def advance_ms(self, delta_ms: int) -> int:
        self._current_ms += delta_ms
        self._last_observed_ms = max(self._last_observed_ms, self._current_ms)
        return self._current_ms

    def set_time_ms(self, target_ms: int) -> int:
        self._current_ms = int(target_ms)
        return self._current_ms

    def set_to_just_before_midnight(self, date_str: Optional[str] = None) -> int:
        """Sets time to 23:59:59.000 UTC on the current or given day."""
        day = date_str or self.utc_day()
        dt = datetime.datetime.strptime(day + " 23:59:59", "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=datetime.timezone.utc
        )
        self._current_ms = int(dt.timestamp() * 1000)
        return self._current_ms

    def step_across_midnight(self, delta_seconds: float = 2.0) -> int:
        """Moves from just before midnight across the boundary into the next UTC day."""
        self.set_to_just_before_midnight()
        return self.advance_seconds(delta_seconds)

    def resets_at_ms(self) -> int:
        """Calculates next 00:00:00 UTC midnight in milliseconds."""
        dt = datetime.datetime.fromtimestamp(self._current_ms / 1000.0, tz=datetime.timezone.utc)
        next_midnight = (dt + datetime.timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return int(next_midnight.timestamp() * 1000)

    def remaining_until_midnight_parts(self) -> tuple[int, int]:
        """Returns (hours, minutes) until next UTC midnight."""
        diff_ms = max(0, self.resets_at_ms() - self._current_ms)
        total_seconds = diff_ms // 1000
        hours = total_seconds // 3600
        mins = (total_seconds % 3600) // 60
        return int(hours), int(mins)

    def is_clock_regressed(self) -> bool:
        return self._current_ms < self._last_observed_ms
