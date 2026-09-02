"""Speaks raw JSON-RPC to a tool server so the transport is never debugged through a model.

When a tool server misbehaves, attaching an assistant to it and reading the
assistant's interpretation is the slowest possible way to find out why. This
probe performs the handshake directly over standard input and output, prints
exactly what the server said, and exits non-zero if anything is wrong.

The rule during the exercise is: run this first, attach an assistant second.

A handshake alone is a weak check. It passes against a server whose every tool
call would fail, because ``initialize`` and ``tools/list`` touch neither the
credential store nor the upstream. ``--call`` therefore issues real
``tools/call`` requests and reads the results off the wire, which is the only
place the message an assistant actually sees can be observed: the in-process
tests see an exception, whereas a client sees whatever the software development
kit put in the result.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex

# Launching the tool server is the entire purpose of this module.
import subprocess  # nosec B404
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

__all__ = [
    "DEMONSTRATION_CALLS",
    "CallOutcome",
    "ProbeError",
    "ProbeResult",
    "ToolCall",
    "probe",
    "read_server_command",
    "read_server_env",
]

PROTOCOL_VERSION: Final = "2025-06-18"
DEFAULT_TIMEOUT_SECONDS: Final = 15.0
STDERR_EXCERPT_CHARACTERS: Final = 2000


class ProbeError(RuntimeError):
    """The server failed to complete the handshake."""


@dataclass(frozen=True)
class ToolCall:
    """One tool invocation to make, and what has to be true of the result.

    Attributes:
        name: The tool to call.
        arguments: The arguments to send.
        expect_error: Whether the result must be flagged as an error.
        expect_text: Fragments that must appear in the result.
        forbid_text: Fragments that must not appear in the result.
    """

    name: str
    arguments: dict[str, Any]
    expect_error: bool = False
    expect_text: tuple[str, ...] = ()
    forbid_text: tuple[str, ...] = ()


@dataclass(frozen=True)
class CallOutcome:
    """What one tool call actually returned, and how it measured up.

    Attributes:
        call: The call that was made.
        is_error: Whether the server flagged the result as an error.
        text: Everything the server returned, flattened for inspection.
        failures: One entry per expectation that did not hold.
    """

    call: ToolCall
    is_error: bool
    text: str
    failures: tuple[str, ...]

    @property
    def ok(self) -> bool:
        """Report whether every expectation held.

        Returns:
            ``True`` when nothing failed.
        """
        return not self.failures


@dataclass(frozen=True)
class ProbeResult:
    """Everything one probe run observed.

    Attributes:
        tools: The tool descriptors the server advertised.
        outcomes: One entry per call made, empty when no calls were requested.
    """

    tools: list[dict[str, Any]] = field(default_factory=list)
    outcomes: list[CallOutcome] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Report whether every call met its expectations.

        Returns:
            ``True`` when no call failed.
        """
        return all(outcome.ok for outcome in self.outcomes)


# The two calls that matter, and why each one is here.
#
# The first proves the read path end to end: a credential was resolved, the
# upstream answered, and the arithmetic reached the caller. It also asserts the
# data boundary, because the upstream returns basket, loyalty and cashier
# identifiers on every point of sale row and none of them may cross into a
# model's context.
#
# The second proves the failure path, which is the one no in-process test can
# see. A server that masks its error message still passes every unit test and
# still completes a handshake; it fails only here.
DEMONSTRATION_CALLS: Final = (
    ToolCall(
        name="check_stock_position",
        arguments={"store_id": "47", "sku": "8847291"},
        expect_text=("gap_units", "replenishment_threshold_units"),
        forbid_text=("basket_id", "loyalty_id", "cashier_id", "unit_price_eur"),
    ),
    ToolCall(
        name="check_stock_position",
        arguments={"store_id": "999", "sku": "8847291"},
        expect_error=True,
        expect_text=(
            "No StoreLink credential is configured for store 999",
            "Correlation id:",
        ),
    ),
)


def read_server_command(config_path: Path, server_name: str | None = None) -> list[str]:
    """Read a server's launch command from an MCP client configuration file.

    Args:
        config_path: Path to a file containing an ``mcpServers`` object.
        server_name: Which server to read. Defaults to the only one present.

    Returns:
        The command and arguments used to launch the server.

    Raises:
        ProbeError: If the file is missing, malformed, or ambiguous.
    """
    if not config_path.exists():
        msg = f"{config_path} does not exist."
        raise ProbeError(msg)

    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        msg = f"{config_path} is not valid JSON: {exc}"
        raise ProbeError(msg) from exc

    servers = config.get("mcpServers") or {}
    if not servers:
        msg = f"{config_path} declares no servers under 'mcpServers'."
        raise ProbeError(msg)

    if server_name is None:
        if len(servers) > 1:
            msg = f"{config_path} declares several servers; name one of {sorted(servers)}."
            raise ProbeError(msg)
        server_name = next(iter(servers))

    entry = servers.get(server_name)
    if not isinstance(entry, dict) or not entry.get("command"):
        msg = f"Server {server_name!r} has no 'command'."
        raise ProbeError(msg)

    return [str(entry["command"]), *(str(arg) for arg in entry.get("args", []))]


