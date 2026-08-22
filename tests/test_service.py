"""Orchestration: read the position, apply the rule, place the order, record it.

The StoreLink client is replaced with a scripted stand-in here, so what these
tests pin is the decision-making rather than the transport. The cases that
matter most are the ones a reviewer will reach for: a gap of exactly the
threshold, a replay that must not inflate reported spend, and a store this
server holds no credential for.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

import pytest

from duvo_fde.credentials import StoreCredentialMissingError
from duvo_fde.errors import InvalidRequestError, UnknownEntityError
from duvo_fde.runtime import Runtime
from duvo_fde.service import BuyerService, OutOfPolicyOrderError, replenishment_idempotency_key
from duvo_fde.storelink import StoreLinkClient

from .conftest import write_secret

CORRELATION = "test-correlation"
SKU = "8847291"


class StubStoreLink:
    """A scripted stand-in for Korral's StoreLink system."""

    def __init__(
        self,
        *,
        on_hand: int | None = 12,
        sold: list[int] | None = None,
        timezone: str | None = None,
    ) -> None:
        """Script one store's figures."""
        self.on_hand = on_hand
        self.sold = [31] if sold is None else sold
        self.timezone = timezone
        self.orders_placed: list[dict[str, Any]] = []
        self.calls: list[str] = []
        self._next_order = 1001

    def get_store(self, store_id: str, *, correlation_id: str) -> dict[str, Any]:
        self.calls.append("get_store")
        record: dict[str, Any] = {"store_id": store_id}
        if self.timezone:
            record["timezone"] = self.timezone
        return record

    def get_sku(self, store_id: str, sku: str, *, correlation_id: str) -> dict[str, Any]:
        self.calls.append("get_sku")
        return {"sku": sku, "name": "Madeta butter 250g"}

    def get_inventory(
        self, store_id: str, sku: str, *, correlation_id: str
    ) -> dict[str, Any] | None:
        self.calls.append("get_inventory")
        if self.on_hand is None:
            return None
        return {"on_hand_units": self.on_hand}

    def get_pos(
        self, store_id: str, sku: str, *, since: str, correlation_id: str
    ) -> list[dict[str, Any]]:
        self.calls.append("get_pos")
        # Real till rows carry basket, loyalty, payment and staff detail. They
        # are returned here precisely so that the test can prove none of it
        # reaches the caller's result.
        return [
            {
                "units": units,
                "basket_id": f"BSK-{index}",
                "loyalty_id": "LOY-90210",
                "payment_pan": "4111111111111111",
                "staff_id": "STAFF-7",
            }
            for index, units in enumerate(self.sold)
        ]

    def create_replenishment_order(
        self, store_id: str, *, sku: str, quantity_units: int, correlation_id: str
    ) -> dict[str, Any]:
        self.calls.append("create_replenishment_order")
        order_id = f"REP-{self._next_order}"
        self._next_order += 1
        self.orders_placed.append({"store_id": store_id, "quantity_units": quantity_units})
        return {"order_id": order_id, "status": "accepted"}

    def get_replenishment_order(
        self, store_id: str, order_id: str, *, correlation_id: str
    ) -> dict[str, Any]:
        self.calls.append("get_replenishment_order")
        return {
            "order_id": order_id,
            "sku": SKU,
            "quantity_units": 19,
            "status": "accepted",
            "raised_at": "2026-01-01T09:00:00+00:00",
        }


@pytest.fixture
def store_keys(secrets_dir: Path) -> None:
    """Configure credentials for the stores these tests act on."""
    write_secret(secrets_dir, "korral_store_key_47", "key-47")
    write_secret(secrets_dir, "korral_store_key_102", "key-102")


def _service(runtime: Runtime, client: StubStoreLink) -> BuyerService:
    """Build the service against the scripted stand-in."""
    return BuyerService(runtime, cast(StoreLinkClient, client))


def _audit_records(runtime: Runtime) -> list[dict[str, Any]]:
    """Read back everything written to the audit trail."""
    path = runtime.settings.audit_log_path
    if path is None or not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_a_gap_above_the_threshold_requires_an_order(runtime: Runtime, store_keys: None) -> None:
    client = StubStoreLink(on_hand=12, sold=[31])
    service = _service(runtime, client)

    result = service.check_stock_position(store_id="47", sku=SKU, correlation_id=CORRELATION)

    assert result["on_hand_units"] == 12
    assert result["pos_units_sold_24h"] == 31
    assert result["gap_units"] == 19
    assert result["replenishment_threshold_units"] == 6
    assert result["replenishment_required"] is True
    assert result["assessment"] == "order_required"


def test_a_gap_of_exactly_the_threshold_does_not_require_an_order(
    runtime: Runtime, store_keys: None
) -> None:
    # The boundary the brief is most easily misread on. Six does not exceed six.
    client = StubStoreLink(on_hand=26, sold=[32])
    service = _service(runtime, client)

    result = service.check_stock_position(store_id="102", sku=SKU, correlation_id=CORRELATION)

    assert result["gap_units"] == 6
    assert result["replenishment_required"] is False
    assert result["assessment"] == "no_order_required"


