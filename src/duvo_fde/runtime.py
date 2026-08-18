"""Composition root: builds the application's collaborators once, in one place.

Keeping assembly here means the domain code written against the brief takes its
dependencies as arguments and stays trivially testable, and it means there is a
single obvious place to look when asking "what does this process actually talk
to?".
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from duvo_fde.audit import AuditLog
from duvo_fde.clock import Clock, SystemClock
from duvo_fde.config import Settings, load_settings
from duvo_fde.health import HealthRegistry, ProbeResult, ProbeStatus
from duvo_fde.idempotency import IdempotencyStore
from duvo_fde.log import configure_logging
from duvo_fde.secrets_provider import SecretsProvider

__all__ = ["Runtime", "build_runtime"]


@dataclass(frozen=True)
class Runtime:
    """Every collaborator the service needs, assembled and ready.

    Attributes:
        settings: Validated configuration.
        secrets: Secret provider that picks up rotations without a restart.
        audit: Append-only audit trail.
        health: Registry backing the liveness and readiness endpoints.
        idempotency: Store preventing duplicate writes.
        clock: Time source, injectable for tests.
    """

    settings: Settings
    secrets: SecretsProvider
    audit: AuditLog
    health: HealthRegistry
    idempotency: IdempotencyStore
    clock: Clock


def build_runtime(
    settings: Settings | None = None,
    *,
    clock: Clock | None = None,
    configure_logs: bool = True,
    required_secrets: tuple[str, ...] = (),
) -> Runtime:
    """Assemble the runtime from configuration.

    Args:
        settings: Configuration to use. Loaded from the environment when omitted.
        clock: Time source. Defaults to the system clock.
        configure_logs: Whether to install the logging configuration. Tests that
            capture logs themselves pass ``False``.
        required_secrets: Secret names to expose as readiness probes.

    Returns:
        The assembled runtime.
    """
    settings = settings or load_settings()
    clock = clock or SystemClock()

    if configure_logs:
        configure_logging(level=settings.log_level, fmt=settings.log_format)

    secrets = SecretsProvider(settings.secrets_dir, clock=clock)
    audit = AuditLog(settings.audit_log_path, clock=clock)
    health = HealthRegistry()
    idempotency = IdempotencyStore(clock=clock)

    for name in required_secrets:
        health.register(name=f"secret:{name}", probe=_secret_probe(secrets, name))

    return Runtime(
        settings=settings,
        secrets=secrets,
        audit=audit,
        health=health,
        idempotency=idempotency,
        clock=clock,
    )


def _secret_probe(secrets: SecretsProvider, name: str) -> Callable[[], ProbeResult]:
    """Build a readiness probe for one secret.

    A secret whose file is currently unreadable but for which a last known good
    value is held reports *degraded*, not *failed*. Failing here would take a
    correctly-serving instance out of rotation and, on a liveness probe, restart
    it — turning a transient read error into an outage.

    Args:
        secrets: The provider to query.
        name: Secret name.

    Returns:
        A callable returning the probe result.
    """

    def probe() -> ProbeResult:
        state = secrets.state(name)
        probe_name = f"secret:{name}"
        if not state.available:
            return ProbeResult(probe_name, ProbeStatus.FAILED, "no usable value held")
        if state.degraded:
            return ProbeResult(probe_name, ProbeStatus.DEGRADED, "serving last known good value")
        return ProbeResult(probe_name, ProbeStatus.OK, f"rotations={state.rotations}")

    return probe
