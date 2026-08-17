"""The container health check depends on this exit code contract."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from duvo_fde.__main__ import main, serve
from duvo_fde.runtime import Runtime


def test_config_command_prints_settings_and_succeeds(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("DUVO_SECRETS_DIR", str(tmp_path))
    monkeypatch.setenv("DUVO_AUDIT_LOG_PATH", str(tmp_path / "audit.log"))

    exit_code = main(["config"])

    assert exit_code == 0
    assert "upstream_base_url" in json.loads(capsys.readouterr().out)


def test_serve_stays_alive_until_it_is_told_to_stop(runtime: Runtime) -> None:
    """The container stack depends on this.

    An entry point that prints and exits makes `docker compose up --wait` fail,
    because the container it is waiting for is already gone. That is how this
    was found: the images built correctly and the stack still would not start.
    """
    stop = threading.Event()
    stop.set()

    assert serve(runtime, stop=stop) == 0


def test_serve_blocks_while_the_stop_event_is_unset(runtime: Runtime) -> None:
    stop = threading.Event()
    finished = threading.Event()

    def run() -> None:
        serve(runtime, stop=stop)
        finished.set()

    worker = threading.Thread(target=run, daemon=True)
    worker.start()

    assert finished.wait(timeout=0.2) is False, "serve returned without being asked to stop"

    stop.set()
    assert finished.wait(timeout=5) is True
    worker.join(timeout=5)


def test_health_command_reports_both_payloads(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("DUVO_SECRETS_DIR", str(tmp_path))
    monkeypatch.setenv("DUVO_AUDIT_LOG_PATH", str(tmp_path / "audit.log"))

    exit_code = main(["health"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["liveness"] == {"status": "alive"}
    assert payload["readiness"]["ready"] is True