def test_till_rows_are_aggregated_and_never_returned(runtime: Runtime, store_keys: None) -> None:
    # Rule ten: whatever reaches a model's context has left the boundary. Only
    # the two aggregate integers are allowed across it.
    client = StubStoreLink(on_hand=12, sold=[10, 11, 10])
    service = _service(runtime, client)

    result = service.check_stock_position(store_id="47", sku=SKU, correlation_id=CORRELATION)

    assert result["pos_units_sold_24h"] == 31
    assert result["pos_transaction_count"] == 3
    serialised = json.dumps(result)
    for leaked in ("basket_id", "BSK-", "loyalty_id", "LOY-", "payment_pan", "4111", "STAFF-"):
        assert leaked not in serialised


def test_checking_a_position_writes_the_buyers_audit_record(
    runtime: Runtime, store_keys: None
) -> None:
    service = _service(runtime, StubStoreLink())

    service.check_stock_position(store_id="47", sku=SKU, correlation_id=CORRELATION)

    records = _audit_records(runtime)
    assert [record["action"] for record in records] == ["stock_position_checked"]
    assert records[0]["outcome"] == "order_required"
    assert "gap of 19 units" in records[0]["context"]["explanation"]


def test_an_order_is_raised_for_the_measured_gap(runtime: Runtime, store_keys: None) -> None:
    client = StubStoreLink(on_hand=12, sold=[31])
    service = _service(runtime, client)

    result = service.raise_replenishment_order(store_id="47", sku=SKU, correlation_id=CORRELATION)

    assert result["order_quantity_units"] == 19
    assert result["order_id"] == "REP-1001"
    assert result["order_outcome"] == "created"
    assert result["counts_towards_daily_order_total"] is True
    assert client.orders_placed == [{"store_id": "47", "quantity_units": 19}]


def test_an_order_at_exactly_the_threshold_is_refused(runtime: Runtime, store_keys: None) -> None:
    # The write path applies the rule itself rather than trusting an earlier
    # read, so this refusal stands even if a model insists otherwise.
    client = StubStoreLink(on_hand=26, sold=[32])
    service = _service(runtime, client)

    with pytest.raises(OutOfPolicyOrderError) as caught:
        service.raise_replenishment_order(store_id="102", sku=SKU, correlation_id=CORRELATION)

    assert caught.value.code == "out_of_policy"
    assert "cannot be overridden by a caller" in caught.value.safe_message
    assert client.orders_placed == []


def test_a_refused_order_is_recorded_in_the_audit_trail(runtime: Runtime, store_keys: None) -> None:
    service = _service(runtime, StubStoreLink(on_hand=26, sold=[32]))

    with pytest.raises(OutOfPolicyOrderError):
        service.raise_replenishment_order(store_id="102", sku=SKU, correlation_id=CORRELATION)

    records = _audit_records(runtime)
    assert records[-1]["action"] == "replenishment_order_refused"
    assert records[-1]["outcome"] == "below_threshold"


def test_a_unit_that_is_not_ranged_cannot_be_replenished(
    runtime: Runtime, store_keys: None
) -> None:
    client = StubStoreLink(on_hand=None, sold=[31])
    service = _service(runtime, client)

    with pytest.raises(UnknownEntityError):
        service.raise_replenishment_order(store_id="47", sku=SKU, correlation_id=CORRELATION)

    assert client.orders_placed == []
    assert _audit_records(runtime)[-1]["outcome"] == "not_stocked"


def test_a_repeated_order_replays_rather_than_purchasing_again(
    runtime: Runtime, store_keys: None
) -> None:
    # The defect this repository exists to avoid: a replay whose flag is
    # dropped before reporting, so retries inflate reported spend.
    client = StubStoreLink(on_hand=12, sold=[31])
    service = _service(runtime, client)

    first = service.raise_replenishment_order(store_id="47", sku=SKU, correlation_id=CORRELATION)
    second = service.raise_replenishment_order(store_id="47", sku=SKU, correlation_id="retry")

    assert second["order_id"] == first["order_id"]
    assert second["order_outcome"] == "duplicate"
    assert second["counts_towards_daily_order_total"] is False
    assert len(client.orders_placed) == 1


def test_the_replay_flag_survives_into_the_audit_trail(runtime: Runtime, store_keys: None) -> None:
    service = _service(runtime, StubStoreLink())

    service.raise_replenishment_order(store_id="47", sku=SKU, correlation_id=CORRELATION)
    service.raise_replenishment_order(store_id="47", sku=SKU, correlation_id="retry")

    raised = [r for r in _audit_records(runtime) if r["action"] == "replenishment_order_raised"]
    assert [r["outcome"] for r in raised] == ["created", "duplicate"]
    assert raised[0]["context"]["counts_towards_daily_order_total"] is True
    assert raised[1]["context"]["counts_towards_daily_order_total"] is False


