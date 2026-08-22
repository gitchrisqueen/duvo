"""Orchestration: read the position, apply the rule, place the order, record it.

Two audiences read what happens here, and they need different things. An
engineer debugging late at night needs correlated, structured detail about every
upstream call. A Korral category buyer reading the audit trail the next morning
needs plain English about what was done on their behalf and why. Both streams
are written here, and both carry the same correlation identifier, so the buyer
can hand an engineer one string and the engineer can find everything.
"""

from __future__ import annotations

import logging
from typing import Any

from duvo_fde.credentials import resolve_store_key
from duvo_fde.domain import policy
from duvo_fde.errors import InvalidRequestError, UnknownEntityError
from duvo_fde.runtime import Runtime
from duvo_fde.storelink import StoreLinkClient

__all__ = ["BuyerService", "OutOfPolicyOrderError"]

_LOGGER = logging.getLogger(__name__)

_ACTOR = "duvo-agent"


class OutOfPolicyOrderError(InvalidRequestError):
    """An order was requested that Korral's replenishment policy does not permit.

    This has its own code rather than reusing the generic validation code,
    because how often a caller tries to place an order the policy refuses is the
    single most useful safety measurement this server produces. It should sit
    near zero, and a rise means either the tool descriptions or the model's
    behaviour has drifted.
    """

    code = "out_of_policy"


