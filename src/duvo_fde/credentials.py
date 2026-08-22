"""Resolving the right StoreLink key for the store being acted on.

Korral issues one key per store and rotates them weekly. ``SecretsProvider``
looks a secret up by filename and has no notion of a store, so the store is
encoded in the name. That naming convention is the only join between a store
identifier and a credential, which makes this module small and load bearing.
"""

from __future__ import annotations

import re
from typing import Final

from duvo_fde.errors import SecretUnavailableError
from duvo_fde.secrets_provider import SecretsProvider

__all__ = [
    "STORE_KEY_SECRET_PREFIX",
    "StoreCredentialMissingError",
    "resolve_store_key",
    "store_key_secret_name",
]

STORE_KEY_SECRET_PREFIX: Final = "korral_store_key_"  # noqa: S105 - a filename prefix, not a key
"""Filename prefix for a store's StoreLink key inside the mounted directory.

The prefix names the system and the credential type, so a directory holding
credentials for several systems stays readable, and an operator's directory
listing answers "which stores are configured" at a glance, which is the first
question asked during an incident. The store identifier is the suffix, so a
sorted listing is in store order.
"""

_SAFE_STORE_ID: Final = re.compile(r"^[0-9]{1,10}$")


class StoreCredentialMissingError(SecretUnavailableError):
    """No StoreLink credential is configured for the requested store.

    This is deliberately a different code from an unknown store. The two have
    different owners: a missing credential is Korral's information technology
    team's to fix, while an unknown store is the caller's mistake. Conflating
    them is how an operator spends twenty minutes on the wrong problem.
    """

    code = "store_credential_missing"


def store_key_secret_name(store_id: str) -> str:
    """Map a store identifier onto the filename holding its key.

    Args:
        store_id: A validated store identifier.

    Returns:
        The secret name, which is also the filename inside the mounted
        directory.

    Raises:
        StoreCredentialMissingError: The identifier is not a shape that could
            name a credential file.
    """
    if not _SAFE_STORE_ID.match(store_id):
        raise StoreCredentialMissingError(
            "A StoreLink credential can only be resolved for a numeric store identifier.",
            details={"store_id": store_id},
        )
    return f"{STORE_KEY_SECRET_PREFIX}{store_id}"


def resolve_store_key(secrets: SecretsProvider, store_id: str) -> str:
    """Return the StoreLink key for one store, failing closed.

    This runs before any network call is made, so a store this server holds no
    credential for is never queried at all. The error names only the store the
    caller itself supplied: it never enumerates which stores are configured, so
    it cannot be used to probe the rest of Korral's estate, and it is identical
    in shape for every unconfigured store.

    Args:
        secrets: The provider backed by the mounted secrets directory.
        store_id: A validated store identifier.

    Returns:
        The current key for that store. The provider re-reads the file on every
        access, so a key rotated by Korral is picked up with no restart.

    Raises:
        StoreCredentialMissingError: No credential is configured for the store.
    """
    name = store_key_secret_name(store_id)
    try:
        return secrets.get(name)
    except SecretUnavailableError as exc:
        raise StoreCredentialMissingError(
            f"No StoreLink credential is configured for store {store_id}. This server holds "
            "one key per store and none is present for that store. Korral information "
            f"technology: place that store's key in the mounted secrets directory as the "
            f"file {name}, and it will be picked up on the next call with no restart.",
            details={"store_id": store_id, "secret": name},
        ) from exc
