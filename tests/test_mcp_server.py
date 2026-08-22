"""The agent facing tool surface.

The strongest guarantee this server makes is structural rather than behavioural:
there is no vocabulary in which a caller could express an order that Korral's
policy does not permit, because no tool accepts a quantity or a threshold. These
tests assert that against the schemas the server actually advertises, so the
guarantee cannot quietly regress by someone adding a parameter.

The server's methods are asynchronous. They are driven with ``asyncio.run``
rather than a plugin, which keeps the suite free of an event loop fixture and
still finishes in milliseconds.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from duvo_fde.mcp_server import SERVER_NAME, build_server, new_correlation_id
from duvo_fde.runtime import Runtime

from .conftest import write_secret

EXPECTED_TOOLS = {
    "check_stock_position",
    "raise_replenishment_order",
    "get_replenishment_order_status",
}

FORBIDDEN_PARAMETERS = {
    "quantity",
    "quantity_units",
    "order_quantity_units",
    "threshold",
    "threshold_units",
    "gap",
    "gap_units",
    "force",
    "override",
}


def _tools(runtime: Runtime) -> list[Any]:
    """List the tools the server advertises."""
    return asyncio.run(build_server(runtime).list_tools())


def _call(runtime: Runtime, name: str, arguments: dict[str, Any]) -> Any:
    """Invoke one tool through the server, as a client would."""
    return asyncio.run(build_server(runtime).call_tool(name, arguments))


def test_the_server_advertises_exactly_the_three_intended_tools(runtime: Runtime) -> None:
    assert {tool.name for tool in _tools(runtime)} == EXPECTED_TOOLS


def test_the_server_is_named_for_the_system_it_fronts(runtime: Runtime) -> None:
    assert build_server(runtime).name == SERVER_NAME


def test_every_tool_carries_a_description_a_model_can_act_on(runtime: Runtime) -> None:
    for tool in _tools(runtime):
        assert tool.description
        assert len(tool.description) > 100


def test_no_tool_accepts_a_quantity_a_threshold_or_an_override(runtime: Runtime) -> None:
    # Rule three, enforced structurally. A fixed business rule is a constant,
    # and a caller must have no way to express a different one.
    for tool in _tools(runtime):
        properties = set(tool.input_schema.get("properties", {}))
        assert properties & FORBIDDEN_PARAMETERS == set(), f"{tool.name} exposes {properties}"


def test_the_tools_take_identifiers_only(runtime: Runtime) -> None:
    # Identifiers select data. They never select outcomes.
    schemas = {tool.name: set(tool.input_schema.get("properties", {})) for tool in _tools(runtime)}

    assert schemas["check_stock_position"] == {"store_id", "sku"}
    assert schemas["raise_replenishment_order"] == {"store_id", "sku"}
    assert schemas["get_replenishment_order_status"] == {"store_id", "order_id"}


def test_both_identifiers_are_required_on_every_tool(runtime: Runtime) -> None:
    for tool in _tools(runtime):
        required = set(tool.input_schema.get("required", []))
        assert required == set(tool.input_schema.get("properties", {}))


def test_the_reads_are_annotated_read_only_and_the_write_is_not(runtime: Runtime) -> None:
    annotations = {tool.name: tool.annotations for tool in _tools(runtime)}

    assert annotations["check_stock_position"].read_only_hint is True
    assert annotations["get_replenishment_order_status"].read_only_hint is True
    assert annotations["raise_replenishment_order"].read_only_hint is False
    assert annotations["raise_replenishment_order"].destructive_hint is False


def test_the_instructions_tell_a_model_not_to_apply_the_rule_itself(runtime: Runtime) -> None:
    instructions = build_server(runtime).instructions or ""

    assert "applied by this server, not by you" in instructions
    assert "correlation identifier" in instructions


def test_the_instructions_state_the_data_boundary(runtime: Runtime) -> None:
    instructions = build_server(runtime).instructions or ""

    assert "loyalty identifiers" in instructions
    assert "never returned by any tool" in instructions


def test_a_correlation_identifier_is_short_hexadecimal_and_unique() -> None:
    minted = {new_correlation_id() for _ in range(200)}

    assert len(minted) == 200
    for value in minted:
        assert len(value) == 12
        assert all(character in "0123456789abcdef" for character in value)


def test_a_failing_tool_call_carries_its_correlation_identifier(runtime: Runtime) -> None:
    # The case where correlation matters most is the failure, so the identifier
    # is appended to the message the caller actually sees.
    with pytest.raises(ToolError) as caught:
        _call(runtime, "check_stock_position", {"store_id": "999", "sku": "8847291"})

    assert "Correlation id:" in str(caught.value)
    assert "No StoreLink credential is configured for store 999" in str(caught.value)


def test_a_failing_tool_call_never_leaks_a_credential(runtime: Runtime, secrets_dir: Path) -> None:
    write_secret(secrets_dir, "korral_store_key_47", "super-secret-value")

    with pytest.raises(ToolError) as caught:
        _call(runtime, "check_stock_position", {"store_id": "999", "sku": "8847291"})

    assert "super-secret-value" not in str(caught.value)


def test_a_malformed_identifier_is_refused_before_anything_is_read(runtime: Runtime) -> None:
    with pytest.raises(ToolError) as caught:
        _call(runtime, "check_stock_position", {"store_id": "../etc", "sku": "8847291"})

    assert "one to ten digits" in str(caught.value)


def test_an_unknown_tool_name_is_refused(runtime: Runtime) -> None:
    with pytest.raises(ToolError):
        _call(runtime, "delete_everything", {"store_id": "47"})
