"""Liveness and readiness must answer different questions."""

from __future__ import annotations

from pathlib import Path

from duvo_fde.clock import FrozenClock
from duvo_fde.config import Settings
from duvo_fde.health import HealthRegistry, ProbeResult, ProbeStatus
from duvo_fde.runtime import build_runtime
from tests.conftest import write_secret


def test_liveness_ignores_dependencies() -> None:
    """Liveness asserts only that the process can serve. Nothing else."""
    health = HealthRegistry()
    health.register("upstream", lambda: ProbeResult("upstream", ProbeStatus.FAILED, "down"))

    assert health.liveness() == {"status": "alive"}


def test_readiness_is_ready_when_every_probe_is_ok() -> None:
    health = HealthRegistry()
    health.register("upstream", lambda: ProbeResult("upstream", ProbeStatus.OK))

    payload, ready = health.readiness()

    assert ready is True
    assert payload["status"] == "ready"


def test_a_degraded_probe_stays_ready() -> None:
    """Degraded means "still serving correctly", so traffic keeps flowing."""
    health = HealthRegistry()
    health.register(
        "secret", lambda: ProbeResult("secret", ProbeStatus.DEGRADED, "last known good")
    )

    payload, ready = health.readiness()

    assert ready is True
    assert payload["status"] == "degraded"
    assert payload["checks"]["secret"]["detail"] == "last known good"


def test_a_failed_probe_is_not_ready() -> None:
    health = HealthRegistry()
    health.register("upstream", lambda: ProbeResult("upstream", ProbeStatus.FAILED, "unreachable"))

    _, ready = health.readiness()

    assert ready is False


def test_a_raising_probe_is_treated_as_failed() -> None:
    health = HealthRegistry()

    def explode() -> ProbeResult:
        raise RuntimeError("boom")

    health.register("upstream", explode)
    payload, ready = health.readiness()

    assert ready is False
    assert payload["checks"]["upstream"]["detail"] == "RuntimeError"


def test_unreadable_key_file_degrades_readiness_but_does_not_fail_it(
    tmp_path: Path, secrets_dir: Path, frozen_clock: FrozenClock
) -> None:
    """The restart-loop trap, asserted end to end through the runtime.

    A container whose key file becomes unreadable while it is still serving on
    the last known good value must not be reported as unready, or an
    orchestrator will cycle a perfectly functional instance.
    """
    path = write_secret(secrets_dir, "upstream_api_key", "initial-value-1234")
    settings = Settings(secrets_dir=secrets_dir, audit_log_path=tmp_path / "audit.log")
    runtime = build_runtime(
        settings,
        clock=frozen_clock,
        configure_logs=False,
        required_secrets=("upstream_api_key",),
    )
    _, ready_before = runtime.health.readiness()
    assert ready_before is True

    path.unlink()

    payload, ready_after = runtime.health.readiness()

    assert ready_after is True
    assert payload["status"] == "degraded"
    assert runtime.health.liveness() == {"status": "alive"}


def test_a_secret_that_was_never_readable_fails_readiness(
    tmp_path: Path, secrets_dir: Path, frozen_clock: FrozenClock
) -> None:
    settings = Settings(secrets_dir=secrets_dir, audit_log_path=tmp_path / "audit.log")
    runtime = build_runtime(
        settings,
        clock=frozen_clock,
        configure_logs=False,
        required_secrets=("never_written",),
    )

    payload, ready = runtime.health.readiness()

    assert ready is False
    assert payload["status"] == "not_ready"
