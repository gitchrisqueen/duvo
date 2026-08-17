"""Speaks raw JSON-RPC to a tool server so the transport is never debugged through a model.

When a tool server misbehaves, attaching an assistant to it and reading the
assistant's interpretation is the slowest possible way to find out why. This
probe performs the handshake directly over standard input and output, prints
exactly what the server said, and exits non-zero if anything is wrong.

The rule during the exercise is: run this first, attach an assistant second.
"""

from __future__ import annotations

import argparse
import json
import shlex

# Launching the tool server is the entire purpose of this module.
import subprocess  # nosec B404
import sys
import time
from pathlib import Path
from typing import Any, Final

__all__ = ["ProbeError", "probe", "read_server_command"]

PROTOCOL_VERSION: Final = "2025-06-18"
DEFAULT_TIMEOUT_SECONDS: Final = 15.0


class ProbeError(RuntimeError):
    """The server failed to complete the handshake."""


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


def probe(command: list[str], *, timeout: float = DEFAULT_TIMEOUT_SECONDS) -> list[dict[str, Any]]:
    """Complete an initialise handshake and list the server's tools.

    Args:
        command: Command and arguments used to launch the server.
        timeout: Overall wall-clock limit in seconds.

    Returns:
        The tool descriptors the server advertised.

    Raises:
        ProbeError: If the handshake fails at any point.
    """
    deadline = time.monotonic() + timeout
    # The command comes from .mcp.json in this repository, or from an explicit
    # --command argument typed by the operator. No shell is interposed.
    process = subprocess.Popen(  # noqa: S603  # nosec B603
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
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
        return list(tools)
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
        ``0`` when the handshake succeeds and at least one tool is advertised.
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
    args = parser.parse_args(argv)

    try:
        command = (
            shlex.split(args.command)
            if args.command
            else read_server_command(args.config, args.server)
        )
    except ProbeError as exc:
        print(f"Cannot determine how to launch the server: {exc}", file=sys.stderr)
        return 2

    print(f"Launching: {' '.join(command)}")
    try:
        tools = probe(command, timeout=args.timeout)
    except (ProbeError, OSError) as exc:
        print(f"Handshake failed: {exc}", file=sys.stderr)
        return 1

    print(f"Handshake succeeded. {len(tools)} tool(s) advertised:")
    for tool in tools:
        name = tool.get("name", "<unnamed>")
        description = (tool.get("description") or "").strip().splitlines()
        summary = description[0] if description else ""
        print(f"  - {name}: {summary}")

    if len(tools) < args.min_tools:
        print(
            f"Expected at least {args.min_tools} tool(s), found {len(tools)}.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
