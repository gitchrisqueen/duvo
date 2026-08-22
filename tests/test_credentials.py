"""Resolving a store's StoreLink key.

The naming convention in this module is the only join between a store
identifier and a credential, so these tests pin the convention itself, the
fail-closed behaviour when no credential is present, and the shape of the error
a caller is allowed to see.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from duvo_fde.credentials import (
    STORE_KEY_SECRET_PREFIX,
    StoreCredentialMissingError,
    resolve_store_key,
    store_key_secret_name,
)
from duvo_fde.runtime import Runtime

from .conftest import write_secret


def test_secret_name_is_the_prefix_followed_by_the_store() -> None:
    assert store_key_secret_name("47") == f"{STORE_KEY_SECRET_PREFIX}47"


@pytest.mark.parametrize("store_id", ["", "../etc", "47a", "-1", "1" * 11, "4 7"])
def test_a_non_numeric_store_can_never_name_a_credential_file(store_id: str) -> None:
    # This is the traversal guard. A store identifier reaches a filename, so
    # anything that is not plainly numeric must be refused before it does.
    with pytest.raises(StoreCredentialMissingError):
        store_key_secret_name(store_id)


def test_resolving_returns_the_key_currently_on_disk(runtime: Runtime, secrets_dir: Path) -> None:
    write_secret(secrets_dir, "korral_store_key_47", "key-47")

    assert resolve_store_key(runtime.secrets, "47") == "key-47"


def test_a_store_with_no_credential_fails_closed(runtime: Runtime) -> None:
    with pytest.raises(StoreCredentialMissingError) as caught:
        resolve_store_key(runtime.secrets, "999")

    assert caught.value.code == "store_credential_missing"


def test_the_error_names_only_the_store_that_was_asked_for(
    runtime: Runtime, secrets_dir: Path
) -> None:
    # Other stores are configured. The message must not become a way to
    # enumerate the rest of Korral's estate.
    write_secret(secrets_dir, "korral_store_key_47", "key-47")
    write_secret(secrets_dir, "korral_store_key_102", "key-102")

    with pytest.raises(StoreCredentialMissingError) as caught:
        resolve_store_key(runtime.secrets, "999")

    message = caught.value.safe_message
    assert "999" in message
    assert "47" not in message
    assert "102" not in message


def test_the_error_never_carries_a_key_value(runtime: Runtime, secrets_dir: Path) -> None:
    write_secret(secrets_dir, "korral_store_key_47", "super-secret-value")

    with pytest.raises(StoreCredentialMissingError) as caught:
        resolve_store_key(runtime.secrets, "999")

    assert "super-secret-value" not in caught.value.safe_message
    assert "super-secret-value" not in str(caught.value.details)


def test_a_rotated_key_is_picked_up_with_no_restart(runtime: Runtime, secrets_dir: Path) -> None:
    write_secret(secrets_dir, "korral_store_key_47", "old-key")
    assert resolve_store_key(runtime.secrets, "47") == "old-key"

    write_secret(secrets_dir, "korral_store_key_47", "new-key")

    assert resolve_store_key(runtime.secrets, "47") == "new-key"
