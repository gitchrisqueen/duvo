"""Typed configuration loaded from the environment.

Configuration is validated once, at startup, so that a misconfigured deployment
fails immediately and visibly rather than at the first request. Secrets are
deliberately absent from this model: they are read through
:class:`duvo_fde.secrets_provider.SecretsProvider` so that rotation works
without a restart. Only the *location* of the secrets is configuration.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings", "load_settings"]


class Settings(BaseSettings):
    """Runtime configuration for the service.

    Attributes:
        secrets_dir: Directory holding one file per secret. A directory, not a
            file, so that rotation is observable inside a container.
        upstream_base_url: Base URL of the system this server integrates with.
        upstream_timeout_seconds: Per-request timeout for upstream calls.
        log_level: Logging level name.
        log_format: ``"json"`` for aggregation or ``"console"`` for development.
        audit_log_path: Where the audit trail is appended. Empty disables file
            output and routes records through the logger only.
    """

    model_config = SettingsConfigDict(
        env_prefix="DUVO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    secrets_dir: Path = Field(default=Path("./secrets"))
    upstream_base_url: str = Field(default="http://localhost:8080")
    upstream_timeout_seconds: float = Field(default=10.0, gt=0)
    log_level: str = Field(default="INFO")
    log_format: str = Field(default="json")
    audit_log_path: Path | None = Field(default=Path("./audit.log"))

    @field_validator("log_format")
    @classmethod
    def _validate_log_format(cls, value: str) -> str:
        """Reject log formats this service does not implement.

        Args:
            value: The configured format.

        Returns:
            The validated format.

        Raises:
            ValueError: If the format is not supported.
        """
        allowed = {"json", "console"}
        if value not in allowed:
            msg = f"log_format must be one of {sorted(allowed)}, got {value!r}."
            raise ValueError(msg)
        return value

    @field_validator("audit_log_path", mode="before")
    @classmethod
    def _empty_disables_audit_file(cls, value: object) -> object:
        """Treat an empty string as "no audit file".

        Args:
            value: The raw configured value.

        Returns:
            ``None`` when the value is blank, otherwise the value unchanged.
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value


def load_settings() -> Settings:
    """Load and validate settings from the environment.

    Returns:
        The validated settings object.
    """
    return Settings()
