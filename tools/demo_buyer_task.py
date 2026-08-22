"""Drive the buyer's instruction through the real tools and assert the outcome.

This exists so that the demonstration proves something rather than merely
printing something. Every figure below is fetched from the running mock over
HTTP, and every expectation is asserted: if the arithmetic, the threshold, the
deduplication or the fail-closed path regressed, this exits non-zero and says
which one.

It lives in ``tools`` rather than in the shipped package because it is a check,
not a feature, and the runtime image excludes this directory.
"""

from __future__ import annotations

from duvo_fde.errors import DuvoError
from duvo_fde.runtime import build_runtime
from duvo_fde.service import BuyerService, OutOfPolicyOrderError
from duvo_fde.storelink import StoreLinkClient

SKU = "8847291"
ORDERING_STORE = "47"
REFUSED_STORE = "102"
UNCONFIGURED_STORE = "999"


def main() -> int:
    """Run the buyer task and assert every outcome the brief describes.

    Returns:
        Process exit code. Zero when every expectation held.
    """
    runtime = build_runtime(configure_logs=False)
    service = BuyerService(runtime, StoreLinkClient(runtime))
    failures: list[str] = []

    def expect(condition: bool, message: str) -> None:
        """Record a failed expectation without stopping the run.

        Args:
            condition: What had to be true.
            message: What to report when it was not.
        """
        if condition:
            print(f"  ok    {message}")
        else:
            print(f"  FAIL  {message}")
            failures.append(message)

    print("\nStep one: check on-hand against the last 24 hours of till sales, for both stores.")
    positions = {}
    for store in (ORDERING_STORE, REFUSED_STORE):
        result = service.check_stock_position(
            store_id=store, sku=SKU, correlation_id=f"demo-check-{store}"
        )
        positions[store] = result
        print(
            f"\n  store {store}: on hand {result['on_hand_units']}, "
            f"sold {result['pos_units_sold_24h']} across "
            f"{result['pos_transaction_count']} till transactions, "
            f"gap {result['gap_units']} -> {result['assessment']}"
        )
        print(f"    {result['explanation']}")
        expect(
            result["replenishment_threshold_units"] == 6,
            f"store {store} reports the threshold Korral stated",
        )
        expect(
            "basket_id" not in result and "loyalty_id" not in result,
            f"store {store} returned no basket or loyalty detail to the caller",
        )

    expect(positions[ORDERING_STORE]["gap_units"] == 19, "store 47's gap is 19 units")
    expect(
        positions[REFUSED_STORE]["gap_units"] == 6,
        "store 102's gap is exactly 6 units, which is the boundary case",
    )

    print("\nStep two: raise an order wherever the gap exceeds six units.")
    order = service.raise_replenishment_order(
        store_id=ORDERING_STORE, sku=SKU, correlation_id="demo-order-47"
    )
    print(
        f"\n  store {ORDERING_STORE}: ordered {order['order_quantity_units']} units, "
        f"order {order['order_id']}, outcome {order['order_outcome']}"
    )
    expect(order["order_quantity_units"] == 19, "store 47 ordered 19 units, the measured gap")
    expect(order["order_outcome"] == "created", "store 47's order was newly created")

    try:
        service.raise_replenishment_order(
            store_id=REFUSED_STORE, sku=SKU, correlation_id="demo-order-102"
        )
        expect(False, "store 102 was refused")
    except OutOfPolicyOrderError as exc:
        print(f"\n  store {REFUSED_STORE}: refused [{exc.code}]")
        print(f"    {exc.safe_message}")
        expect(True, "store 102 was refused, because six does not exceed six")

    print("\nStep three: the agent retries. The order must not be placed twice.")
    replay = service.raise_replenishment_order(
        store_id=ORDERING_STORE, sku=SKU, correlation_id="demo-retry-47"
    )
    print(
        f"\n  store {ORDERING_STORE} again: order {replay['order_id']}, "
        f"outcome {replay['order_outcome']}, counts towards the daily total "
        f"{replay['counts_towards_daily_order_total']}"
    )
    expect(replay["order_id"] == order["order_id"], "the retry returned the original order")
    expect(replay["order_outcome"] == "duplicate", "the retry is reported as a replay")
    expect(
        replay["counts_towards_daily_order_total"] is False,
        "the replay does not inflate the buyer's reported spend",
    )

    print("\nStep four: a store this server holds no credential for.")
    try:
        service.check_stock_position(
            store_id=UNCONFIGURED_STORE, sku=SKU, correlation_id="demo-999"
        )
        expect(False, "store 999 failed closed")
    except DuvoError as exc:
        print(f"\n  [{exc.code}] {exc.safe_message}")
        expect(exc.code == "store_credential_missing", "store 999 failed with its own error code")
        expect(
            ORDERING_STORE not in exc.safe_message and REFUSED_STORE not in exc.safe_message,
            "the error named no store other than the one asked for",
        )

    print("\nStep five: a malformed identifier from a model.")
    try:
        service.check_stock_position(store_id="../etc", sku=SKU, correlation_id="demo-bad")
        expect(False, "a malformed store identifier was rejected")
    except DuvoError as exc:
        print(f"\n  [{exc.code}] {exc.safe_message}")
        expect(exc.code == "invalid_request", "a malformed identifier is rejected at the boundary")

    if failures:
        print(f"\n{len(failures)} expectation(s) failed.")
        return 1
    print("\nEvery expectation held.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
