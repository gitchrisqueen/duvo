"""Korral's business rules.

Every calculation and every threshold in this package is deterministic and runs
on the server. Nothing here is delegated to a model, and no fixed business rule
stated in the brief is exposed as something a caller can change.
"""

from duvo_fde.domain.policy import (
    POS_WINDOW_HOURS,
    REPLENISHMENT_GAP_THRESHOLD_UNITS,
    ReplenishmentDecision,
    StockAssessment,
    StockPosition,
    assess,
    compute_gap_units,
    exceeds_threshold,
    order_quantity_units_for_gap,
    pos_window,
    validate_sku,
    validate_store_id,
)

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
