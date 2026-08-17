"""The audit trail must actually be written, not merely declared."""

from __future__ import annotations

from pathlib import Path

from duvo_fde.audit import AuditLog
from duvo_fde.clock import FrozenClock
from duvo_fde.log import REDACTED, secret_registry
from duvo_fde.runtime import Runtime


def test_a_record_reaches_the_configured_file(tmp_path: Path, frozen_clock: FrozenClock) -> None:
    """Asserts on the file contents, not on the call having been made."""
    path = tmp_path / "nested" / "audit.log"
    audit = AuditLog(path, clock=frozen_clock)

    audit.record(actor="agent", action="place_order", target="store-7", outcome="created")

    assert path.exists()
    records = audit.read_all()
    assert len(records) == 1
    assert records[0]["action"] == "place_order"
    assert records[0]["target"] == "store-7"
    assert records[0]["outcome"] == "created"


def test_records_append_rather_than_overwrite(tmp_path: Path, frozen_clock: FrozenClock) -> None:
    audit = AuditLog(tmp_path / "audit.log", clock=frozen_clock)

    audit.record(actor="agent", action="a", target="t", outcome="created")
    audit.record(actor="agent", action="b", target="t", outcome="duplicate")

    assert [r["action"] for r in audit.read_all()] == ["a", "b"]


def test_the_timestamp_comes_from_the_injected_clock(
    tmp_path: Path, frozen_clock: FrozenClock
) -> None:
    audit = AuditLog(tmp_path / "audit.log", clock=frozen_clock)

    record = audit.record(actor="agent", action="a", target="t", outcome="created")

    assert record.timestamp == frozen_clock.now().isoformat()


def test_secrets_are_redacted_from_audit_context(tmp_path: Path, frozen_clock: FrozenClock) -> None:
    secret_registry.register("super-secret-value-123")
    audit = AuditLog(tmp_path / "audit.log", clock=frozen_clock)

    audit.record(
        actor="agent",
        action="call",
        target="upstream",
        outcome="created",
        context={"header": "super-secret-value-123"},
    )

    written = (tmp_path / "audit.log").read_text(encoding="utf-8")
    assert "super-secret-value-123" not in written
    assert REDACTED in written


def test_file_output_can_be_disabled(frozen_clock: FrozenClock) -> None:
    audit = AuditLog(None, clock=frozen_clock)

    record = audit.record(actor="agent", action="a", target="t", outcome="created")

    assert record.action == "a"
    assert audit.read_all() == []


def test_the_runtime_wires_the_audit_log_to_a_real_path(runtime: Runtime) -> None:
    """Guards against an audit log that is configured but never connected."""
    runtime.audit.record(actor="agent", action="a", target="t", outcome="created")

    assert runtime.audit.path is not None
    assert runtime.audit.path.exists()
    assert len(runtime.audit.read_all()) == 1
