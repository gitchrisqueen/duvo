"""Rotation behaviour, including the failure mode that motivates this design."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from duvo_fde.clock import FrozenClock
from duvo_fde.errors import SecretUnavailableError
from duvo_fde.log import secret_registry
from duvo_fde.secrets_provider import SecretsProvider
from tests.conftest import rotate_secret_by_rename, write_secret


def test_reads_a_secret_from_the_directory(secrets_dir: Path, frozen_clock: FrozenClock) -> None:
    write_secret(secrets_dir, "upstream_api_key", "initial-value-1234")
    provider = SecretsProvider(secrets_dir, clock=frozen_clock)

    assert provider.get("upstream_api_key") == "initial-value-1234"


def test_picks_up_a_rotation_performed_by_rename(
    secrets_dir: Path, frozen_clock: FrozenClock
) -> None:
    """The case that breaks a cached file handle: the inode changes."""
    original = write_secret(secrets_dir, "upstream_api_key", "initial-value-1234")
    provider = SecretsProvider(secrets_dir, clock=frozen_clock)
    assert provider.get("upstream_api_key") == "initial-value-1234"
    original_inode = original.stat().st_ino

    rotated = rotate_secret_by_rename(secrets_dir, "upstream_api_key", "rotated-value-5678")

    assert rotated.stat().st_ino != original_inode, "test setup must actually change the inode"
    assert provider.get("upstream_api_key") == "rotated-value-5678"
    assert provider.state("upstream_api_key").rotations == 1


def test_picks_up_a_rotation_written_in_place(secrets_dir: Path, frozen_clock: FrozenClock) -> None:
    write_secret(secrets_dir, "upstream_api_key", "initial-value-1234")
    provider = SecretsProvider(secrets_dir, clock=frozen_clock)
    assert provider.get("upstream_api_key") == "initial-value-1234"

    write_secret(secrets_dir, "upstream_api_key", "in-place-value-9999")

    assert provider.get("upstream_api_key") == "in-place-value-9999"


def test_no_restart_is_required_between_rotations(
    secrets_dir: Path, frozen_clock: FrozenClock
) -> None:
    """Several rotations are observed by one long-lived provider instance."""
    write_secret(secrets_dir, "upstream_api_key", "value-generation-0")
    provider = SecretsProvider(secrets_dir, clock=frozen_clock)

    observed = [provider.get("upstream_api_key")]
    for generation in range(1, 4):
        rotate_secret_by_rename(secrets_dir, "upstream_api_key", f"value-generation-{generation}")
        observed.append(provider.get("upstream_api_key"))

    assert observed == [f"value-generation-{index}" for index in range(4)]
    assert provider.state("upstream_api_key").rotations == 3


def test_keeps_serving_last_known_good_when_the_file_becomes_unreadable(
    secrets_dir: Path, frozen_clock: FrozenClock
) -> None:
    """A transient read failure degrades the service; it does not break it."""
    path = write_secret(secrets_dir, "upstream_api_key", "initial-value-1234")
    provider = SecretsProvider(secrets_dir, clock=frozen_clock)
    assert provider.get("upstream_api_key") == "initial-value-1234"

    path.unlink()

    assert provider.get("upstream_api_key") == "initial-value-1234"
    state = provider.state("upstream_api_key")
    assert state.available is True
    assert state.degraded is True


def test_recovers_when_the_file_returns(secrets_dir: Path, frozen_clock: FrozenClock) -> None:
    path = write_secret(secrets_dir, "upstream_api_key", "initial-value-1234")
    provider = SecretsProvider(secrets_dir, clock=frozen_clock)
    provider.get("upstream_api_key")
    path.unlink()
    assert provider.state("upstream_api_key").degraded is True

    rotate_secret_by_rename(secrets_dir, "upstream_api_key", "restored-value-4321")

    assert provider.get("upstream_api_key") == "restored-value-4321"
    assert provider.state("upstream_api_key").degraded is False


def test_ignores_an_empty_file_caught_mid_rotation(
    secrets_dir: Path, frozen_clock: FrozenClock
) -> None:
    """A zero-length read is a partial write, not a valid new credential."""
    path = write_secret(secrets_dir, "upstream_api_key", "initial-value-1234")
    provider = SecretsProvider(secrets_dir, clock=frozen_clock)
    provider.get("upstream_api_key")

    path.write_text("", encoding="utf-8")

    assert provider.get("upstream_api_key") == "initial-value-1234"
    assert provider.state("upstream_api_key").degraded is True


def test_raises_when_a_secret_has_never_been_readable(
    secrets_dir: Path, frozen_clock: FrozenClock
) -> None:
    provider = SecretsProvider(secrets_dir, clock=frozen_clock)

    with pytest.raises(SecretUnavailableError) as excinfo:
        provider.get("missing_key")

    assert "missing_key" not in excinfo.value.safe_message


def test_registers_rotated_values_for_redaction(
    secrets_dir: Path, frozen_clock: FrozenClock
) -> None:
    """A newly rotated secret is protected from logs the moment it is loaded."""
    write_secret(secrets_dir, "upstream_api_key", "initial-value-1234")
    provider = SecretsProvider(secrets_dir, clock=frozen_clock)
    provider.get("upstream_api_key")
    rotate_secret_by_rename(secrets_dir, "upstream_api_key", "rotated-value-5678")
    provider.get("upstream_api_key")

    scrubbed = secret_registry.scrub("token is rotated-value-5678 here")

    assert "rotated-value-5678" not in scrubbed


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read files regardless of mode")
def test_permission_error_degrades_rather_than_fails(
    secrets_dir: Path, frozen_clock: FrozenClock
) -> None:
    path = write_secret(secrets_dir, "upstream_api_key", "initial-value-1234")
    provider = SecretsProvider(secrets_dir, clock=frozen_clock)
    provider.get("upstream_api_key")

    path.chmod(0o000)
    try:
        assert provider.get("upstream_api_key") == "initial-value-1234"
        assert provider.state("upstream_api_key").degraded is True
    finally:
        path.chmod(0o600)