def test_the_deduplication_key_is_readable_and_carries_no_secret(
    runtime: Runtime, store_keys: None
) -> None:
    service = _service(runtime, StubStoreLink())

    result = service.raise_replenishment_order(store_id="47", sku=SKU, correlation_id=CORRELATION)

    assert result["idempotency_key"] == replenishment_idempotency_key(
        store_id="47", sku=SKU, order_quantity_units=19, ordering_date="2026-01-01"
    )
    assert "key-47" not in result["idempotency_key"]


def test_a_larger_gap_the_second_time_is_a_different_order(
    runtime: Runtime, store_keys: None
) -> None:
    # Quantity is part of the key on purpose. A buyer whose shelf emptied
    # further wants the larger order, not a silent replay of the old one.
    client = StubStoreLink(on_hand=12, sold=[31])
    service = _service(runtime, client)
    service.raise_replenishment_order(store_id="47", sku=SKU, correlation_id=CORRELATION)

    client.on_hand = 4
    second = service.raise_replenishment_order(store_id="47", sku=SKU, correlation_id="later")

    assert second["order_outcome"] == "created"
    assert second["order_quantity_units"] == 27
    assert len(client.orders_placed) == 2


def test_the_ordering_date_follows_the_stores_own_timezone(
    runtime: Runtime, store_keys: None
) -> None:
    # The frozen clock sits at 09:00 UTC, which is already the next day in
    # Auckland. Replenishment is a daily cycle in the store's own time.
    service = _service(runtime, StubStoreLink(timezone="Pacific/Auckland"))

    result = service.raise_replenishment_order(store_id="47", sku=SKU, correlation_id=CORRELATION)

    assert result["ordering_date"] == "2026-01-01"
    assert ":date=2026-01-01" in result["idempotency_key"]


def test_an_unknown_store_timezone_falls_back_to_coordinated_universal_time(
    runtime: Runtime, store_keys: None
) -> None:
    service = _service(runtime, StubStoreLink(timezone="Mars/Olympus_Mons"))

    result = service.raise_replenishment_order(store_id="47", sku=SKU, correlation_id=CORRELATION)

    assert result["ordering_date"] == "2026-01-01"


def test_an_order_status_is_reported_from_storelink(runtime: Runtime, store_keys: None) -> None:
    service = _service(runtime, StubStoreLink())

    result = service.get_replenishment_order_status(
        store_id="47", order_id="REP-1001", correlation_id=CORRELATION
    )

    assert result["order_id"] == "REP-1001"
    assert result["order_status"] == "accepted"
    assert _audit_records(runtime)[-1]["action"] == "replenishment_order_status_checked"


def test_a_store_with_no_credential_is_never_queried(runtime: Runtime, store_keys: None) -> None:
    # Failing closed means the network call is not attempted at all, so the
    # stub should record no calls whatsoever.
    client = StubStoreLink()
    service = _service(runtime, client)

    with pytest.raises(StoreCredentialMissingError):
        service.check_stock_position(store_id="999", sku=SKU, correlation_id=CORRELATION)

    assert client.calls == []


def test_a_status_lookup_for_a_store_with_no_credential_fails_closed(
    runtime: Runtime, store_keys: None
) -> None:
    client = StubStoreLink()
    service = _service(runtime, client)

    with pytest.raises(StoreCredentialMissingError):
        service.get_replenishment_order_status(
            store_id="999", order_id="REP-1001", correlation_id=CORRELATION
        )

    assert client.calls == []


@pytest.mark.parametrize("store_id", ["../etc", "", "abc", "-1"])
def test_a_malformed_store_identifier_is_rejected_at_the_boundary(
    runtime: Runtime, store_keys: None, store_id: str
) -> None:
    client = StubStoreLink()
    service = _service(runtime, client)

    with pytest.raises(InvalidRequestError):
        service.check_stock_position(store_id=store_id, sku=SKU, correlation_id=CORRELATION)

    assert client.calls == []


@pytest.mark.parametrize("sku", ["../etc", "", "not-a-sku"])
def test_a_malformed_stock_keeping_unit_is_rejected_at_the_boundary(
    runtime: Runtime, store_keys: None, sku: str
) -> None:
    client = StubStoreLink()
    service = _service(runtime, client)

    with pytest.raises(InvalidRequestError):
        service.check_stock_position(store_id="47", sku=sku, correlation_id=CORRELATION)

    assert client.calls == []


def test_the_credential_is_resolved_before_any_network_call(
    runtime: Runtime, store_keys: None
) -> None:
    # Ordering matters: the cheapest rejection runs first and the credential is
    # resolved before StoreLink is touched.
    client = StubStoreLink()
    service = _service(runtime, client)

    service.check_stock_position(store_id="47", sku=SKU, correlation_id=CORRELATION)

    assert client.calls[0] == "get_store"
