"""Korral's replenishment rule, expressed once, in one place.

Nothing in this module performs input or output. It does not reach the network,
the clock, the filesystem, the secrets provider, the audit log or the logger, so
every rule here is testable by calling a function.

Two rules from the repository's working instructions are load bearing here. The
calculation is deterministic and lives on the server, never delegated to a
model. The threshold is a fixed business rule stated in the brief, so it is a
constant in this module and never a parameter a caller can supply.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final

from duvo_fde.errors import InvalidRequestError, UpstreamError

__all__ = [
    "POS_WINDOW_HOURS",
    "REPLENISHMENT_GAP_THRESHOLD_UNITS",
    "ReplenishmentDecision",
    "StockAssessment",
    "StockPosition",
    "assess",
    "compute_gap_units",
    "exceeds_threshold",
    "order_quantity_units_for_gap",
    "pos_window",
    "validate_sku",
    "validate_store_id",
]

REPLENISHMENT_GAP_THRESHOLD_UNITS: Final[int] = 6
"""Korral's replenishment threshold, in units.

Stated in the brief as a rule, not as a default, so it is a constant here. It is
deliberately not a setting in ``config.py``: an environment variable is an
override path, and a caller who can change a stated business rule has changed
Korral's policy rather than this server's configuration.
"""

POS_WINDOW_HOURS: Final[int] = 24
"""The trailing window over which till sales are counted, in hours."""

_STORE_ID_PATTERN: Final = re.compile(r"^[0-9]{1,10}$")
_SKU_PATTERN: Final = re.compile(r"^[0-9]{1,20}$")


class StockAssessment(StrEnum):
    """What this server concluded about one position."""

    ORDER_REQUIRED = "order_required"
    NO_ORDER_REQUIRED = "no_order_required"
    NOT_STOCKED = "not_stocked"


@dataclass(frozen=True)
class StockPosition:
    """One measured position, as fetched from StoreLink.

    Attributes:
        store_id: The store the figures were read from.
        sku: The stock keeping unit the figures describe.
        sku_name: The display name, so a buyer reads a product rather than a
            number.
        on_hand_units: Units currently on hand, or ``None`` when the stock
            keeping unit is not ranged at this store. ``None`` is never
            conflated with zero.
        pos_units_sold_24h: Units sold through the till in the trailing window.
        pos_transaction_count: How many till transactions were aggregated. This
            is the only field that separates "nothing sold" from "nothing came
            back", which is a failure mode worth being able to see.
    """

    store_id: str
    sku: str
    sku_name: str
    on_hand_units: int | None
    pos_units_sold_24h: int
    pos_transaction_count: int


@dataclass(frozen=True)
class ReplenishmentDecision:
    """This server's decision about one position.

    Attributes:
        assessment: What was concluded.
        gap_units: The measured gap, or ``None`` when nothing is ranged.
        order_quantity_units: What would be ordered, or ``None``.
        threshold_units: The threshold that was applied, returned so a buyer can
            check the rule without reading source.
        explanation: One plain English sentence containing the arithmetic. The
            same sentence goes to the agent and into the audit trail, so a
            discrepancy between what the buyer reads and what the agent said is
            a bug anyone can see.
    """

    assessment: StockAssessment
    gap_units: int | None
    order_quantity_units: int | None
    threshold_units: int
    explanation: str


def validate_store_id(raw: str) -> str:
    """Check a store identifier arriving from a caller.

    Args:
        raw: The value supplied by the caller.

    Returns:
        The validated identifier.

    Raises:
        InvalidRequestError: The value is empty, malformed, or not a store
            identifier at all.
    """
    candidate = str(raw).strip()
    if not _STORE_ID_PATTERN.match(candidate):
        raise InvalidRequestError(
            "A Korral store identifier is one to ten digits, for example 47. "
            f"The value supplied was not accepted: {candidate!r}.",
            details={"store_id": candidate},
        )
    return candidate


def validate_sku(raw: str) -> str:
    """Check a stock keeping unit identifier arriving from a caller.

    Args:
        raw: The value supplied by the caller.

    Returns:
        The validated identifier.

    Raises:
        InvalidRequestError: The value is empty or malformed.
    """
    candidate = str(raw).strip()
    if not _SKU_PATTERN.match(candidate):
        raise InvalidRequestError(
            "A Korral stock keeping unit identifier is one to twenty digits, for example "
            f"8847291. The value supplied was not accepted: {candidate!r}.",
            details={"sku": candidate},
        )
    return candidate


def compute_gap_units(*, on_hand_units: int, pos_units_sold_24h: int) -> int:
    """Compute the shortfall between recent demand and current stock.

    The direction matters more than anything else in this module. A positive gap
    means the last twenty four hours of demand would exhaust what is on the
    shelf, which is exactly the question the buyer is asking. The arguments are
    keyword only so that a call site cannot silently compute the inverse.

    Args:
        on_hand_units: Units currently on hand.
        pos_units_sold_24h: Units sold through the till in the trailing window.

    Returns:
        Units sold in the window minus units on hand.
    """
    return pos_units_sold_24h - on_hand_units


def exceeds_threshold(gap_units: int) -> bool:
    """Apply Korral's threshold to a measured gap.

    The brief says the gap must exceed six units. "Exceeds" is strictly greater
    than, so a gap of exactly six does not raise an order.

    Args:
        gap_units: The measured gap.

    Returns:
        Whether the gap crosses the threshold.
    """
    return gap_units > REPLENISHMENT_GAP_THRESHOLD_UNITS


def order_quantity_units_for_gap(gap_units: int) -> int:
    """Choose how much to order for a gap that crossed the threshold.

    The brief specifies when to order and is silent on how much, so this rule is
    ours and is recorded as an assumption. Ordering the gap restores roughly one
    day of observed demand. It stays a named function so that Korral can replace
    the quantity rule without touching the trigger.

    Args:
        gap_units: The measured gap, which has already crossed the threshold.

    Returns:
        The quantity to order, in units.
    """
    return gap_units


def pos_window(now: datetime) -> tuple[datetime, datetime]:
    """Compute the trailing window over which till sales are counted.

    Args:
        now: The current instant, supplied by the injectable clock so that tests
            never depend on the wall clock.

    Returns:
        The start and end of the window.
    """
    return now - timedelta(hours=POS_WINDOW_HOURS), now


def assess(position: StockPosition) -> ReplenishmentDecision:
    """Apply Korral's replenishment rule to one measured position.

    Args:
        position: The figures read from StoreLink.

    Returns:
        The decision, the arithmetic, and a sentence explaining both.

    Raises:
        UpstreamError: StoreLink reported a negative quantity on hand. That is a
            stock record error rather than a shortage, and this server will not
            compute a real order from it.
    """
    if position.on_hand_units is None:
        return ReplenishmentDecision(
            assessment=StockAssessment.NOT_STOCKED,
            gap_units=None,
            order_quantity_units=None,
            threshold_units=REPLENISHMENT_GAP_THRESHOLD_UNITS,
            explanation=(
                f"{position.sku_name} is not ranged at store {position.store_id}. This is "
                "not the same as zero on hand: there is no shelf presence to replenish. "
                "Adding this product to the store's range is a buyer's decision rather "
                "than a replenishment decision, so no order was raised."
            ),
        )

    if position.on_hand_units < 0:
        raise UpstreamError(
            f"StoreLink reported units on hand for store {position.store_id}, stock keeping "
            f"unit {position.sku} as {position.on_hand_units}. A negative quantity on hand "
            "is a stock record error rather than a shortage, and this server will not "
            "compute a replenishment order from it.",
            details={"store_id": position.store_id, "on_hand_units": position.on_hand_units},
        )

    gap_units = compute_gap_units(
        on_hand_units=position.on_hand_units,
        pos_units_sold_24h=position.pos_units_sold_24h,
    )
    sold = (
        f"Store {position.store_id} sold {position.pos_units_sold_24h} units of "
        f"{position.sku_name} through the till in the last {POS_WINDOW_HOURS} hours and has "
        f"{position.on_hand_units} on hand, a gap of {gap_units} units."
    )

    if exceeds_threshold(gap_units):
        quantity = order_quantity_units_for_gap(gap_units)
        return ReplenishmentDecision(
            assessment=StockAssessment.ORDER_REQUIRED,
            gap_units=gap_units,
            order_quantity_units=quantity,
            threshold_units=REPLENISHMENT_GAP_THRESHOLD_UNITS,
            explanation=(
                f"{sold} That exceeds Korral's {REPLENISHMENT_GAP_THRESHOLD_UNITS} unit "
                f"replenishment threshold, so an order for {quantity} units is required."
            ),
        )

    return ReplenishmentDecision(
        assessment=StockAssessment.NO_ORDER_REQUIRED,
        gap_units=gap_units,
        order_quantity_units=None,
        threshold_units=REPLENISHMENT_GAP_THRESHOLD_UNITS,
        explanation=(
            f"{sold} Korral's threshold is {REPLENISHMENT_GAP_THRESHOLD_UNITS} units and the "
            f"rule is that the gap must exceed it, so {gap_units} does not qualify. No order "
            "was raised."
        ),
    )
