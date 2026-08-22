"""The HTTP client for Korral's StoreLink system.

Every outbound request carries the acting store's key in the documented header.
Requests are signed with the key belonging to the store being acted on, which is
also true of the two endpoints that carry no store in their path: those are only
ever called in the context of the store whose data the buyer is examining.

Only fields this client can see in a response are read. Where a response shape
is not documented in the brief, the assumption is recorded in
``docs/00-brief-analysis.md`` rather than guessed at silently.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from duvo_fde.credentials import resolve_store_key, store_key_secret_name
from duvo_fde.errors import UnknownEntityError, UpstreamError
from duvo_fde.runtime import Runtime

__all__ = ["AUTH_HEADER", "StoreLinkClient"]

_LOGGER = logging.getLogger(__name__)

AUTH_HEADER = "X-Korral-Store-Key"
"""The header StoreLink authenticates on, per the brief."""


class StoreLinkClient:
    """A thin, deliberate wrapper over the StoreLink endpoints we use."""

    def __init__(self, runtime: Runtime, client: httpx.Client | None = None) -> None:
        """Build the client.

        Args:
            runtime: The assembled runtime, for settings and secrets.
            client: An HTTP client to use. One is built from settings when
                omitted, which is the production path; tests pass their own.
        """
        self._runtime = runtime
        self._client = client or httpx.Client(
            base_url=runtime.settings.upstream_base_url,
            timeout=runtime.settings.upstream_timeout_seconds,
        )

    def get_store(self, store_id: str, *, correlation_id: str) -> dict[str, Any]:
        """Read one store's details.

        Args:
            store_id: A validated store identifier.
            correlation_id: The identifier joining logs to the audit trail.

        Returns:
            The store record.
        """
        return self._get(f"/v1/stores/{store_id}", store_id=store_id, correlation_id=correlation_id)

    def get_sku(self, store_id: str, sku: str, *, correlation_id: str) -> dict[str, Any]:
        """Read one stock keeping unit's details.

        This endpoint carries no store in its path, so it is signed with the key
        of the store whose data is being examined. Whether StoreLink in fact
        accepts a store key here is the first item on the day one confirmation
        list in ``DEPLOYMENT.md``.

        Args:
            store_id: The store providing the credential and the context.
            sku: A validated stock keeping unit identifier.
            correlation_id: The identifier joining logs to the audit trail.

        Returns:
            The stock keeping unit record.
        """
        return self._get(f"/v1/skus/{sku}", store_id=store_id, correlation_id=correlation_id)

    def get_supplier(
        self, store_id: str, supplier_id: str, *, correlation_id: str
    ) -> dict[str, Any]:
        """Read one supplier's details, including its lead time.

        Lead time is returned to the buyer as context. It never enters the
        threshold arithmetic: the brief states the rule and does not say lead
        time modifies it.

        Args:
            store_id: The store providing the credential and the context.
            supplier_id: The supplier identifier taken from the stock keeping
                unit record.
            correlation_id: The identifier joining logs to the audit trail.

        Returns:
            The supplier record.
        """
        return self._get(
            f"/v1/suppliers/{supplier_id}", store_id=store_id, correlation_id=correlation_id
        )

    def get_inventory(
        self, store_id: str, sku: str, *, correlation_id: str
    ) -> dict[str, Any] | None:
        """Read current units on hand for one stock keeping unit at one store.

        Args:
            store_id: A validated store identifier.
            sku: A validated stock keeping unit identifier.
            correlation_id: The identifier joining logs to the audit trail.

        Returns:
            The inventory record, or ``None`` when the stock keeping unit is not
            ranged at this store. Not being ranged is an outcome, not an error,
            and it is never reported as zero on hand.
        """
        try:
            return self._get(
                f"/v1/stores/{store_id}/inventory",
                store_id=store_id,
                correlation_id=correlation_id,
                params={"sku": sku},
            )
        except UnknownEntityError:
            return None

    def get_pos(
        self, store_id: str, sku: str, *, since: str, correlation_id: str
    ) -> list[dict[str, Any]]:
        """Read recent till transactions for one stock keeping unit at one store.

        The rows returned here carry basket, loyalty, payment and staff detail.
        None of it leaves this process: the caller aggregates these rows to a
        unit count and a row count, and only those two integers cross the
        boundary into a model's context.

        Args:
            store_id: A validated store identifier.
            sku: A validated stock keeping unit identifier.
            since: The start of the window, as a timestamp with an explicit
                offset.
            correlation_id: The identifier joining logs to the audit trail.

        Returns:
            The transaction rows in the window.
        """
        payload = self._get(
            f"/v1/stores/{store_id}/pos",
            store_id=store_id,
            correlation_id=correlation_id,
            params={"sku": sku, "since": since},
        )
        rows = payload.get("transactions", [])
        return list(rows) if isinstance(rows, list) else []

    def create_replenishment_order(
        self, store_id: str, *, sku: str, quantity_units: int, correlation_id: str
    ) -> dict[str, Any]:
        """Raise a replenishment order.

        This write is never retried inside this server. A blind retry across a
        credential rotation or an ambiguous failure can place a second real
        order against Korral's supplier, and this server does not retry a write
        it cannot prove did not happen.

        Args:
            store_id: A validated store identifier.
            sku: A validated stock keeping unit identifier.
            quantity_units: The quantity this server computed. It is never
                supplied by a caller.
            correlation_id: The identifier joining logs to the audit trail.

        Returns:
            The order record StoreLink returned.

        Raises:
            UpstreamError: StoreLink rejected the credential or did not answer.
                The order's state is unknown and must be confirmed before any
                further attempt.
        """
        key_name = store_key_secret_name(store_id)
        key = resolve_store_key(self._runtime.secrets, store_id)
        started = time.monotonic()
        path = f"/v1/stores/{store_id}/replenishment"
        try:
            response = self._client.post(
                path,
                headers={AUTH_HEADER: key},
                json={"sku": sku, "quantity_units": quantity_units},
            )
        except httpx.HTTPError as exc:
            self._log(path, "POST", 0, started, store_id, key_name, correlation_id, "unavailable")
            raise UpstreamError(
                f"Replenishment order for store {store_id}, stock keeping unit {sku} could "
                "not be confirmed. StoreLink did not answer, so the order may or may not "
                "exist. This server does not retry a write it cannot prove did not happen, "
                "because a blind retry can place a second real order against Korral's "
                "supplier. No order has been recorded here and no order identifier was "
                "returned. Confirm this store's outstanding orders in StoreLink before any "
                "further attempt.",
                details={"store_id": store_id, "sku": sku, "error": type(exc).__name__},
            ) from exc

        if response.status_code == 401:
            self._log(path, "POST", 401, started, store_id, key_name, correlation_id, "rejected")
            raise UpstreamError(
                f"Replenishment order for store {store_id}, stock keeping unit {sku} could "
                "not be confirmed. StoreLink rejected this server's credential during the "
                "write, which is what a key rotating mid request looks like. This server "
                "does not retry a write it cannot prove did not happen, because a blind "
                "retry can place a second real order against Korral's supplier. No order "
                "has been recorded here and no order identifier was returned. Confirm this "
                "store's outstanding orders in StoreLink before any further attempt, and if "
                "you hold an order identifier, call get_replenishment_order_status.",
                details={"store_id": store_id, "sku": sku, "secret": key_name},
            )

        if response.status_code >= 400:
            self._log(
                path,
                "POST",
                response.status_code,
                started,
                store_id,
                key_name,
                correlation_id,
                "unavailable",
            )
            raise UpstreamError(
                f"StoreLink did not accept the replenishment order for store {store_id}, "
                f"stock keeping unit {sku}. The order's state is unknown and this server "
                "will not retry it. Confirm this store's outstanding orders in StoreLink.",
                details={"store_id": store_id, "status": response.status_code},
            )

        self._log(
            path, "POST", response.status_code, started, store_id, key_name, correlation_id, "ok"
        )
        return dict(response.json())

    def get_replenishment_order(
        self, store_id: str, order_id: str, *, correlation_id: str
    ) -> dict[str, Any]:
        """Read one replenishment order's current status.

        Args:
            store_id: A validated store identifier.
            order_id: The order identifier.
            correlation_id: The identifier joining logs to the audit trail.

        Returns:
            The order record.
        """
        return self._get(
            f"/v1/stores/{store_id}/replenishment/{order_id}",
            store_id=store_id,
            correlation_id=correlation_id,
        )

    def _get(
        self,
        path: str,
        *,
        store_id: str,
        correlation_id: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Perform one authenticated read, with the rotation policy applied.

        A rejected credential is either a rotation or a revocation, and the two
        need different sentences. The key is re-read and compared: if it changed
        between our read and StoreLink's check, the read is retried once, which
        is free because a read has no side effect. If it did not change, the key
        is wrong or revoked and an identical request would produce an identical
        rejection, so it is not retried.

        Args:
            path: The StoreLink path.
            store_id: The store whose key signs the request.
            correlation_id: The identifier joining logs to the audit trail.
            params: Query parameters, if any.

        Returns:
            The decoded response body.

        Raises:
            UnknownEntityError: StoreLink does not recognise the identifier.
            UpstreamError: StoreLink rejected the credential, failed, or
                returned something unusable.
        """
        key_name = store_key_secret_name(store_id)
        for attempt in (1, 2):
            key = resolve_store_key(self._runtime.secrets, store_id)
            started = time.monotonic()
            try:
                response = self._client.get(path, headers={AUTH_HEADER: key}, params=params)
            except httpx.HTTPError as exc:
                self._log(
                    path,
                    "GET",
                    0,
                    started,
                    store_id,
                    key_name,
                    correlation_id,
                    "unavailable",
                    attempt,
                )
                raise UpstreamError(
                    f"StoreLink did not answer when reading data for store {store_id}. No "
                    "figure was read, so nothing was assessed for that store and no order "
                    "was raised on a guess.",
                    details={"store_id": store_id, "path": path, "error": type(exc).__name__},
                ) from exc

            if response.status_code == 401:
                rotated = resolve_store_key(self._runtime.secrets, store_id) != key
                self._log(
                    path,
                    "GET",
                    401,
                    started,
                    store_id,
                    key_name,
                    correlation_id,
                    "retried_after_rotation" if rotated and attempt == 1 else "rejected",
                    attempt,
                    rotated,
                )
                if rotated and attempt == 1:
                    continue
                raise UpstreamError(
                    f"StoreLink rejected this server's credential for store {store_id}. The "
                    "key held for that store is not currently accepted, which usually means "
                    "it was revoked or replaced without the new value reaching the secrets "
                    "mount. Korral information technology: confirm the current key for that "
                    "store.",
                    details={"store_id": store_id, "secret": key_name},
                )

            if response.status_code == 404:
                self._log(
                    path,
                    "GET",
                    404,
                    started,
                    store_id,
                    key_name,
                    correlation_id,
                    "not_found",
                    attempt,
                )
                raise UnknownEntityError(
                    f"StoreLink does not recognise that identifier for store {store_id}.",
                    details={"store_id": store_id, "path": path},
                )

            if response.status_code >= 400:
                self._log(
                    path,
                    "GET",
                    response.status_code,
                    started,
                    store_id,
                    key_name,
                    correlation_id,
                    "unavailable",
                    attempt,
                )
                raise UpstreamError(
                    f"StoreLink returned an error reading data for store {store_id}. Nothing "
                    "was assessed for that store.",
                    details={"store_id": store_id, "status": response.status_code},
                )

            self._log(
                path,
                "GET",
                response.status_code,
                started,
                store_id,
                key_name,
                correlation_id,
                "ok",
                attempt,
            )
            return dict(response.json())

        raise UpstreamError(  # pragma: no cover - the loop always returns or raises
            f"StoreLink could not be read for store {store_id}.",
            details={"store_id": store_id},
        )

    def _log(
        self,
        path: str,
        method: str,
        status: int,
        started: float,
        store_id: str,
        key_name: str,
        correlation_id: str,
        outcome: str,
        attempt: int = 1,
        rotation_retry: bool = False,
    ) -> None:
        """Emit the one diagnostic line an engineer needs for this request.

        The path is logged without its query string. The credential is
        identified by the name of the file it came from and never by its value.

        Args:
            path: The StoreLink path.
            method: The HTTP method.
            status: The response status, or zero when there was no response.
            started: The monotonic timestamp the request began at.
            store_id: The acting store.
            key_name: The name of the secret used, never its value.
            correlation_id: The identifier joining logs to the audit trail.
            outcome: A short, countable outcome label.
            attempt: Which attempt this was.
            rotation_retry: Whether a rotation was detected.
        """
        _LOGGER.info(
            "StoreLink request.",
            extra={
                "fields": {
                    "correlation_id": correlation_id,
                    "store_id": store_id,
                    "upstream_method": method,
                    "upstream_path": path,
                    "upstream_status": status,
                    "duration_ms": int((time.monotonic() - started) * 1000),
                    "attempt": attempt,
                    "store_key_secret_name": key_name,
                    "store_key_rotations": self._runtime.secrets.state(key_name).rotations,
                    "store_key_degraded": self._runtime.secrets.state(key_name).degraded,
                    "rotation_retry": rotation_retry,
                    "outcome": outcome,
                }
            },
        )
