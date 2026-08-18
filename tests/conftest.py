"""Shared fixtures.

Every fixture here is in-memory or on a temporary path. Nothing in this suite
touches the network, sleeps, or depends on wall-clock time, which is what keeps
the whole suite under the five second budget.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from duvo_fde.clock import FrozenClock
from duvo_fde.config import Settings
from duvo_fde.log import secret_registry
from duvo_fde.runtime import Runtime, build_runtime


@pytest.fixture(autouse=True)
def _clean_secret_registry() -> Iterator[None]:
    """Keep registered secrets from leaking between tests."""
    secret_registry.clear()
    yield
    secret_registry.clear()


@pytest.fixture
def frozen_clock() -> FrozenClock:
    """Return a clock frozen at a fixed instant."""
    return FrozenClock(datetime(2026, 1, 1, 9, 0, 0, tzinfo=UTC))


@pytest.fixture
def secrets_dir(tmp_path: Path) -> Path:
    """Return an empty secrets directory."""
    directory = tmp_path / "secrets"
    directory.mkdir()
    return directory


@pytest.fixture
def settings(tmp_path: Path, secrets_dir: Path) -> Settings:
    """Return settings pointing at temporary paths."""
    return Settings(
        secrets_dir=secrets_dir,
        upstream_base_url="http://upstream.test",
        log_format="json",
        audit_log_path=tmp_path / "audit.log",
    )


@pytest.fixture
def runtime(settings: Settings, frozen_clock: FrozenClock) -> Runtime:
    """Return an assembled runtime that does not reconfigure global logging."""
    return build_runtime(settings, clock=frozen_clock, configure_logs=False)


def write_secret(directory: Path, name: str, value: str) -> Path:
    """Write a secret file in place.

    Args:
        directory: The secrets directory.
        name: Secret name, used as the filename.
        value: The secret value.

    Returns:
        The path written.
    """
    path = directory / name
    path.write_text(value, encoding="utf-8")
    return path


def rotate_secret_by_rename(directory: Path, name: str, value: str) -> Path:
    """Replace a secret the way a secret manager does: write then rename.

    This produces a new inode, which is precisely the case that a cached file
    handle or a stale stat comparison fails to notice.

    Args:
        directory: The secrets directory.
        name: Secret name.
        value: The new secret value.

    Returns:
        The path of the rotated secret.
    """
    staging = directory / f".{name}.new"
    staging.write_text(value, encoding="utf-8")
    target = directory / name
    staging.replace(target)
    return target
