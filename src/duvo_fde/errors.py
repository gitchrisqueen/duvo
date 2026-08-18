"""Typed errors with messages that are safe to return to a caller.

Every error carries a stable ``code`` for programmatic handling and a
``safe_message`` that is written for an external audience. Internal detail,
upstream response bodies, and anything that might embed a credential stay in
``details``, which is only ever emitted through the redacting logger.

Example:
    ```python
    raise InvalidRequestError(
        safe_message="Quantity must be greater than zero.",
        details={"received": -5},
    )
    ```
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "ConfigurationError",
    "DuplicateRequestError",
    "DuvoError",
    "InvalidRequestError",
    "SecretUnavailableError",
    "UnknownEntityError",
    "UpstreamError",
]


class DuvoError(Exception):
    """Base class for every error this service raises deliberately.

    Attributes:
        code: Stable machine-readable identifier, used by callers and tests.
        safe_message: Human-readable message with no secrets or internals.
        details: Structured context for logging. Never returned to a caller.
    """

    code: str = "internal_error"

    def __init__(
        self,
        safe_message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialise the error.

        Args:
            safe_message: Message suitable for returning to an external caller.
            details: Structured context for logs. Redacted before emission.
        """
        super().__init__(safe_message)
        self.safe_message = safe_message
        self.details: dict[str, Any] = details or {}

    def as_payload(self) -> dict[str, Any]:
        """Return the caller-facing representation of this error.

        Returns:
            A dictionary containing only the code and the safe message.
        """
        return {"error": {"code": self.code, "message": self.safe_message}}


class InvalidRequestError(DuvoError):
    """The request failed validation at the service boundary."""

    code = "invalid_request"


class UnknownEntityError(DuvoError):
    """The request referenced an identifier this service does not recognise."""

    code = "unknown_entity"


class DuplicateRequestError(DuvoError):
    """A write was replayed and was deliberately not performed a second time.

    This is not always an error condition. Callers that supply an idempotency
    key normally receive the original result instead of this exception; it is
    raised only where a replay must be surfaced explicitly.
    """

    code = "duplicate_request"


class UpstreamError(DuvoError):
    """The upstream system failed, timed out, or returned something unusable."""

    code = "upstream_error"


class ConfigurationError(DuvoError):
    """The service is misconfigured and cannot operate correctly."""

    code = "configuration_error"


class SecretUnavailableError(DuvoError):
    """A required secret has never been readable since the process started.

    This is distinct from a secret that is *currently* unreadable but for which
    a last known good value is still held. That case is a degraded condition,
    not a failure, and is reported through readiness rather than raised here.
    """

    code = "secret_unavailable"
