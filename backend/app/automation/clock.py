"""
Injectable Central UTC Clock Boundary (Sections 16, 17)
Provides deterministic time virtualization for scheduling, lead time calculations,
and backoff simulations without relying on wall-clock system time.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import UTC, datetime, timedelta


class Clock(ABC):
    """Abstract UTC Clock interface for operational scheduling and timing."""

    @abstractmethod
    def now(self) -> datetime:
        """Return the current timezone-aware UTC datetime."""
        ...

    @abstractmethod
    def sleep(self, seconds: float) -> None:
        """Sleep or advance time by the specified duration in seconds."""
        ...


class SystemClock(Clock):
    """Production UTC wall clock."""

    def now(self) -> datetime:
        return datetime.now(UTC)

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            time.sleep(seconds)


class FakeClock(Clock):
    """
    Deterministic simulated UTC clock for testing and time-travel scenarios.
    Sleep advances time instantaneously without real-time delay.
    """

    def __init__(self, initial_time: datetime | None = None) -> None:
        if initial_time is not None:
            if initial_time.tzinfo is None:
                self._current_time = initial_time.replace(tzinfo=UTC)
            else:
                self._current_time = initial_time.astimezone(UTC)
        else:
            self._current_time = datetime(2026, 10, 23, 12, 0, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._current_time

    def set_time(self, dt: datetime) -> None:
        if dt.tzinfo is None:
            self._current_time = dt.replace(tzinfo=UTC)
        else:
            self._current_time = dt.astimezone(UTC)

    def advance(self, duration: float | timedelta) -> None:
        if isinstance(duration, (int, float)):
            self._current_time += timedelta(seconds=float(duration))
        elif isinstance(duration, timedelta):
            self._current_time += duration
        else:
            raise TypeError(f"Unsupported duration type: {type(duration)}")

    def sleep(self, seconds: float) -> None:
        if seconds > 0:
            self.advance(seconds)
