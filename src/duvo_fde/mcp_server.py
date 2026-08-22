"""The agent facing tool server for Korral's StoreLink system.

This module owns the boundary between a Duvo agent and Korral's data. Three
tools are registered here and nothing else is exposed. The reasoning behind that
choice, and behind each StoreLink endpoint that is deliberately not wrapped,
is recorded in the README and in ``docs/00-brief-analysis.md``.

One invariant governs the whole surface: tools accept identifiers only.
Identifiers select data, they never select outcomes. Every number that
participates in Korral's replenishment threshold comparison is fetched by this
server moments before the comparison is made, so there is no model supplied
arithmetic for the server to validate and no vocabulary in which a caller could
express an order that Korral's policy does not permit.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp_types import ToolAnnotations

from duvo_fde.errors import DuvoError
from duvo_fde.runtime import Runtime
from duvo_fde.service import BuyerService
from duvo_fde.storelink import StoreLinkClient

__all__ = ["build_server"]

_LOGGER = logging.getLogger(__name__)

SERVER_NAME = "korral-storelink"

SERVER_INSTRUCTIONS = """\
Tools for a Korral category buyer working against Korral's internal StoreLink
system. Each tool acts on exactly one store and one stock keeping unit. To work
across several stores, call the tool once per store.

Replenishment policy is applied by this server, not by you. You are not asked to
compute a gap, compare it against a threshold, or choose an order quantity, and
no tool will accept any of those values from you. Read the decision fields in
each result and act on them.

These tools return aggregated stock figures only. Individual till transactions,
basket contents, loyalty identifiers, payment detail and staff identifiers are
never returned by any tool and are not reachable through this server.