def read_server_env(config_path: Path, server_name: str | None = None) -> dict[str, str]:
    """Read a server's declared environment from a client configuration file.

    A client launches the server with this environment, so a probe that ignores
    it is probing a different process from the one the assistant will get.

    Args:
        config_path: Path to a file containing an ``mcpServers`` object.
        server_name: Which server to read. Defaults to the only one present.

    Returns:
        The declared environment, empty when the file or the server declares
        none. A missing or malformed file is not an error here, because the
        caller may be probing an explicit ``--command`` instead.
    """
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    servers = config.get("mcpServers") or {}
    if server_name is None:
        if len(servers) != 1:
            return {}
        server_name = next(iter(servers))

    entry = servers.get(server_name)
    if not isinstance(entry, dict):
        return {}
    declared = entry.get("env")
    if not isinstance(declared, dict):
        return {}
    return {str(key): str(value) for key, value in declared.items()}


def _result_text(result: dict[str, Any]) -> str:
    """Flatten everything a call result carries into one searchable string.

    Both halves matter. The text blocks are what a model reads, and the
    structured content is what a caller parses, so an assertion about either
    one has to be able to see both.

    Args:
        result: The ``result`` object from a ``tools/call`` response.

    Returns:
        The flattened text.
    """
    parts: list[str] = []
    for block in result.get("content") or []:
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    structured = result.get("structuredContent")
    if structured is not None:
        parts.append(json.dumps(structured, sort_keys=True))
    return "\n".join(parts)


def _judge(call: ToolCall, is_error: bool, text: str) -> CallOutcome:
    """Measure one call result against what the call said had to be true.

    Args:
        call: The call that was made.
        is_error: Whether the server flagged the result as an error.
        text: The flattened result.

    Returns:
        The outcome, carrying one failure entry per expectation that broke.
    """
    failures: list[str] = []
    if is_error != call.expect_error:
        wanted = "an error" if call.expect_error else "a successful result"
        got = "an error" if is_error else "a successful result"
        failures.append(f"expected {wanted}, got {got}")
    for fragment in call.expect_text:
        if fragment not in text:
            failures.append(f"expected to find {fragment!r} in the result")
    for fragment in call.forbid_text:
        if fragment in text:
            failures.append(f"{fragment!r} reached the caller and must not have")
    return CallOutcome(call=call, is_error=is_error, text=text, failures=tuple(failures))


def _send(process: subprocess.Popen[str], message: dict[str, Any]) -> None:
    """Write one JSON-RPC message to the server.

    Args:
        process: The running server process.
        message: The message to send.

    Raises:
        ProbeError: If the server's input stream is unavailable.
    """
    if process.stdin is None:
        msg = "The server process has no standard input."
        raise ProbeError(msg)
    process.stdin.write(json.dumps(message) + "\n")
    process.stdin.flush()


def _receive(process: subprocess.Popen[str], deadline: float) -> dict[str, Any]:
    """Read the next JSON-RPC response, skipping anything that is not one.

    Args:
        process: The running server process.
        deadline: Monotonic time after which to give up.

    Returns:
        The decoded response.

    Raises:
        ProbeError: If the server exits, times out, or never answers.
    """
    if process.stdout is None:
        msg = "The server process has no standard output."
        raise ProbeError(msg)

    while time.monotonic() < deadline:
        line = process.stdout.readline()
        if not line:
            code = process.poll()
            msg = f"The server closed its output stream (exit code {code})."
            raise ProbeError(msg)
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            # Servers that log to standard output rather than standard error
            # are a real and common misconfiguration. Report it rather than
            # letting it look like a protocol failure.
            print(f"    (non-protocol output on stdout: {line[:120]})", file=sys.stderr)
            continue
        if isinstance(message, dict) and "id" in message:
            return message

    msg = "Timed out waiting for the server to respond."
    raise ProbeError(msg)


