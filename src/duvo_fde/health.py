"""Liveness and readiness as two separate questions.

Collapsing these into a single health endpoint is a common and expensive
mistake. They answer different questions and have different consequences:

* **Liveness** asks "is this process broken beyond recovery?" A failure here
  tells an orchestrator to kill and restart the container.
* **Readiness** asks "should traffic be routed here right now?" A failure here
  removes the instance from rotation but leaves it running.

The distinction matters most in the degraded case. If a credential file becomes
temporarily unreadable while the service is still serving correctly on the last
known good value, reporting that as unhealthy would trigger a restart loop and
convert a transient blip into an outage. That condition is *degraded*: it is
reported, it is visible, and it does not take the instance out of service.

Only a probe that reports :data:`ProbeStatus.FAILED` makes the service unready.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

__all__ = ["HealthRegistry", "ProbeResult", "ProbeStatus"]


class ProbeStatus(StrEnum):
    """Outcome of a single readiness probe."""

    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"


@dataclass(frozen=True)
class ProbeResult:
    """Result of one readiness probe.

    Attributes:
        name: Probe name, used as the key in the readiness payload.
        status: Whether the dependency is healthy, degraded, or failed.
        detail: Short human-readable explanation. Must not contain secrets.
    """

    name: str
    status: ProbeStatus
    detail: str = ""


class HealthRegistry:
    """Holds readiness probes and renders the two health payloads.

    Example:
        ```python
        health = HealthRegistry()
        health.register("upstream", lambda: ProbeResult("upstream", ProbeStatus.OK))
        payload, ready = health.readiness()
        ```
    """

    def __init__(self) -> None:
        """Initialise an empty registry."""
        self._probes: dict[str, Callable[[], ProbeResult]] = {}

    def register(self, name: str, probe: Callable[[], ProbeResult]) -> None:
        """Add a readiness probe.

        Args:
            name: Unique probe name.
            probe: Callable returning a :class:`ProbeResult`. It must not raise;
                if it does, the probe is reported as failed.
        """
        self._probes[name] = probe

    def liveness(self) -> dict[str, Any]:
        """Report process liveness.

        This deliberately checks nothing external. Reaching this code proves the
        process is running and able to serve a request, which is the only thing
        liveness should assert. Dependency state belongs in readiness.

        Returns:
            A payload indicating the process is alive.
        """
        return {"status": "alive"}

    def readiness(self) -> tuple[dict[str, Any], bool]:
        """Run every probe and report whether traffic should be routed here.

        Returns:
            A tuple of the readiness payload and a boolean that is ``True`` when
            the service is ready. Degraded probes are reported in the payload
            but do not make the service unready.
        """
        results: list[ProbeResult] = []
        for name, probe in self._probes.items():
            try:
                results.append(probe())
            except Exception as exc:  # noqa: BLE001 - a raising probe is a failed probe.
                results.append(
                    ProbeResult(name=name, status=ProbeStatus.FAILED, detail=type(exc).__name__)
                )

        ready = all(result.status is not ProbeStatus.FAILED for result in results)
        degraded = any(result.status is ProbeStatus.DEGRADED for result in results)

        if not ready:
            status = "not_ready"
        elif degraded:
            status = "degraded"
        else:
            status = "ready"

        payload: dict[str, Any] = {
            "status": status,
            "ready": ready,
            "checks": {
                result.name: {"status": str(result.status), "detail": result.detail}
                for result in results
            },
        }
        return payload, ready
