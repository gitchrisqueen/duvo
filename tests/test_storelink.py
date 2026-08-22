"""The HTTP client for Korral's StoreLink system.

Every test here drives a scripted transport rather than a socket, so the suite
stays offline and deterministic. What is being pinned is the client's policy
rather than the plumbing: which requests carry which key, what a rejected
credential means, and above all that a write is never retried blindly.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from duvo_fde.credentials import StoreCredentialMissingError
from duvo_fde.errors import UnknownEntityError, UpstreamError
from duvo_fde.runtime import Runtime
from duvo_fde.storelink import AUTH_HEADER, StoreLinkClient

from .conftest import rotate_secret_by_rename, write_secret

BASE_URL = "http://upstream.test"
CORRELATION = "test-correlation"


def _client(
    runtime: Runtime, handler: Callable[[httpx.Request], httpx.Response]
) -> StoreLinkClient:
    """Build a client whose transport is a scripted handler."""
    return StoreLinkClient(
        runtime,
        httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE_URL),
    )


@pytest.fixture
def store_47(secrets_dir: Path) -> str:
    """Configure store 47's credential and return its value."""
    write_secret(secrets_dir, "korral_store_key_47", "key-47")
    return "key-47"


def test_a_read_carries_the_acting_stores_key(runtime: Runtime, store_47: str) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["key"] = request.headers[AUTH_HEADER]
        return httpx.Response(200, json={"store_id": "47", "timezone": "Europe/Prague"})

    store = _client(runtime, handler).get_store("47", correlation_id=CORRELATION)

    assert store["store_id"] == "47"
    assert seen["path"] == "/v1/stores/47"
    assert seen["key"] == store_47


def test_the_stock_keeping_unit_endpoint_is_signed_with_the_acting_stores_key(
    runtime: Runtime, store_47: str
) -> None:
    # This endpoint carries no store in its path. It is still signed with the
    # key of the store whose data is being examined, which is the day one
    # confirmation item recorded in DEPLOYMENT.md.
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["key"] = request.headers[AUTH_HEADER]
        return httpx.Response(200, json={"sku": "8847291", "name": "Madeta butter 250g"})

    record = _client(runtime, handler).get_sku("47", "8847291", correlation_id=CORRELATION)

    assert record["name"] == "Madeta butter 250g"
    assert seen["path"] == "/v1/skus/8847291"
    assert seen["key"] == store_47


def test_a_supplier_is_read_with_the_acting_stores_key(runtime: Runtime, store_47: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/suppliers/SUP-1"
        assert request.headers[AUTH_HEADER] == store_47
        return httpx.Response(200, json={"supplier_id": "SUP-1", "lead_time_days": 2})

    supplier = _client(runtime, handler).get_supplier("47", "SUP-1", correlation_id=CORRELATION)

    assert supplier["lead_time_days"] == 2


def test_inventory_returns_the_record_when_the_unit_is_ranged(
    runtime: Runtime, store_47: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["sku"] == "8847291"
        return httpx.Response(200, json={"on_hand_units": 12})

    inventory = _client(runtime, handler).get_inventory("47", "8847291", correlation_id=CORRELATION)

    assert inventory is not None
    assert inventory["on_hand_units"] == 12


def test_a_unit_that_is_not_ranged_is_none_rather_than_zero(
    runtime: Runtime, store_47: str
) -> None:
    # Not ranged and zero on hand are different facts. Reporting the first as
    # the second would invent a gap and could raise an order for a product the
    # store does not carry.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "not found"})

    inventory = _client(runtime, handler).get_inventory("47", "8847291", correlation_id=CORRELATION)

    assert inventory is None


def test_till_rows_are_returned_for_the_caller_to_aggregate(
    runtime: Runtime, store_47: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["since"] == "2026-01-01T09:00:00+00:00"
        return httpx.Response(
            200,
            json={"transactions": [{"units": 3}, {"units": 4}]},
        )

    rows = _client(runtime, handler).get_pos(
        "47", "8847291", since="2026-01-01T09:00:00+00:00", correlation_id=CORRELATION
    )

    assert rows == [{"units": 3}, {"units": 4}]


def test_a_till_payload_of_an_unexpected_shape_reads_as_no_rows(
    runtime: Runtime, store_47: str
) -> None:
    # Rule five: only read what the upstream actually returns. A payload whose
    # transactions field is not a list must not raise part way through a buyer's
    # task.
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"transactions": None})

    rows = _client(runtime, handler).get_pos(
        "47", "8847291", since="2026-01-01T09:00:00+00:00", correlation_id=CORRELATION
    )

    assert rows == []


def test_a_missing_till_field_reads_as_no_rows(runtime: Runtime, store_47: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    rows = _client(runtime, handler).get_pos(
        "47", "8847291", since="2026-01-01T09:00:00+00:00", correlation_id=CORRELATION
    )

    assert rows == []


def test_a_rejected_read_is_retried_once_when_the_key_rotated_underneath_it(
    runtime: Runtime, secrets_dir: Path, store_47: str
) -> None:
    # A rotation mid request is the benign case: the key we signed with is no
    # longer the current one, so signing again with the new value is free
    # because a read has no side effect.
    attempts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request.headers[AUTH_HEADER])
        if len(attempts) == 1:
            rotate_secret_by_rename(secrets_dir, "korral_store_key_47", "key-47-rotated")
            return httpx.Response(401, json={"error": "unauthorised"})
        return httpx.Response(200, json={"store_id": "47"})

    store = _client(runtime, handler).get_store("47", correlation_id=CORRELATION)

    assert store["store_id"] == "47"
    assert attempts == ["key-47", "key-47-rotated"]


def test_a_rejected_read_is_not_retried_when_the_key_did_not_change(
    runtime: Runtime, store_47: str
) -> None:
    # Nothing rotated, so an identical request would be rejected identically.
    # Retrying would only spend the customer's rate limit.
    attempts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request.headers[AUTH_HEADER])
        return httpx.Response(401, json={"error": "unauthorised"})

    with pytest.raises(UpstreamError) as caught:
        _client(runtime, handler).get_store("47", correlation_id=CORRELATION)

    assert len(attempts) == 1
    assert "47" in caught.value.safe_message
    assert store_47 not in caught.value.safe_message