class BuyerService:
    """The buyer's job, performed deterministically on the server."""

    def __init__(self, runtime: Runtime, client: StoreLinkClient) -> None:
        """Build the service.

        Args:
            runtime: The assembled runtime.
            client: The StoreLink client.
        """
        self._runtime = runtime
        self._client = client

    def check_stock_position(
        self, *, store_id: str, sku: str, correlation_id: str
    ) -> dict[str, Any]:
        """Report one position and this server's decision about it.

        Args:
            store_id: The store to examine.
            sku: The stock keeping unit to examine.
            correlation_id: The identifier joining logs to the audit trail.

        Returns:
            The measured figures, the gap, and the decision.
        """
        position, decision, _ = self._measure(
            store_id=store_id, sku=sku, correlation_id=correlation_id
        )
        result: dict[str, Any] = {
            "correlation_id": correlation_id,
            "store_id": position.store_id,
            "sku": position.sku,
            "sku_name": position.sku_name,
            "on_hand_units": position.on_hand_units,
            "pos_units_sold_24h": position.pos_units_sold_24h,
            "pos_transaction_count": position.pos_transaction_count,
            "gap_units": decision.gap_units,
            "replenishment_threshold_units": decision.threshold_units,
            "replenishment_required": decision.assessment is policy.StockAssessment.ORDER_REQUIRED,
            "assessment": str(decision.assessment),
            "explanation": decision.explanation,
            "assessed_at_utc": self._runtime.clock.now().isoformat(),
        }
        self._audit(
            action="stock_position_checked",
            target=f"store={position.store_id};sku={position.sku}",
            outcome=str(decision.assessment),
            context={**result},
        )
        return result

    def raise_replenishment_order(
        self, *, store_id: str, sku: str, correlation_id: str
    ) -> dict[str, Any]:
        """Raise an order when, and only when, Korral's policy requires one.

        The position is measured again here rather than taken from the caller.
        Stock moves between a check and an order, so deciding on the older
        reading would be the bug, and re-reading means no number a model
        produced can reach the comparison.

        Args:
            store_id: The store to order for.
            sku: The stock keeping unit to order.
            correlation_id: The identifier joining logs to the audit trail.

        Returns:
            The order, the arithmetic that justified it, and whether this call
            created it or replayed an earlier one.

        Raises:
            OutOfPolicyOrderError: The recomputed gap does not cross Korral's
                threshold, so no order is permitted.
            UnknownEntityError: The stock keeping unit is not ranged at the
                store, so there is nothing to replenish.
        """
        position, decision, store = self._measure(
            store_id=store_id, sku=sku, correlation_id=correlation_id
        )

        if decision.assessment is policy.StockAssessment.NOT_STOCKED:
            self._audit(
                action="replenishment_order_refused",
                target=f"store={position.store_id};sku={position.sku}",
                outcome="not_stocked",
                context={"correlation_id": correlation_id, "explanation": decision.explanation},
            )
            raise UnknownEntityError(
                decision.explanation,
                details={"store_id": position.store_id, "sku": position.sku},
            )

        if decision.assessment is not policy.StockAssessment.ORDER_REQUIRED:
            self._audit(
                action="replenishment_order_refused",
                target=f"store={position.store_id};sku={position.sku}",
                outcome="below_threshold",
                context={
                    "correlation_id": correlation_id,
                    "store_id": position.store_id,
                    "sku": position.sku,
                    "sku_name": position.sku_name,
                    "on_hand_units": position.on_hand_units,
                    "pos_units_sold_24h": position.pos_units_sold_24h,
                    "gap_units": decision.gap_units,
                    "threshold_units": decision.threshold_units,
                    "explanation": decision.explanation,
                },
            )
            raise OutOfPolicyOrderError(
                f"Order refused for store {position.store_id}, stock keeping unit "
                f"{position.sku}. This server re-checked the position itself. "
                f"{decision.explanation} That threshold is Korral policy and cannot be "
                "overridden by a caller, so calling this tool again with different "
                "arguments will not change the outcome.",
                details={"store_id": position.store_id, "gap_units": decision.gap_units},
            )

        quantity = decision.order_quantity_units
        assert quantity is not None
        ordering_date = self._ordering_date(store)
        request_key = replenishment_idempotency_key(
            store_id=position.store_id,
            sku=position.sku,
            order_quantity_units=quantity,
            ordering_date=ordering_date,
        )

        def place() -> dict[str, Any]:
            return self._client.create_replenishment_order(
                position.store_id,
                sku=position.sku,
                quantity_units=quantity,
                correlation_id=correlation_id,
            )

        operation = self._runtime.idempotency.execute(request_key, place)
        order = operation.response

        result: dict[str, Any] = {
            "correlation_id": correlation_id,
            "store_id": position.store_id,
            "sku": position.sku,
            "sku_name": position.sku_name,
            "on_hand_units": position.on_hand_units,
            "pos_units_sold_24h": position.pos_units_sold_24h,
            "pos_transaction_count": position.pos_transaction_count,
            "gap_units": decision.gap_units,
            "replenishment_threshold_units": decision.threshold_units,
            "order_quantity_units": quantity,
            "order_id": order.get("order_id"),
            "order_status": order.get("status"),
            "order_outcome": str(operation.outcome),
            "counts_towards_daily_order_total": operation.counts_towards_totals,
            "idempotency_key": request_key,
            "ordering_date": ordering_date,
            "ordered_at_utc": self._runtime.clock.now().isoformat(),
            "explanation": decision.explanation,
        }
        self._audit(
            action="replenishment_order_raised",
            target=f"store={position.store_id};sku={position.sku}",
            outcome=str(operation.outcome),
            context={**result},
        )
        return result

    def get_replenishment_order_status(
        self, *, store_id: str, order_id: str, correlation_id: str
    ) -> dict[str, Any]:
        """Report StoreLink's current status for one order.

        StoreLink is the system of record here. This deliberately does not
        report whether this server holds a record of the order: in the situation
        this tool exists for, our record is the thing that is missing.

        Args:
            store_id: The store the order was raised at.
            order_id: The order identifier.
            correlation_id: The identifier joining logs to the audit trail.

        Returns:
            The order's status as StoreLink reports it.
        """
        checked = policy.validate_store_id(store_id)
        resolve_store_key(self._runtime.secrets, checked)
        order = self._client.get_replenishment_order(
            checked, str(order_id).strip(), correlation_id=correlation_id
        )
        result: dict[str, Any] = {
            "correlation_id": correlation_id,
            "store_id": checked,
            "order_id": order.get("order_id"),
            "sku": order.get("sku"),
            "order_quantity_units": order.get("quantity_units"),
            "order_status": order.get("status"),
            "raised_at_utc": order.get("raised_at"),
        }
        self._audit(
            action="replenishment_order_status_checked",
            target=f"store={checked};order={order_id}",
            outcome="found",
            context={**result},
        )
        return result

    def _measure(
        self, *, store_id: str, sku: str, correlation_id: str
    ) -> tuple[policy.StockPosition, policy.ReplenishmentDecision, dict[str, Any]]:
        """Read one position from StoreLink and apply the rule to it.

        The order of these steps is deliberate: the cheapest rejection runs
        first, and the credential is resolved before any network call, so a
        store this server has no key for is never queried.

        Args:
            store_id: The store to examine.
            sku: The stock keeping unit to examine.
            correlation_id: The identifier joining logs to the audit trail.

        Returns:
            The measured position, the decision, and the store record.
        """
        checked_store = policy.validate_store_id(store_id)
        checked_sku = policy.validate_sku(sku)
        resolve_store_key(self._runtime.secrets, checked_store)

        store = self._client.get_store(checked_store, correlation_id=correlation_id)
        sku_record = self._client.get_sku(checked_store, checked_sku, correlation_id=correlation_id)
        inventory = self._client.get_inventory(
            checked_store, checked_sku, correlation_id=correlation_id
        )
        start, _end = policy.pos_window(self._runtime.clock.now())
        rows = self._client.get_pos(
            checked_store, checked_sku, since=start.isoformat(), correlation_id=correlation_id
        )

        position = policy.StockPosition(
            store_id=checked_store,
            sku=checked_sku,
            sku_name=str(sku_record.get("name", checked_sku)),
            on_hand_units=None if inventory is None else int(inventory["on_hand_units"]),
            pos_units_sold_24h=sum(int(row.get("units", 0)) for row in rows),
            pos_transaction_count=len(rows),
        )
        return position, policy.assess(position), store

    def _ordering_date(self, store: dict[str, Any]) -> str:
        """Return the trading date the order belongs to.

        Replenishment is a daily cycle, so an identical order tomorrow is a
        different order and must not be treated as a replay of today's.

        Args:
            store: The store record, which may carry a timezone.

        Returns:
            The ordering date, as a plain calendar date.
        """
        now = self._runtime.clock.now()
        timezone_name = store.get("timezone")
        if timezone_name:
            try:
                from zoneinfo import ZoneInfo

                now = now.astimezone(ZoneInfo(str(timezone_name)))
            except Exception:  # noqa: BLE001 - an unknown timezone falls back to UTC
                _LOGGER.warning(
                    "Unknown store timezone; falling back to coordinated universal time.",
                    extra={"fields": {"timezone": str(timezone_name)}},
                )
        return now.date().isoformat()

    def _audit(self, *, action: str, target: str, outcome: str, context: dict[str, Any]) -> None:
        """Append one record to the buyer's trail.

        Args:
            action: What was done.
            target: What it was done to.
            outcome: How it turned out.
            context: The arithmetic and the plain English explanation.
        """
        self._runtime.audit.record(
            actor=_ACTOR, action=action, target=target, outcome=outcome, context=context
        )


def replenishment_idempotency_key(
    *, store_id: str, sku: str, order_quantity_units: int, ordering_date: str
) -> str:
    """Derive the key that makes a repeated order a replay rather than a purchase.

    The key is readable rather than hashed, deliberately. An opaque digest would
    force an engineer to run this code to work out why a write was deduplicated,
    whereas a readable key explains itself in a log line. It carries no secret
    and no customer data.

    Quantity is part of the key on purpose. A second call whose recomputed gap
    has grown is a genuinely different order, and a buyer whose shelf emptied
    further wants that order rather than a silent replay of the old one. A
    caller that simply repeats itself sees the same figures, the same quantity,
    the same key, and therefore a replay.

    Args:
        store_id: The store being ordered for.
        sku: The stock keeping unit being ordered.
        order_quantity_units: The quantity this server computed.
        ordering_date: The store's trading date.

    Returns:
        The deduplication key.
    """
    return (
        f"replenishment:v1:store={store_id}:sku={sku}"
        f":qty={order_quantity_units}:date={ordering_date}"
    )
