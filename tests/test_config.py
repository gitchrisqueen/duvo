"""Configuration is validated once, loudly, at startup."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from duvo_fde.config import Settings


def test_defaults_are_usable() -> None:
    settings = Settings()

    assert settings.log_format == "json"
    assert settings.upstream_timeout_seconds > 0


def test_an_unsupported_log_format_is_rejected() -> None:
    with pytest.raises(ValidationError, match="log_format"):
        Settings(log_format="xml")


def test_a_non_positive_timeout_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(upstream_timeout_seconds=0)


def test_an_empty_audit_path_disables_file_output() -> None:
    settings = Settings.model_validate({"audit_log_path": ""})

    assert settings.audit_log_path is None


def test_settings_are_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("DUVO_UPSTREAM_BASE_URL", "http://example.test")
    monkeypatch.setenv("DUVO_SECRETS_DIR", str(tmp_path))

    settings = Settings()

    assert settings.upstream_base_url == "http://example.test"
    assert settings.secrets_dir == tmp_path


def test_no_secret_values_are_part_of_configuration() -> None:
    """Secrets are read through the provider so rotation works without a restart."""
    fields = set(Settings.model_fields)

    assert not {name for name in fields if name.endswith(("_key", "_token", "_password"))}