def test_an_unrecognised_identifier_is_reported_as_an_unknown_entity(
    runtime: Runtime, store_47: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "not found"})

    with pytest.raises(UnknownEntityError):
        _client(runtime, handler).get_store("47", correlation_id=CORRELATION)


def test_an_upstream_failure_on_a_read_assesses_nothing(runtime: Runtime, store_47: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "unavailable"})

    with pytest.raises(UpstreamError) as caught:
        _client(runtime, handler).get_store("47", correlation_id=CORRELATION)

    assert "Nothing was assessed" in caught.value.safe_message


def test_a_read_that_never_reaches_storelink_raises_upstream(
    runtime: Runtime, store_47: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route to host")

    with pytest.raises(UpstreamError) as caught:
        _client(runtime, handler).get_store("47", correlation_id=CORRELATION)

    assert "no order was raised on a guess" in caught.value.safe_message


def test_a_write_sends_the_quantity_this_server_computed(runtime: Runtime, store_47: str) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["method"] = request.method
        seen["body"] = httpx.Response(200, content=request.content).json()
        return httpx.Response(200, json={"order_id": "REP-1001", "status": "accepted"})

    order = _client(runtime, handler).create_replenishment_order(
        "47", sku="8847291", quantity_units=19, correlation_id=CORRELATION
    )

    assert order == {"order_id": "REP-1001", "status": "accepted"}
    assert seen["method"] == "POST"
    assert seen["path"] == "/v1/stores/47/replenishment"
    assert seen["body"] == {"sku": "8847291", "quantity_units": 19}


def test_a_rejected_write_is_never_retried(runtime: Runtime, store_47: str) -> None:
    # This is the expensive mistake. A retried write can place a second real
    # order against Korral's supplier, so a rejection during a write is
    # reported as unconfirmed rather than attempted again.
    attempts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request.method)
        return httpx.Response(401, json={"error": "unauthorised"})

    with pytest.raises(UpstreamError) as caught:
        _client(runtime, handler).create_replenishment_order(
            "47", sku="8847291", quantity_units=19, correlation_id=CORRELATION
        )

    assert attempts == ["POST"]
    assert "does not retry a write it cannot prove did not happen" in caught.value.safe_message


def test_a_failed_write_reports_the_order_state_as_unknown(runtime: Runtime, store_47: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    with pytest.raises(UpstreamError) as caught:
        _client(runtime, handler).create_replenishment_order(
            "47", sku="8847291", quantity_units=19, correlation_id=CORRELATION
        )

    assert "state is unknown" in caught.value.safe_message


def test_a_write_that_never_reaches_storelink_reports_it_may_or_may_not_exist(
    runtime: Runtime, store_47: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    with pytest.raises(UpstreamError) as caught:
        _client(runtime, handler).create_replenishment_order(
            "47", sku="8847291", quantity_units=19, correlation_id=CORRELATION
        )

    assert "may or may not exist" in caught.value.safe_message


def test_a_write_for_a_store_with_no_credential_never_reaches_the_network(runtime: Runtime) -> None:
    # No credential is configured, so no request should be attempted at all.
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("StoreLink was called for a store with no credential")

    with pytest.raises(StoreCredentialMissingError):
        _client(runtime, handler).create_replenishment_order(
            "999", sku="8847291", quantity_units=19, correlation_id=CORRELATION
        )


def test_an_order_status_is_read_from_storelink(runtime: Runtime, store_47: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/stores/47/replenishment/REP-1001"
        return httpx.Response(200, json={"order_id": "REP-1001", "status": "accepted"})

    order = _client(runtime, handler).get_replenishment_order(
        "47", "REP-1001", correlation_id=CORRELATION
    )

    assert order["status"] == "accepted"


def test_a_client_is_built_from_settings_when_none_is_supplied(runtime: Runtime) -> None:
    # The production path. Nothing is sent here; only the wiring is checked.
    client = StoreLinkClient(runtime)

    assert client._client.base_url == httpx.URL(runtime.settings.upstream_base_url)
