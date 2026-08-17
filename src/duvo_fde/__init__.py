"""Forward Deployed Engineer exercise scaffold.

This package provides the infrastructure that every integration server needs
regardless of the business domain: configuration, secret handling that survives
rotation, structured logging that cannot leak secrets, a health model that
distinguishes liveness from readiness, idempotent write handling, and an
append-only audit trail.

Domain-specific code lives in :mod:`duvo_fde.domain` and is written against the
task brief.
"""

__all__ = ["__version__"]

__version__ = "0.1.0"
