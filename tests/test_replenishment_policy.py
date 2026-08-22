"""Korral's replenishment rule.

These tests pin the two decisions in the brief that are most easily got wrong:
the direction of the gap, and whether a gap of exactly six raises an order.
Everything here is a plain function call with no input or output of any kind.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from duvo_fde.domain import policy
from duvo_fde.errors import InvalidRequestError, UpstreamError


def _position(on_hand: int | None, sold: int, *, store: str = "47") -> policy.StockPosition:
    """Build a position for a test.

    Args:
        on_hand: Units on hand, or ``None`` when not ranged.
        sold: Units sold in the window.
        store: The store identifier.

    Returns:
        The position.
    """
    return policy.StockPosition(
        store_id=store,
        sku="8847291",
        sku_name="Madeta butter 250g",
        on_hand_units=on_hand,
        pos_units_sold_24h=sold,
        pos_transaction_count=1,
    )


def test_the_threshold_is_six_units() -> None:
    """The brief states six, so the constant is six."""
    assert policy.REPLENISHMENT_GAP_THRESHOLD_UNITS == 6


def test_the_gap_is_units_sold_minus_units_on_hand() -> None:
    """A positive gap means recent demand would exhaust the shelf."""
    assert policy.compute_gap_units(on_hand_units=12, pos_units_sold_24h=31) == 19


def test_a_well_stocked_store_has_a_negative_gap() -> None:
    """The direction holds in both directions, which is the point of the test."""
    assert policy.compute_gap_units(on_hand_units=40, pos_units_sold_24h=5) == -35


@pytest.mark.parametrize(
    ("gap", "expected"),
    [(-3, False), (0, False), (5, False), (6, False), (7, True), (19, True)],
)
def test_exceeds_is_strictly_greater_than(gap: int, expected: bool) -> None:
    """A gap of exactly six does not order. Seven does."""
    assert policy.exceeds_threshold(gap) is expected


def test_the_store_at_exactly_the_threshold_is_refused() -> None:
    """This is the demonstration's second store, and the whole point of it."""
    decision = policy.assess(_position(26, 32, store="102"))
    assert decision.assessment is policy.StockAssessment.NO_ORDER_REQUIRED
    assert decision.gap_units == 6
    assert decision.order_quantity_units is None
    assert "does not qualify" in decision.explanation


def test_the_store_above_the_threshold_orders_the_gap() -> None:
    """The quantity is the gap, computed on the server."""
    decision = policy.assess(_position(12, 31))
    assert decision.assessment is policy.StockAssessment.ORDER_REQUIRED
    assert decision.gap_units == 19
    assert decision.order_quantity_units == 19


def test_an_ordered_quantity_is_always_positive() -> None:
    """The quantity rule only ever runs above the threshold, so it cannot be zero."""
    for sold in range(7, 40):
        decision = policy.assess(_position(0, sold))
        assert decision.order_quantity_units is not None
        assert decision.order_quantity_units >= 7


def test_not_stocked_is_not_the_same_as_zero_on_hand() -> None:
    """Nothing ranged is a different outcome from an empty shelf, and never orders."""
    absent = policy.assess(_position(None, 30))
    assert absent.assessment is policy.StockAssessment.NOT_STOCKED
    assert absent.gap_units is None
    assert absent.order_quantity_units is None

    empty = policy.assess(_position(0, 30))
    assert empty.assessment is policy.StockAssessment.ORDER_REQUIRED
    assert empty.gap_units == 30


def test_a_negative_quantity_on_hand_is_refused_rather_than_ordered_from() -> None:
    """A negative count is a stock record error, not a shortage."""
    with pytest.raises(UpstreamError):
        policy.assess(_position(-4, 10))


@pytest.mark.parametrize("bad", ["", "  ", "abc", "47a", "../47", "-1", "9" * 11])
def test_malformed_store_identifiers_are_rejected(bad: str) -> None:
    """Identifiers arrive from a model, so they are checked at the boundary."""
    with pytest.raises(InvalidRequestError):
        policy.validate_store_id(bad)


@pytest.mark.parametrize("bad", ["", "butter", "884-7291", "../x"])
def test_malformed_stock_keeping_units_are_rejected(bad: str) -> None:
    """The same boundary applies to the product identifier."""
    with pytest.raises(InvalidRequestError):
        policy.validate_sku(bad)


def test_valid_identifiers_survive_validation() -> None:
    """Surrounding whitespace is tolerated; the value is not otherwise altered."""
    assert policy.validate_store_id(" 47 ") == "47"
    assert policy.validate_sku("8847291") == "8847291"


def test_the_window_is_the_trailing_twenty_four_hours() -> None:
    """The window ends now and starts a day earlier, from the injectable clock."""
    now = datetime(2026, 8, 22, 9, 14, tzinfo=UTC)
    start, end = policy.pos_window(now)
    assert end == now
    assert (end - start).total_seconds() == 24 * 3600
