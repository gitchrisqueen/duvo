"""Append-only audit trail for actions taken on the customer's behalf.

An audit log that is declared but never written is worse than no audit log: it
is a claim in a document that a reviewer will eventually test. Every write path
in this service records here, and ``tests/test_audit.py`` asserts that records
actually reach the configured destination rather than merely that the call
compiles.

Records are JSON lines so they can be shipped, grepped, and replayed. They pass
through the same redaction as ordinary logs.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from duvo_fde.clock import Clock, SystemClock
from duvo_fde.log import secret_registry

__all__ = ["AuditLog", "AuditRecord"]

_LOGGER = logging.getLogger("duvo_fde.audit")


@dataclass(frozen=True)
class AuditRecord:
    """One auditable action.

    Attributes:
        timestamp: ISO-8601 timestamp in UTC.
        actor: Who or what initiated the action, for example ``"agent"``.
        action: What was attempted, for example ``"place_order"``.
        target: What it was attempted against, for example a location id.
        outcome: Result of the attempt, for example ``"created"``.
        context: Additional structured detail. Redacted before emission.
    """

    timestamp: str
    actor: str
    action: str
    target: str
    outcome: str
    context: dict[str, Any]


class AuditLog:
    """Writes audit records to a file and to the application logger.

    Example:
        ```python
        audit = AuditLog(Path("audit.log"))
        audit.record(actor="agent", action="place_order", target="store-7", outcome="created")
        ```
    """

    def __init__(self, path: Path | None = None, *, clock: Clock | None = None) -> None:
        """Initialise the audit log.

        Args:
            path: File to append records to. When ``None``, records are emitted
                through the logger only.
            clock: Clock used for record timestamps. Defaults to the system clock.
        """
        self._path = path
        self._clock = clock or SystemClock()
        self._lock = threading.Lock()
        if self._path is not None:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path | None:
        """Return the file records are appended to.

        Returns:
            The configured path, or ``None`` when file output is disabled.
        """
        return self._path

    def record(
        self,
        *,
        actor: str,
        action: str,
        target: str,
        outcome: str,
        context: dict[str, Any] | None = None,
    ) -> AuditRecord:
        """Append one record to the audit trail.

        Args:
            actor: Who or what initiated the action.
            action: What was attempted.
            target: What it was attempted against.
            outcome: The result of the attempt.
            context: Additional structured detail.

        Returns:
            The record that was written, so callers can assert on it.
        """
        record = AuditRecord(
            timestamp=self._clock.now().isoformat(),
            actor=actor,
            action=action,
            target=target,
            outcome=outcome,
            context=context or {},
        )
        line = secret_registry.scrub(json.dumps(asdict(record), default=str))

        if self._path is not None:
            with self._lock, self._path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

        _LOGGER.info("audit", extra={"fields": {"audit": json.loads(line)}})
        return record

    def read_all(self) -> list[dict[str, Any]]:
        """Read every record written so far.

        Intended for tests and for the smoke test's evidence output.

        Returns:
            The records in write order. Empty when file output is disabled or
            nothing has been written yet.
        """
        if self._path is None or not self._path.exists():
            return []
        with self._path.open(encoding="utf-8") as handle:
            return [json.loads(line) for line in handle if line.strip()]
