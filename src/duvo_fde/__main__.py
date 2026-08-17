"""Command line entry point.

Subcommands:
    ``serve``   Run the tool server. The transport is wired here once the brief
                is known; the scaffold validates configuration and exits clearly
                rather than pretending to serve something that does not exist.
    ``health``  Print the liveness and readiness payloads as JSON. Used by the
                container health check and by ``scripts/smoke.sh``.
    ``config``  Print the resolved configuration with no secret values.
"""

from __future__ import annotations

import argparse
import json
import sys

from duvo_fde.log import configure_logging
from duvo_fde.runtime import build_runtime

__all__ = ["main"]


def _build_parser() -> argparse.ArgumentParser:
    """Construct the argument parser.

    Returns:
        The configured parser.
    """
    parser = argparse.ArgumentParser(prog="duvo-fde", description="Duvo FDE exercise tool server.")
    parser.add_argument(
        "command",
        choices=("serve", "health", "config"),
        nargs="?",
        default="health",
        help="Action to perform. Defaults to 'health'.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command line interface.

    Args:
        argv: Argument list. Defaults to ``sys.argv[1:]``.

    Returns:
        Process exit code. ``0`` on success, ``1`` when the service is not ready.
    """
    args = _build_parser().parse_args(argv)
    runtime = build_runtime()

    if args.command == "config":
        settings = runtime.settings.model_dump(mode="json")
        print(json.dumps(settings, indent=2, sort_keys=True))
        return 0

    if args.command == "health":
        readiness, ready = runtime.health.readiness()
        print(json.dumps({"liveness": runtime.health.liveness(), "readiness": readiness}, indent=2))
        return 0 if ready else 1

    configure_logging(level=runtime.settings.log_level, fmt=runtime.settings.log_format)
    print(
        "No transport is wired yet. The server entry point is implemented against "
        "the task brief in duvo_fde.domain.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
