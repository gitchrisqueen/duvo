"""Deduplication must be visible to the reporting layer, not just the write layer."""

from __future__ import annotations

import threading
from collections.abc import Callable

import pytest

from duvo_fde.clock import FrozenClock
from duvo_fde.idempotency import IdempotencyStore, OperationOutcome


def _counting_operation(calls: list[str], response_id: str) -> Callable[[], dict[str, str]]:
    """Return an operation that records that it ran."""

    def operation() -> dict[str, str]:
        calls.append(response_id)
        return {"id": response_id}

    return operation


def test_first_call_executes_the_operation(frozen_clock: FrozenClock) -> None:
    store = IdempotencyStore(clock=frozen_clock)
    calls: list[str] = []

    result = store.execute("order-1", _counting_operation(calls, "A"))

    assert calls == ["A"]
    assert result.outcome is OperationOutcome.CREATED
    assert result.response == {"id": "A"}


def test_replay_does_not_execute_the_operation_again(frozen_clock: FrozenClock) -> None:
    store = IdempotencyStore(clock=frozen_clock)
    calls: list[str] = []

    store.execute("order-1", _counting_operation(calls, "A"))
    store.execute("order-1", _counting_operation(calls, "B"))

    assert calls == ["A"]


def test_replay_returns_the_original_response(frozen_clock: FrozenClock) -> None:
    """Callers see a consistent view rather than a second, different result."""
    store = IdempotencyStore(clock=frozen_clock)
    store.execute("order-1", lambda: {"id": "A", "total": 100})

    replay = store.execute("order-1", lambda: {"id": "B", "total": 999})

    assert replay.response == {"id": "A", "total": 100}


def test_replay_is_flagged_so_reporting_can_exclude_it(frozen_clock: FrozenClock) -> None:
    store = IdempotencyStore(clock=frozen_clock)
    first = store.execute("order-1", lambda: {"total": 100})
    replay = store.execute("order-1", lambda: {"total": 100})

    assert first.deduplicated is False
    assert first.counts_towards_totals is True
    assert replay.deduplicated is True
    assert replay.counts_towards_totals is False


def test_reported_totals_are_not_inflated_by_retries(frozen_clock: FrozenClock) -> None:
    """The reporting bug this module exists to prevent.

    Deduplicating the write is not enough. If the replay flag is discarded
    before the reporting layer, a retried order is counted as a second purchase
    and the buyer reads an overstated spend figure.
    """
    store = IdempotencyStore(clock=frozen_clock)
    submissions = ["order-1", "order-1", "order-2", "order-1"]

    results = [store.execute(key, lambda: {"total": 100}) for key in submissions]
    reported_spend = sum(r.response["total"] for r in results if r.counts_towards_totals)
    reported_orders = sum(1 for r in results if r.counts_towards_totals)

    assert reported_orders == 2
    assert reported_spend == 200


def test_concurrent_replays_execute_the_operation_once(frozen_clock: FrozenClock) -> None:
    """Two threads must not both pass the membership check."""
    store = IdempotencyStore(clock=frozen_clock)
    calls: list[int] = []
    lock = threading.Lock()
    barrier = threading.Barrier(8)

    def operation() -> dict[str, int]:
        with lock:
            calls.append(1)
        return {"id": 1}

    def worker() -> None:
        barrier.wait(timeout=5)
        store.execute("order-1", operation)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert calls == [1]


def test_distinct_keys_are_independent(frozen_clock: FrozenClock) -> None:
    store = IdempotencyStore(clock=frozen_clock)

    first = store.execute("order-1", lambda: {"id": "A"})
    second = store.execute("order-2", lambda: {"id": "B"})

    assert first.outcome is OperationOutcome.CREATED
    assert second.outcome is OperationOutcome.CREATED


@pytest.mark.parametrize("key", ["", "   "])
def test_an_empty_idempotency_key_is_rejected(key: str, frozen_clock: FrozenClock) -> None:
    store = IdempotencyStore(clock=frozen_clock)

    with pytest.raises(ValueError, match="idempotency key"):
        store.execute(key, lambda: {})


def test_seen_reports_membership(frozen_clock: FrozenClock) -> None:
    store = IdempotencyStore(clock=frozen_clock)
    store.execute("order-1", lambda: {})

    assert store.seen("order-1") is True
    assert store.seen("order-2") is False
