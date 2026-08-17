"""Executes the commands that the documentation claims work.

The strongest criticism made of an otherwise excellent submission in this
process was that its documentation asserted every command had been validated
when two of them failed during the live demonstration. Documentation is a claim,
and an unverified claim is a liability.

Any shell block in a Markdown file preceded by a ``<!-- verify -->`` marker is
executed by this module, locally and in continuous integration. A block that
fails fails the build, so the documentation cannot drift away from the code
without somebody noticing.

Markers:
    ``<!-- verify -->``              Run the block; it must exit zero.
    ``<!-- verify: expect-fail -->`` Run the block; it must exit non-zero. Useful
                                     for demonstrating a rejected input.
    ``<!-- verify: skip -->``        Record the block as deliberately unverified.
                                     It is reported, never silently ignored.

Anything without a marker is not executed, so illustrative snippets and
destructive examples stay safe.
"""

from __future__ import annotations

import argparse
import os
import re

# Running documented commands is the entire purpose of this module.
import subprocess  # nosec B404
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

__all__ = ["VerifiableBlock", "extract_blocks", "run_block"]

_MARKER: Final = re.compile(r"^<!--\s*verify(?::\s*(?P<option>[a-z-]+))?\s*-->\s*$")
_FENCE_OPEN: Final = re.compile(r"^```(?P<language>bash|sh|shell|console)\s*$")
_FENCE_CLOSE: Final = re.compile(r"^```\s*$")

#: Per-block wall-clock limit. A documented command that takes longer than this
#: is not a command a reviewer will run.
DEFAULT_TIMEOUT_SECONDS: Final = 300


@dataclass(frozen=True)
class VerifiableBlock:
    """One shell block that the documentation promises works.

    Attributes:
        path: File the block came from.
        line: Line number of the opening fence, for error messages.
        code: The shell source to execute.
        option: ``None``, ``"expect-fail"``, or ``"skip"``.
    """

    path: Path
    line: int
    code: str
    option: str | None = None


def extract_blocks(text: str, path: Path | None = None) -> list[VerifiableBlock]:
    """Find every marked shell block in a document.

    Args:
        text: Raw Markdown.
        path: Path recorded on each block, for display only.

    Returns:
        The marked blocks, in document order.
    """
    blocks: list[VerifiableBlock] = []
    lines = text.splitlines()
    index = 0
    source = path or Path("<text>")

    while index < len(lines):
        marker = _MARKER.match(lines[index].strip())
        if not marker:
            index += 1
            continue

        cursor = index + 1
        while cursor < len(lines) and not lines[cursor].strip():
            cursor += 1
        if cursor >= len(lines) or not _FENCE_OPEN.match(lines[cursor].strip()):
            index += 1
            continue

        fence_line = cursor + 1
        body: list[str] = []
        cursor += 1
        while cursor < len(lines) and not _FENCE_CLOSE.match(lines[cursor].strip()):
            body.append(lines[cursor])
            cursor += 1

        blocks.append(
            VerifiableBlock(
                path=source,
                line=fence_line,
                code="\n".join(body),
                option=marker.group("option"),
            )
        )
        index = cursor + 1

    return blocks


def run_block(
    block: VerifiableBlock,
    *,
    cwd: Path,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> tuple[bool, str]:
    """Execute one block and decide whether it behaved as documented.

    Args:
        block: The block to run.
        cwd: Working directory, normally the repository root.
        timeout: Wall-clock limit in seconds.

    Returns:
        A tuple of whether the block behaved as documented and the combined
        output, truncated for display.
    """
    if block.option == "skip":
        return True, "skipped by marker"

    # A documented command may reasonably be "run the verification sweep", which
    # would re-enter this module and never terminate. The marker below lets the
    # wrapper scripts detect re-entry and step aside, so documentation can
    # legitimately mention its own tooling without hanging the build.
    environment = {**os.environ, "DOC_VERIFIER_ACTIVE": "1"}

    try:
        # The command comes from this repository's own documentation, which is
        # reviewed in the same pull request as the code it describes. No shell
        # is interposed and the argument list is fixed.
        completed = subprocess.run(  # noqa: S603  # nosec B603
            ["/usr/bin/env", "bash", "-euo", "pipefail", "-c", block.code],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=environment,
        )
    except subprocess.TimeoutExpired:
        return False, f"timed out after {timeout}s"

    output = (completed.stdout + completed.stderr).strip()
    succeeded = completed.returncode == 0
    expected = succeeded if block.option != "expect-fail" else not succeeded
    return expected, output[-2000:]


def main(argv: list[str] | None = None) -> int:
    """Verify the documented commands in the given files.

    Args:
        argv: Argument list. Defaults to ``sys.argv[1:]``.

    Returns:
        ``0`` when every marked block behaved as documented, ``1`` otherwise.
    """
    parser = argparse.ArgumentParser(
        prog="doc-verifier",
        description="Execute the shell blocks the documentation claims work.",
    )
    parser.add_argument("paths", nargs="+", type=Path, help="Markdown files to verify.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Working directory.")
    parser.add_argument("--list", action="store_true", help="List blocks without running them.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    args = parser.parse_args(argv)

    blocks: list[VerifiableBlock] = []
    for path in args.paths:
        if path.is_file():
            blocks.extend(extract_blocks(path.read_text(encoding="utf-8"), path))

    if not blocks:
        print("No blocks are marked for verification.")
        return 0

    if args.list:
        for block in blocks:
            marker = block.option or "run"
            first = block.code.strip().splitlines()[0] if block.code.strip() else ""
            print(f"{block.path}:{block.line}  [{marker}]  {first}")
        return 0

    failures = 0
    skipped = 0
    for block in blocks:
        passed, output = run_block(block, cwd=args.root, timeout=args.timeout)
        label = f"{block.path}:{block.line}"
        if block.option == "skip":
            skipped += 1
            print(f"SKIP {label} (marked unverified)")
        elif passed:
            print(f"ok   {label}")
        else:
            failures += 1
            print(f"FAIL {label}", file=sys.stderr)
            print(
                f"     {block.code.strip().splitlines()[0] if block.code.strip() else ''}",
                file=sys.stderr,
            )
            for line in output.splitlines()[-15:]:
                print(f"     | {line}", file=sys.stderr)

    total = len(blocks)
    print(f"\n{total - failures - skipped} verified, {skipped} skipped, {failures} failed")
    if skipped:
        print("Blocks marked 'skip' are reported here rather than presented as verified.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
