"""Command line entry point.

Subcommands:
    ``serve``   Run the tool server. Until a transport is wired against the task
                brief, this runs a placeholder that stays alive and reports
                ready, so that the container stack, the smoke test, and the
                demonstration are all exercisable before any domain code exists.
    ``health``  Print the liveness and readiness payloads as JSON. Used by the
                container health check and by ``scripts/smoke.sh``.
    ``config``  Print the resolved configuration with no secret values.
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import threading
from types import FrameType

from duvo_fde.log import configure_logging
from duvo_fde.runtime import Runtime, build_runtime

__all__ = ["main", "serve"]

_LOGGER = logging.getLogger(__name__)


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


def serve(runtime: Runtime, *, stop: threading.Event | None = None) -> int:
    """Run the server until asked to stop.

    No transport is wired in the scaffold. Rather than exiting, which would
    leave the container stack unable to start and therefore impossible to
    rehearse against, this holds the process open and reports its state
    honestly. The real transport replaces this body once the brief is known.

    Args:
        runtime: The assembled runtime.
        stop: Event that ends the loop. One is created and wired to ``SIGTERM``
            and ``SIGINT`` when omitted.

    Returns:
        Process exit code.
    """
    owns_signals = stop is None
    stop = stop or threading.Event()

    if owns_signals:

        def _handle(signum: int, _frame: FrameType | None) -> None:
            _LOGGER.info("Shutting down.", extra={"fields": {"signal": signum}})
            stop.set()

        signal.signal(signal.SIGTERM, _handle)
        signal.signal(signal.SIGINT, _handle)

    _, ready = runtime.health.readiness()
    _LOGGER.warning(
        "No transport is wired yet. This is the scaffold placeholder: it stays "
        "alive so the stack can be started and exercised, and it is replaced by "
        "the real transport in duvo_fde.domain during the exercise.",
        extra={"fields": {"ready": ready, "upstream": runtime.settings.upstream_base_url}},
    )

    stop.wait()
    return 0


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
    return serve(runtime)


if __name__ == "__main__":
    raise SystemExit(main())
