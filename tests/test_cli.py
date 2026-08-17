"""The container health check depends on this exit code contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from duvo_fde.__main__ import main


def test_config_command_prints_settings_and_succeeds(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    monkeypatch.setenv("DUVO_SECRETS_DIR", str(tmp_path))
    monkeypatch.setenv("DUVO_AUDIT_LOG_PATH", str(tmp_path / "audit.log"))

    exit_code = main(["config"])

    assert exit_code == 0
    assert "upstream_base_url" in json.loads(capsys.readouterr().out)


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
