"""Structured logging that cannot emit a known secret.

Two mechanisms work together:

1. :class:`SecretRegistry` holds the live secret *values*. Any log record whose
   rendered text contains one of them has it replaced with ``***REDACTED***``.
   This catches the case that pattern matching always misses: a credential
   interpolated into an error string by a library we do not control.
2. Field-name redaction removes values under keys that conventionally hold
   credentials, and a small set of patterns catches bearer tokens and
   API-key-shaped strings that were never registered.

The registry is populated by :mod:`duvo_fde.secrets_provider` as secrets are
read, including after a rotation, so a newly rotated key is protected the moment
it is loaded.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from typing import Any, Final

__all__ = [
    "REDACTED",
    "JsonFormatter",
    "RedactionFilter",
    "SecretRegistry",
    "configure_logging",
    "secret_registry",
]

REDACTED: Final = "***REDACTED***"

#: Keys whose values are removed regardless of content.
_SENSITIVE_KEYS: Final = frozenset(
    {
        "api_key",
        "apikey",
        "authorization",
        "credential",
        "password",
        "private_key",
        "secret",
        "token",
        "x-api-key",
    }
)

#: Patterns for credential-shaped strings that were never registered.
_SENSITIVE_PATTERNS: Final = (
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9._\-]{12,}"),
    re.compile(r"(?i)\b(?:api[_-]?key|token|secret)\s*[=:]\s*['\"]?[A-Za-z0-9._\-]{8,}"),
)

#: Minimum length for a registered secret to be redacted by value. Very short
#: values would match ordinary words and turn logs into noise.
_MIN_REDACTABLE_LENGTH: Final = 6


class SecretRegistry:
    """Tracks live secret values so they can be scrubbed from log output.

    The registry never persists values and is not exposed outside the process.
    Registration is idempotent.
    """

    def __init__(self) -> None:
        """Initialise an empty registry."""
        self._values: set[str] = set()

    def register(self, value: str | None) -> None:
        """Record a secret value so it is redacted from future log output.

        Values shorter than six characters are ignored, because redacting them
        would corrupt unrelated log text without meaningfully protecting
        anything.

        Args:
            value: The secret value to protect. ``None`` and blanks are ignored.
        """
        if value and len(value.strip()) >= _MIN_REDACTABLE_LENGTH:
            self._values.add(value.strip())

    def clear(self) -> None:
        """Forget every registered value. Used by tests."""
        self._values.clear()

    def scrub(self, text: str) -> str:
        """Replace every registered secret and credential pattern in ``text``.

        Args:
            text: Arbitrary text that may embed a secret.

        Returns:
            The text with every known secret replaced by :data:`REDACTED`.
        """
        for value in self._values:
            if value in text:
                text = text.replace(value, REDACTED)
        for pattern in _SENSITIVE_PATTERNS:
            text = pattern.sub(REDACTED, text)
        return text


#: Process-wide registry. Populated by the secrets provider.
secret_registry: Final = SecretRegistry()


def _redact_structure(value: Any) -> Any:
    """Recursively redact sensitive keys and scrub string values.

    Args:
        value: Any JSON-compatible structure.

    Returns:
        The structure with sensitive fields replaced.
    """
    if isinstance(value, dict):
        return {
            key: (REDACTED if str(key).lower() in _SENSITIVE_KEYS else _redact_structure(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_structure(item) for item in value]
    if isinstance(value, str):
        return secret_registry.scrub(value)
    return value


class RedactionFilter(logging.Filter):
    """Scrubs secrets from the message and structured fields of every record."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Redact the record in place.

        Args:
            record: The record about to be emitted.

        Returns:
            Always ``True``. This filter modifies rather than drops records.
        """
        if isinstance(record.msg, str):
            record.msg = secret_registry.scrub(record.msg)
        if record.args:
            record.args = tuple(_redact_structure(arg) for arg in record.args)
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            record.fields = _redact_structure(fields)
        if record.exc_text:
            record.exc_text = secret_registry.scrub(record.exc_text)
        return True


class JsonFormatter(logging.Formatter):
    """Renders records as single-line JSON for log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        """Render the record.

        Args:
            record: The record to render.

        Returns:
            A single-line JSON document.
        """
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if isinstance(fields, dict):
            payload.update(fields)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        # The formatter is the last line of defence: scrub the rendered document
        # in case a field reached the record without passing through the filter.
        return secret_registry.scrub(json.dumps(payload, default=str))


def configure_logging(*, level: str = "INFO", fmt: str = "json") -> None:
    """Install the structured handler and redaction filter on the root logger.

    Calling this more than once replaces the previous configuration rather than
    stacking handlers, so it is safe to call from both the entry point and tests.

    Args:
        level: Logging level name, for example ``"INFO"`` or ``"DEBUG"``.
        fmt: ``"json"`` for aggregation, ``"console"`` for local development.
    """
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.addFilter(RedactionFilter())
    if fmt == "console":
        handler.setFormatter(logging.Formatter("%(levelname)-8s %(name)s: %(message)s"))
    else:
        handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level.upper())
