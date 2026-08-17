"""Reading the launch command must fail loudly rather than guess.

The handshake itself is exercised against a real subprocess in
``scripts/mcp_check.sh``. What is worth unit testing is the configuration
reading, because every failure mode here happens at the worst moment: when the
server will not start and the clock is running.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.mcp_probe import ProbeError, read_server_command


def _write(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_reads_the_only_declared_server(tmp_path: Path) -> None:
    config = _write(
        tmp_path / ".mcp.json",
        {"mcpServers": {"duvo-fde": {"command": "python", "args": ["-m", "duvo_fde"]}}},
    )

    assert read_server_command(config) == ["python", "-m", "duvo_fde"]


def test_a_named_server_can_be_selected(tmp_path: Path) -> None:
    config = _write(
        tmp_path / ".mcp.json",
        {"mcpServers": {"a": {"command": "one"}, "b": {"command": "two"}}},
    )

    assert read_server_command(config, "b") == ["two"]


def test_an_ambiguous_configuration_is_rejected(tmp_path: Path) -> None:
    """Guessing which server was meant is how the wrong thing gets probed."""
    config = _write(
        tmp_path / ".mcp.json",
        {"mcpServers": {"a": {"command": "one"}, "b": {"command": "two"}}},
    )

    with pytest.raises(ProbeError, match="several servers"):
        read_server_command(config)


def test_a_missing_file_is_reported_clearly(tmp_path: Path) -> None:
    with pytest.raises(ProbeError, match="does not exist"):
        read_server_command(tmp_path / "absent.json")


def test_malformed_json_is_reported_as_malformed(tmp_path: Path) -> None:
    config = tmp_path / ".mcp.json"
    config.write_text("{not json", encoding="utf-8")

    with pytest.raises(ProbeError, match="not valid JSON"):
        read_server_command(config)


def test_a_configuration_with_no_servers_is_rejected(tmp_path: Path) -> None:
    config = _write(tmp_path / ".mcp.json", {"mcpServers": {}})

    with pytest.raises(ProbeError, match="no servers"):
        read_server_command(config)


def test_a_server_without_a_command_is_rejected(tmp_path: Path) -> None:
    config = _write(tmp_path / ".mcp.json", {"mcpServers": {"duvo-fde": {"args": ["-m"]}}})

    with pytest.raises(ProbeError, match="no 'command'"):
        read_server_command(config)


def test_the_repository_configuration_still_holds_its_placeholder() -> None:
    """The placeholder is replaced during the exercise.

    If this ever fails, either the transport has been wired, in which case
    update this test, or the file has been corrupted.
    """
    config = Path(__file__).resolve().parents[1] / ".mcp.json"

    assert read_server_command(config) == ["REPLACE_ME"]
