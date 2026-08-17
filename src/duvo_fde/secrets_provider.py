"""Secret loading that survives rotation without a process restart.

Why this module is shaped the way it is
---------------------------------------

The obvious implementation — open the secret file once at startup, or watch it
with an ``mtime`` check on a cached file handle — fails silently in a container.
When an operator or a secret manager rotates a credential, the new value almost
never lands in the same inode: the writer creates a new file and renames it over
the old one, and orchestrators such as Kubernetes swap a symlinked directory.
A process holding the old handle, or comparing ``mtime`` on a stale ``os.stat``
result, keeps serving the old credential forever and reports itself perfectly
healthy while doing so.

Two rules follow, and both are load-bearing:

1. **Mount the directory, not the file.** A bind mount of a single file pins the
   inode inside the container, so a rename on the host is never observed at all.
   ``DUVO_SECRETS_DIR`` names a directory; each secret is one file inside it.
2. **Stat by path on every read.** This module never caches a file handle. It
   re-resolves the path and compares ``(inode, mtime_ns, size)``, so a rename,
   an in-place write, and a symlink swap are all detected.

The provider also keeps the last value that was read successfully. If the file
becomes temporarily unreadable — a partially written rotation, a permissions
blip — the service keeps working on the last known good value and reports
*degraded* through readiness rather than failing. Reporting failure here would
be actively harmful: an orchestrator would restart a process that was serving
correctly, turning a transient blip into an outage.

See ``docs/04-operations.md`` for the rotation runbook.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from duvo_fde.clock import Clock, SystemClock
from duvo_fde.errors import SecretUnavailableError
from duvo_fde.log import secret_registry

__all__ = ["SecretState", "SecretsProvider"]

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class _FileIdentity:
    """Identity fingerprint used to detect that a file has been replaced."""

    inode: int
    mtime_ns: int
    size: int


@dataclass(frozen=True)
class SecretState:
    """Observable state of a single secret, for readiness reporting.

    Attributes:
        name: The secret's name, which is also its filename.
        available: Whether a usable value is currently held.
        degraded: Whether the source file is unreadable while a last known good
            value is still being served.
        loaded_at_iso: When the held value was last read successfully.
        rotations: How many times a new value has been observed since start.
    """

    name: str
    available: bool
    degraded: bool
    loaded_at_iso: str | None
    rotations: int


class SecretsProvider:
    """Reads secrets from a directory and picks up rotations automatically.

    Example:
        ```python
        provider = SecretsProvider(Path("/run/secrets"))
        key = provider.get("upstream_api_key")  # re-checks the file each call
        ```
    """

    def __init__(self, directory: Path, *, clock: Clock | None = None) -> None:
        """Initialise the provider.

        Args:
            directory: Directory containing one file per secret. The filename is
                the secret name.
            clock: Clock used for load timestamps. Defaults to the system clock.
        """
        self._directory = directory
        self._clock = clock or SystemClock()
        self._values: dict[str, str] = {}
        self._identities: dict[str, _FileIdentity] = {}
        self._loaded_at: dict[str, str] = {}
        self._rotations: dict[str, int] = {}
        self._degraded: set[str] = set()

    @property
    def directory(self) -> Path:
        """Return the directory this provider reads from.

        Returns:
            The configured secrets directory.
        """
        return self._directory

    def get(self, name: str) -> str:
        """Return the current value of a secret.

        The backing file is re-checked on every call, so a rotation takes effect
        on the next request with no restart and no cache invalidation step.

        Args:
            name: Secret name, matching a filename in the secrets directory.

        Returns:
            The current secret value.

        Raises:
            SecretUnavailableError: If the secret has never been read
                successfully since the process started.
        """
        self._refresh(name)
        try:
            return self._values[name]
        except KeyError:
            msg = f"Secret {name!r} is not available."
            raise SecretUnavailableError(
                "A required credential is not available.",
                details={"secret": name, "directory": str(self._directory)},
            ) from KeyError(msg)

    def state(self, name: str) -> SecretState:
        """Report the current state of a secret without raising.

        Args:
            name: Secret name.

        Returns:
            A snapshot suitable for readiness reporting.
        """
        self._refresh(name)
        return SecretState(
            name=name,
            available=name in self._values,
            degraded=name in self._degraded,
            loaded_at_iso=self._loaded_at.get(name),
            rotations=self._rotations.get(name, 0),
        )

    def _refresh(self, name: str) -> None:
        """Re-read the secret if its backing file has changed.

        Args:
            name: Secret name.
        """
        path = self._directory / name
        try:
            # Resolve and stat by path every time. Never cache a handle: that is
            # exactly how a rotation gets missed.
            stat = path.stat()
            identity = _FileIdentity(
                inode=stat.st_ino, mtime_ns=stat.st_mtime_ns, size=stat.st_size
            )
        except OSError as exc:
            self._mark_degraded(name, reason=str(exc))
            return

        if self._identities.get(name) == identity:
            self._degraded.discard(name)
            return

        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            self._mark_degraded(name, reason=str(exc))
            return

        if not value:
            # A zero-length read usually means we caught a rotation mid-write.
            # Keep the previous value and try again on the next call.
            self._mark_degraded(name, reason="empty file")
            return

        had_previous = name in self._values
        changed = self._values.get(name) != value

        self._values[name] = value
        self._identities[name] = identity
        self._loaded_at[name] = self._clock.now().isoformat()
        self._degraded.discard(name)
        if had_previous and changed:
            self._rotations[name] = self._rotations.get(name, 0) + 1
            _LOGGER.info(
                "Secret rotated.",
                extra={"fields": {"secret": name, "rotations": self._rotations[name]}},
            )

        # Register before any caller can log the value.
        secret_registry.register(value)

    def _mark_degraded(self, name: str, *, reason: str) -> None:
        """Record that a secret's source is unreadable.

        A secret we already hold stays usable; only the degraded flag changes.

        Args:
            name: Secret name.
            reason: Why the read failed. Logged, never returned to a caller.
        """
        self._degraded.add(name)
        _LOGGER.warning(
            "Secret source unreadable; continuing on last known good value."
            if name in self._values
            else "Secret source unreadable and no previous value is held.",
            extra={"fields": {"secret": name, "reason": reason}},
        )