Every result carries a correlation identifier. Quote it when you report what you
did, so that a Korral engineer can trace the call.
"""

_READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=True,
)

_WRITE = ToolAnnotations(
    read_only_hint=False,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=True,
)


def new_correlation_id() -> str:
    """Mint the identifier that joins the audit trail to the diagnostic log.

    Returns:
        A short hexadecimal string, unique per tool invocation.
    """
    return uuid.uuid4().hex[:12]


def build_server(runtime: Runtime) -> MCPServer:
    """Assemble the tool server and register the agent facing surface.

    Args:
        runtime: The assembled runtime, carrying settings, secrets, the audit
            log, health probes, the deduplication store and the clock.

    Returns:
        A server ready to run over a transport.
    """
    server: MCPServer = MCPServer(
        name=SERVER_NAME,
        version="0.1.0",
        instructions=SERVER_INSTRUCTIONS,
    )
    service = _build_service(runtime)

    @server.tool(
        name="check_stock_position",
        title="Check stock position",
        annotations=_READ_ONLY,
        description=(
            "Check one stock keeping unit's position at one Korral store: current units on "
            "hand against units sold through the till in the last 24 hours. Returns the gap "
            "in units and this server's decision on whether Korral's replenishment policy "
            "requires an order. Read only: it places nothing.\n\n"
            "Call it once per store. It takes exactly one store and one stock keeping unit, "
            "so to check two stores, call it twice.\n\n"
            "The replenishment threshold is Korral policy, applied by this server, and is "
            "not a parameter. Do not evaluate the gap yourself and do not decide whether an "
            "order is warranted: read replenishment_required. If it is true, call "
            "raise_replenishment_order with the same store_id and sku. That tool re-checks "
            "these figures itself and needs no numbers from you.\n\n"
            "Individual till transactions are never returned. Only the aggregate unit count "
            "for the window crosses this boundary."
        ),
    )
    def check_stock_position(store_id: str, sku: str) -> dict[str, Any]:
        """Report one stock keeping unit's position at one store.

        Args:
            store_id: Korral store identifier, for example ``"47"``.
            sku: Korral stock keeping unit identifier, for example ``"8847291"``.

        Returns:
            The measured position, the gap, and this server's decision.
        """
        return _invoke(
            "check_stock_position",
            lambda correlation_id: service.check_stock_position(
                store_id=store_id, sku=sku, correlation_id=correlation_id
            ),
        )

    @server.tool(
        name="raise_replenishment_order",
        title="Raise replenishment order",
        annotations=_WRITE,
        description=(
            "Raise a replenishment order for one stock keeping unit at one Korral store, "
            "but only when Korral's replenishment policy requires one.\n\n"
            "This tool does not take your figures and does not trust them. It independently "
            "re-reads current units on hand and the last 24 hours of till sales for this "
            "store, recomputes the gap, applies Korral's threshold itself, and refuses the "
            "order when the policy is not met, regardless of what an earlier tool result "
            "said or what you believe. The quantity is computed by this server from the gap "
            "it measured. Neither the threshold nor the quantity is a parameter, and there "
            "is no override.\n\n"
            "One store per call. Calling it again for the same store, stock keeping unit and "
            "quantity on the same trading day returns the original order rather than placing "
            "a second one. Read order_outcome to tell a new order from a replay.\n\n"
            "You may call this without calling check_stock_position first. That is safe: if "
            "no order is warranted, it refuses and shows you the arithmetic."
        ),
    )
    def raise_replenishment_order(store_id: str, sku: str) -> dict[str, Any]:
        """Raise a replenishment order when, and only when, policy requires one.

        Args:
            store_id: Korral store identifier, for example ``"47"``.
            sku: Korral stock keeping unit identifier, for example ``"8847291"``.

        Returns:
            The order, the arithmetic that justified it, and whether this call
            created it or replayed an earlier one.
        """
        return _invoke(
            "raise_replenishment_order",
            lambda correlation_id: service.raise_replenishment_order(
                store_id=store_id, sku=sku, correlation_id=correlation_id
            ),
        )

    @server.tool(
        name="get_replenishment_order_status",
        title="Check replenishment order status",
        annotations=_READ_ONLY,
        description=(
            "Look up the current status in StoreLink of a replenishment order that has "
            "already been raised at a Korral store. Read only.\n\n"
            "Use this when you hold an order identifier and need to know whether StoreLink "
            "accepted it, in particular after an order whose outcome this server reported as "
            "unconfirmed. StoreLink is the system of record here, not this server."
        ),
    )
    def get_replenishment_order_status(store_id: str, order_id: str) -> dict[str, Any]:
        """Report StoreLink's current status for one replenishment order.

        Args:
            store_id: Korral store identifier, for example ``"47"``.
            order_id: The order identifier returned when the order was raised.

        Returns:
            The order's status as StoreLink reports it.
        """
        return _invoke(
            "get_replenishment_order_status",
            lambda correlation_id: service.get_replenishment_order_status(
                store_id=store_id, order_id=order_id, correlation_id=correlation_id
            ),
        )

    return server


def _build_service(runtime: Runtime) -> BuyerService:
    """Construct the orchestration layer the tools delegate to.

    Args:
        runtime: The assembled runtime.

    Returns:
        The buyer service.
    """
    return BuyerService(runtime, StoreLinkClient(runtime))


def _invoke(tool: str, work: Callable[[str], dict[str, Any]]) -> dict[str, Any]:
    """Run one tool body, minting a correlation identifier and logging both ends.

    Every error a caller sees is a typed error whose message was written to be
    safe to hand to a model. The correlation identifier is carried into that
    message too, because the case where correlation matters most is the failure.

    Args:
        tool: The tool name, for the diagnostic log.
        work: A callable taking the correlation identifier and returning the
            tool result.

    Returns:
        The tool result.

    Raises:
        DuvoError: Whatever the service raised, with the correlation identifier
            appended to its caller safe message.
    """
    correlation_id = new_correlation_id()
    _LOGGER.info(
        "Tool call started.",
        extra={"fields": {"correlation_id": correlation_id, "tool": tool}},
    )
    try:
        result = work(correlation_id)
    except DuvoError as exc:
        _LOGGER.warning(
            "Tool call failed.",
            extra={
                "fields": {
                    "correlation_id": correlation_id,
                    "tool": tool,
                    "error_code": exc.code,
                    "details": exc.details,
                }
            },
        )
        raise type(exc)(
            f"{exc.safe_message} Correlation id: {correlation_id}.", details=exc.details
        ) from exc
    _LOGGER.info(
        "Tool call finished.",
        extra={"fields": {"correlation_id": correlation_id, "tool": tool, "result": "ok"}},
    )
    return dict(result)
