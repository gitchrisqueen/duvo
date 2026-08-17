"""Injectable clock so that time-dependent logic stays testable and fast.

Tests must never sleep. Anything that needs the current time takes a
:class:`Clock`, and tests pass :class:`FrozenClock` instead of waiting for the
wall clock to move.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

__all__ = ["Clock", "FrozenClock", "SystemClock"]


class Clock(Protocol):
    """Provides the current time in UTC."""

    def now(self) -> datetime:
        """Return the current time.

        Returns:
            A timezone-aware datetime in UTC.
        """
        ...


class SystemClock:
    """Clock backed by the operating system."""

    def now(self) -> datetime:
        """Return the current wall-clock time in UTC.

        Returns:
            A timezone-aware datetime in UTC.
        """
        return datetime.now(UTC)


class FrozenClock:
    """Deterministic clock for tests.

    Example:
        ```python
        clock = FrozenClock(datetime(2026, 1, 1, tzinfo=UTC))
        clock.advance(seconds=30)
        ```
    """

    def __init__(self, start: datetime) -> None:
        """Initialise the clock.

        Args:
            start: The time this clock reports until it is advanced.

        Raises:
            ValueError: If ``start`` is not timezone-aware.
        """
        if start.tzinfo is None:
            msg = "FrozenClock requires a timezone-aware datetime."
            raise ValueError(msg)
        self._now = start

    def now(self) -> datetime:
        """Return the frozen time.

        Returns:
            The current value of the frozen clock.
        """
        return self._now

    def advance(self, *, seconds: float = 0.0, days: int = 0) -> None:
        """Move the clock forward.

        Args:
            seconds: Number of seconds to advance.
            days: Number of days to advance.
        """
        self._now += timedelta(seconds=seconds, days=days)
