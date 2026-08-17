"""Idempotent writes whose replay status survives all the way to reporting.

Preventing the duplicate write is only half the job. The half that is easy to
get wrong is telling the *caller* that a replay happened, and carrying that fact
through to whatever aggregates the results.

Consider a buyer's report of "orders placed today". If a retry is correctly
deduplicated at the write layer but the reporting layer only sees "here is an
order", the retry is counted as a second purchase and the reported spend is
overstated. The underlying data is right; the number the buyer reads is wrong,
which is worse than an obvious failure because nobody notices.

:class:`OperationResult` therefore carries both the outcome and the original
upstream response, and every caller is expected to pass the whole result
onwards rather than unwrapping the payload and discarding the outcome.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from duvo_fde.clock import Clock, SystemClock

__all__ = ["IdempotencyStore", "OperationOutcome", "OperationResult"]


class OperationOutcome(StrEnum):
    """Whether a write was performed or recognised as a replay."""

    CREATED = "created"
    DUPLICATE = "duplicate"


@dataclass(frozen=True)
class OperationResult:
    """The full outcome of an idempotent write.

    Attributes:
        outcome: Whether the write happened or was recognised as a replay.
        request_key: The idempotency key the caller supplied.
        response: The upstream response from the original write. Replays return
            the original response so callers see a consistent view.
        recorded_at_iso: When the original write was recorded.
    """

    outcome: OperationOutcome
    request_key: str
    response: dict[str, Any] = field(default_factory=dict)
    recorded_at_iso: str = ""

    @property
    def deduplicated(self) -> bool:
        """Whether this result represents a replay rather than a new write.

        Reporting code must consult this before counting the result towards any
        total. This is the flag whose loss overstates spend.

        Returns:
            ``True`` if the write was a replay.
        """
        return self.outcome is OperationOutcome.DUPLICATE

    @property
    def counts_towards_totals(self) -> bool:
        """Whether this result should be counted in buyer-facing aggregates.

        Returns:
            ``True`` only for writes that actually happened.
        """
        return not self.deduplicated


class IdempotencyStore:
    """In-memory store mapping idempotency keys to their original results.

    The store is process-local and deliberately simple. A deployment that runs
    more than one replica needs shared state here; that trade-off is recorded in
    ``docs/06-assumptions-and-risks.md`` rather than hidden.

    Example:
        ```python
        store = IdempotencyStore()
        result = store.execute("order-123", lambda: upstream.place_order(...))
        if result.counts_towards_totals:
            report.add(result.response)
        ```
    """

    def __init__(self, *, clock: Clock | None = None) -> None:
        """Initialise an empty store.

        Args:
            clock: Clock used for record timestamps. Defaults to the system clock.
        """
        self._clock = clock or SystemClock()
        self._results: dict[str, OperationResult] = {}
        self._lock = threading.Lock()

    def execute(
        self,
        request_key: str,
        operation: Callable[[], dict[str, Any]],
    ) -> OperationResult:
        """Run ``operation`` unless ``request_key`` has already been used.

        The lock is held for the duration of the operation so that two
        concurrent replays cannot both pass the membership check and issue two
        upstream writes.

        Args:
            request_key: Caller-supplied idempotency key.
            operation: Callable performing the write and returning the upstream
                response. Invoked at most once per key.

        Returns:
            The result of the original write, with the outcome describing
            whether this call performed it or replayed it.

        Raises:
            ValueError: If ``request_key`` is empty.
        """
        if not request_key or not request_key.strip():
            msg = "An idempotency key is required."
            raise ValueError(msg)

        with self._lock:
            existing = self._results.get(request_key)
            if existing is not None:
                return OperationResult(
                    outcome=OperationOutcome.DUPLICATE,
                    request_key=request_key,
                    response=existing.response,
                    recorded_at_iso=existing.recorded_at_iso,
                )

            response = operation()
            result = OperationResult(
                outcome=OperationOutcome.CREATED,
                request_key=request_key,
                response=response,
                recorded_at_iso=self._clock.now().isoformat(),
            )
            self._results[request_key] = result
            return result

    def seen(self, request_key: str) -> bool:
        """Report whether a key has already been used.

        Args:
            request_key: The key to check.

        Returns:
            ``True`` if a write has been recorded under this key.
        """
        with self._lock:
            return request_key in self._results
