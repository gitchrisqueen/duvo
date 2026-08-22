"""A deliberately unhelpful stand-in for the customer's upstream system.

The mock is generic: it serves whatever JSON fixture it is given, so the domain
written during the exercise supplies its own data without this file changing.

Three behaviours are intentional, because they are the behaviours real
integrations actually have and the ones a submission is most likely to get
wrong:

1. **It authenticates every request** against a key read from disk on each call,
   so a key rotation can be demonstrated end to end against a running stack.
2. **It is not idempotent.** Posting the same payload twice creates two records.
   Deduplication is our server's job, and a mock that quietly deduplicated would
   hide whether we actually do it.
3. **It returns only the fields in the fixture.** Nothing is invented, so code
   that reads a field the upstream never sends fails here rather than in front
   of a reviewer.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request

__all__ = ["build_app"]


def _load_fixtures(path: Path | None) -> dict[str, list[dict[str, Any]]]:
    """Load collections from a fixture file.

    Args:
        path: Fixture file containing an object mapping collection names to
            lists of records. ``None`` yields empty collections.

    Returns:
        The loaded collections.
    """
    if path is None or not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(name): list(records) for name, records in data.items()}


def _read_expected_key() -> str | None:
    """Read the API key the mock currently expects.

    The key is re-read on every request so that rotating the file is observable
    from outside the process, which is what makes the rotation runbook testable.

    Returns:
        The expected key, or ``None`` when authentication is disabled.
    """
    key_path = os.environ.get("MOCK_UPSTREAM_API_KEY_FILE")
    if key_path:
        try:
            return Path(key_path).read_text(encoding="utf-8").strip()
        except OSError:
            return None
    return os.environ.get("MOCK_UPSTREAM_API_KEY") or None


def build_app() -> FastAPI:
    """Construct the mock application.

    Returns:
        A FastAPI application serving the configured fixtures.
    """
    fixtures_path = os.environ.get("MOCK_UPSTREAM_FIXTURES")
    collections = _load_fixtures(Path(fixtures_path) if fixtures_path else None)
    writes: dict[str, list[dict[str, Any]]] = {}

    app = FastAPI(title="Mock upstream", docs_url=None, redoc_url=None)

    def _authenticate(supplied: str | None) -> None:
        """Reject a request whose key does not match the current expected key.

        Args:
            supplied: The value of the ``X-API-Key`` header.

        Raises:
            HTTPException: With status 401 when the key is missing or wrong.
        """
        expected = _read_expected_key()
        if expected is None:
            return
        if supplied != expected:
            raise HTTPException(status_code=401, detail="Invalid API key.")

    # StoreLink shaped routes, registered above the generic collection routes so
    # that FastAPI matches them first. The generic routes and their behaviour are
    # left exactly as they were, because scripts/smoke.sh proves the stack with
    # them and trading a working proof for an unproven one is a bad exchange.
    #
    # GET /v1/stores is deliberately not implemented. If anyone ever wires a tool
    # to it, it fails here and visibly rather than working in the mock and
    # failing inside Korral.

    def _store_key(store_id: str) -> str | None:
        """Read the expected key for one store, re-reading on every request.

        Args:
            store_id: The store whose key is wanted.

        Returns:
            The key, or ``None`` when no file is present.
        """
        directory = os.environ.get("MOCK_STORELINK_KEY_DIR", "/run/secrets")
        try:
            return (
                (Path(directory) / f"korral_store_key_{store_id}")
                .read_text(encoding="utf-8")
                .strip()
            )
        except OSError:
            return None

    def _authenticate_store(store_id: str, supplied: str | None) -> None:
        """Reject a request not carrying that store's own key.

        Per-store scoping is enforced here rather than assumed. Without it the
        whole per-store credential design would be untested and the demonstration
        would prove nothing.

        Args:
            store_id: The store being acted on.
            supplied: The value of the ``X-Korral-Store-Key`` header.

        Raises:
            HTTPException: With status 401 when the key is missing or wrong.
        """
        expected = _store_key(store_id)
        if expected is None or supplied != expected:
            raise HTTPException(status_code=401, detail="Invalid store key.")

    def _authenticate_any_store(supplied: str | None) -> None:
        """Accept any currently configured store key.

        The stock keeping unit and supplier endpoints carry no store in their
        path, so no single key is the correct one for them. Accepting any
        configured store key is the executable form of that assumption, and it is
        the first item on the day one confirmation list for Korral.

        Args:
            supplied: The value of the ``X-Korral-Store-Key`` header.

        Raises:
            HTTPException: With status 401 when the key matches no store.
        """
        directory = Path(os.environ.get("MOCK_STORELINK_KEY_DIR", "/run/secrets"))
        for candidate in sorted(directory.glob("korral_store_key_*")):
            try:
                if supplied == candidate.read_text(encoding="utf-8").strip():
                    return
            except OSError:  # pragma: no cover - unreadable file
                continue
        raise HTTPException(status_code=401, detail="Invalid store key.")

    def _find(collection: str, **match: str) -> dict[str, Any] | None:
        """Return the first record in a collection matching every field given.

        Args:
            collection: The fixture collection to search.
            **match: Field values that must all match.

        Returns:
            The record, or ``None``.
        """
        for record in collections.get(collection, []) + writes.get(collection, []):
            if all(str(record.get(k)) == v for k, v in match.items()):
                return record
        return None

    @app.get("/v1/stores/{store_id}")
    def storelink_store(
        store_id: str, x_korral_store_key: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Return one store's details.

        Args:
            store_id: The store wanted.
            x_korral_store_key: That store's key.

        Returns:
            The store record.

        Raises:
            HTTPException: 404 when the store is unknown.
        """
        _authenticate_store(store_id, x_korral_store_key)
        record = _find("stores", store_id=store_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Unknown store.")
        return record

    @app.get("/v1/stores/{store_id}/inventory")
    def storelink_inventory(
        store_id: str, sku: str, x_korral_store_key: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Return current units on hand for one stock keeping unit at one store.

        Args:
            store_id: The store wanted.
            sku: The stock keeping unit wanted.
            x_korral_store_key: That store's key.

        Returns:
            The inventory record.

        Raises:
            HTTPException: 404 when the stock keeping unit is not ranged there.
        """
        _authenticate_store(store_id, x_korral_store_key)
        record = _find("inventory", store_id=store_id, sku=sku)
        if record is None:
            raise HTTPException(status_code=404, detail="Not ranged at this store.")
        return record

    @app.get("/v1/stores/{store_id}/pos")
    def storelink_pos(
        store_id: str,
        sku: str,
        since: str | None = None,
        x_korral_store_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        """Return recent till transactions for one stock keeping unit at one store.

        Timestamps are rendered at request time from a fixture offset, so the
        window is genuinely exercised and the demonstration does not go stale.

        Args:
            store_id: The store wanted.
            sku: The stock keeping unit wanted.
            since: The start of the window.
            x_korral_store_key: That store's key.

        Returns:
            The transactions falling inside the window.
        """
        _authenticate_store(store_id, x_korral_store_key)
        now = datetime.now(UTC)
        cutoff = None
        if since:
            try:
                cutoff = datetime.fromisoformat(since)
            except ValueError:
                raise HTTPException(status_code=400, detail="Malformed since.") from None
        rows: list[dict[str, Any]] = []
        for record in collections.get("pos", []):
            if str(record.get("store_id")) != store_id or str(record.get("sku")) != sku:
                continue
            sold_at = now - timedelta(minutes=int(record.get("sold_at_minutes_ago", 0)))
            if cutoff is not None and sold_at < cutoff:
                continue
            row = {k: v for k, v in record.items() if k != "sold_at_minutes_ago"}
            row["sold_at"] = sold_at.isoformat()
            rows.append(row)
        return {"store_id": store_id, "sku": sku, "transactions": rows}

    @app.post("/v1/stores/{store_id}/replenishment", status_code=201)
    async def storelink_replenishment(
        store_id: str, request: Request, x_korral_store_key: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Raise a replenishment order.

        Deliberately not idempotent: two identical posts produce two orders.
        That is what makes the deduplication layer in this server load bearing
        rather than decorative, and it is worth showing.

        Args:
            store_id: The store ordering.
            request: The incoming request, carrying the order body.
            x_korral_store_key: That store's key.

        Returns:
            The created order.
        """
        _authenticate_store(store_id, x_korral_store_key)
        payload = await request.json()
        bucket = writes.setdefault("replenishment", [])
        order = {
            "id": f"REP-{1000 + len(bucket) + 1}",
            "order_id": f"REP-{1000 + len(bucket) + 1}",
            "store_id": store_id,
            "sku": str(payload.get("sku")),
            "quantity_units": int(payload.get("quantity_units", 0)),
            "status": "accepted",
            "raised_at": datetime.now(UTC).isoformat(),
        }
        bucket.append(order)
        return order

    @app.get("/v1/stores/{store_id}/replenishment/{order_id}")
    def storelink_order_status(
        store_id: str, order_id: str, x_korral_store_key: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Return one replenishment order's current status.

        Args:
            store_id: The store the order was raised at.
            order_id: The order wanted.
            x_korral_store_key: That store's key.

        Returns:
            The order record.

        Raises:
            HTTPException: 404 when the order is unknown at that store.
        """
        _authenticate_store(store_id, x_korral_store_key)
        record = _find("replenishment", store_id=store_id, order_id=order_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Unknown order.")
        return record

    @app.get("/v1/skus/{sku}")
    def storelink_sku(
        sku: str, x_korral_store_key: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Return one stock keeping unit's details.

        Args:
            sku: The stock keeping unit wanted.
            x_korral_store_key: Any configured store key.

        Returns:
            The stock keeping unit record.

        Raises:
            HTTPException: 404 when unknown.
        """
        _authenticate_any_store(x_korral_store_key)
        record = _find("skus", sku=sku)
        if record is None:
            raise HTTPException(status_code=404, detail="Unknown sku.")
        return record

    @app.get("/v1/suppliers/{supplier_id}")
    def storelink_supplier(
        supplier_id: str, x_korral_store_key: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Return one supplier's details, including its lead time.

        Args:
            supplier_id: The supplier wanted.
            x_korral_store_key: Any configured store key.

        Returns:
            The supplier record.

        Raises:
            HTTPException: 404 when unknown.
        """
        _authenticate_any_store(x_korral_store_key)
        record = _find("suppliers", supplier_id=supplier_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Unknown supplier.")
        return record

    @app.get("/__health")
    def health() -> dict[str, str]:
        """Report that the mock is serving.

        Returns:
            A static status payload. Unauthenticated by design.
        """
        return {"status": "ok"}

    @app.get("/{collection}")
    def list_records(
        collection: str, x_api_key: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """List the records in a collection.

        Args:
            collection: Collection name.
            x_api_key: Caller-supplied API key.

        Returns:
            The records plus the number written since startup.

        Raises:
            HTTPException: With status 404 when the collection is unknown.
        """
        _authenticate(x_api_key)
        if collection not in collections:
            raise HTTPException(status_code=404, detail="Unknown collection.")
        return {"items": collections[collection] + writes.get(collection, [])}

    @app.get("/{collection}/{record_id}")
    def get_record(
        collection: str, record_id: str, x_api_key: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Return one record by id.

        Args:
            collection: Collection name.
            record_id: Identifier of the record.
            x_api_key: Caller-supplied API key.

        Returns:
            The matching record.

        Raises:
            HTTPException: With status 404 when the record does not exist.
        """
        _authenticate(x_api_key)
        for record in collections.get(collection, []) + writes.get(collection, []):
            if str(record.get("id")) == record_id:
                return record
        raise HTTPException(status_code=404, detail="Unknown record.")

    @app.post("/{collection}", status_code=201)
    async def create_record(
        collection: str, request: Request, x_api_key: str | None = Header(default=None)
    ) -> dict[str, Any]:
        """Create a record. Deliberately not idempotent.

        Args:
            collection: Collection name.
            request: The incoming request, read as JSON.
            x_api_key: Caller-supplied API key.

        Returns:
            The created record, including the id the mock assigned.
        """
        _authenticate(x_api_key)
        payload = await request.json()
        bucket = writes.setdefault(collection, [])
        record = {"id": f"{collection}-{len(bucket) + 1}", **payload}
        bucket.append(record)
        return record

    return app


app = build_app()