def probe(
    command: list[str],
    *,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    env: dict[str, str] | None = None,
    calls: Sequence[ToolCall] = (),
) -> ProbeResult:
    """Complete a handshake, list the tools, and optionally call some of them.

    Args:
        command: Command and arguments used to launch the server.
        timeout: Overall wall-clock limit in seconds.
        env: Environment the client declares for this server. The surrounding
            process environment takes precedence, so an explicit override on
            the command line still wins.
        calls: Tool calls to make after the handshake, each carrying its own
            expectations.

    Returns:
        What the run observed.

    Raises:
        ProbeError: If the handshake fails at any point.
    """
    deadline = time.monotonic() + timeout
    environment = {**(env or {}), **os.environ}
    # The command comes from .mcp.json in this repository, or from an explicit
    # --command argument typed by the operator. No shell is interposed.
    process = subprocess.Popen(  # noqa: S603  # nosec B603
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=environment,
    )

    try:
        _send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "duvo-fde-probe", "version": "1"},
                },
            },
        )
        initialised = _receive(process, deadline)
        if "error" in initialised:
            msg = f"initialize failed: {initialised['error']}"
            raise ProbeError(msg)

        _send(process, {"jsonrpc": "2.0", "method": "notifications/initialized"})
        _send(process, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        listed = _receive(process, deadline)
        if "error" in listed:
            msg = f"tools/list failed: {listed['error']}"
            raise ProbeError(msg)

        tools = listed.get("result", {}).get("tools", [])

        outcomes: list[CallOutcome] = []
        for index, call in enumerate(calls, start=3):
            _send(
                process,
                {
                    "jsonrpc": "2.0",
                    "id": index,
                    "method": "tools/call",
                    "params": {"name": call.name, "arguments": call.arguments},
                },
            )
            answered = _receive(process, deadline)
            if "error" in answered:
                # A protocol-level error is not a tool result. Record it as a
                # failure rather than letting it masquerade as one.
                outcomes.append(_judge(call, is_error=True, text=json.dumps(answered["error"])))
                continue
            result = answered.get("result", {})
            outcomes.append(
                _judge(call, is_error=bool(result.get("isError")), text=_result_text(result))
            )

        return ProbeResult(tools=list(tools), outcomes=outcomes)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def main(argv: list[str] | None = None) -> int:
    """Probe the configured tool server.

    Args:
        argv: Argument list. Defaults to ``sys.argv[1:]``.

    Returns:
        ``0`` when the handshake succeeds, enough tools are advertised, and
        every requested call met its expectations.
    """
    parser = argparse.ArgumentParser(
        prog="mcp-probe",
        description="Complete an MCP handshake over stdio and list the advertised tools.",
    )
    parser.add_argument("--config", type=Path, default=Path(".mcp.json"))
    parser.add_argument("--server", default=None, help="Server name within the configuration.")
    parser.add_argument("--command", default=None, help="Launch command, overriding the config.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--min-tools", type=int, default=1)
    parser.add_argument(
        "--call",
        action="store_true",
        help=(
            "Also make real tool calls and assert on the results. Needs the upstream "
            "to be serving, so run scripts/demo_client.sh or the compose stack first."
        ),
    )
    args = parser.parse_args(argv)

    # The declared environment belongs to the server declared in the
    # configuration. An explicit --command is a different server as far as this
    # probe is concerned, so it gets the surrounding environment and nothing
    # borrowed from a configuration it was told to override.
    try:
        if args.command:
            command = shlex.split(args.command)
            declared_env: dict[str, str] = {}
        else:
            command = read_server_command(args.config, args.server)
            declared_env = read_server_env(args.config, args.server)
    except ProbeError as exc:
        print(f"Cannot determine how to launch the server: {exc}", file=sys.stderr)
        return 2

    print(f"Launching: {' '.join(command)}")
    try:
        result = probe(
            command,
            timeout=args.timeout,
            env=declared_env,
            calls=DEMONSTRATION_CALLS if args.call else (),
        )
    except (ProbeError, OSError) as exc:
        print(f"Handshake failed: {exc}", file=sys.stderr)
        return 1

    print(f"Handshake succeeded. {len(result.tools)} tool(s) advertised:")
    for tool in result.tools:
        name = tool.get("name", "<unnamed>")
        description = (tool.get("description") or "").strip().splitlines()
        summary = description[0] if description else ""
        print(f"  - {name}: {summary}")

    if len(result.tools) < args.min_tools:
        print(
            f"Expected at least {args.min_tools} tool(s), found {len(result.tools)}.",
            file=sys.stderr,
        )
        return 1

    if not args.call:
        return 0

    print(f"\nMade {len(result.outcomes)} real tool call(s):")
    for outcome in result.outcomes:
        arguments = ", ".join(f"{key}={value}" for key, value in outcome.call.arguments.items())
        flag = "error" if outcome.is_error else "result"
        verdict = "ok" if outcome.ok else "FAILED"
        print(f"  {verdict:6} {outcome.call.name}({arguments}) -> {flag}")
        # The whole point of this mode is that a human reads what the caller
        # was given, so print it rather than summarising it.
        for line in outcome.text.splitlines():
            print(f"           {line}")
        for failure in outcome.failures:
            print(f"           ! {failure}", file=sys.stderr)

    if not result.ok:
        print("\nA tool call did not behave as required.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
