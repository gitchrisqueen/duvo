"""The documentation guard is proven against a real terse document.

A guard that has only ever been configured is a claim. These tests are what let
the repository state that compressed prose cannot reach a reviewer.
"""

from __future__ import annotations

from pathlib import Path

from tools.prose_guard import check_text, extract_prose, main

FIXTURE = Path(__file__).parent / "fixtures" / "terse_example.md"

NORMAL_PROSE = """
# Deployment

The service reads its credentials from a directory rather than from individual
files, because a bind mount of a single file pins the inode inside the container
and a rotation performed on the host is never observed. Mounting the directory
means the provider can re-resolve the path on every read, so a rotated key takes
effect on the next request without a restart.

The health endpoints answer two different questions. Liveness asks whether the
process is broken beyond recovery, and readiness asks whether traffic should be
routed to this instance right now. Collapsing them into one endpoint causes an
orchestrator to restart a container that is serving correctly.
"""


def test_a_deliberately_terse_document_is_rejected() -> None:
    """The negative case. If this ever passes, the guard has stopped working."""
    report = check_text(FIXTURE.read_text(encoding="utf-8"), FIXTURE)

    assert report.judged is True
    assert report.ok is False
    assert report.reasons


def test_ordinary_technical_prose_is_accepted() -> None:
    report = check_text(NORMAL_PROSE)

    assert report.judged is True
    assert report.ok is True


# Directories that contain Markdown belonging to something other than this
# checkout's own documentation. `.claude` is the one worth naming: Claude Code
# places git worktrees under `.claude/worktrees`, and a worktree is a complete
# second copy of this repository. Walking into one makes the test read another
# checkout's files, including its copy of the deliberately terse fixture below,
# and the test then fails for a reason that has nothing to do with the
# documentation being judged.
_NOT_OUR_DOCUMENTATION = frozenset({".venv", "node_modules", ".claude", ".git"})


def test_every_tracked_document_in_this_repository_passes() -> None:
    """The guard is run against the real documentation, not just fixtures."""
    root = Path(__file__).resolve().parents[1]
    documents = [
        path
        for path in root.rglob("*.md")
        if not _NOT_OUR_DOCUMENTATION.intersection(path.parts) and path.name != FIXTURE.name
    ]

    failures = {
        str(report.path.relative_to(root)): report.reasons
        for report in (check_text(p.read_text(encoding="utf-8"), p) for p in documents)
        if not report.ok
    }

    assert failures == {}, f"documentation written in compressed style: {failures}"


def test_code_fences_are_not_treated_as_prose() -> None:
    """A file that is mostly code must not be judged on the code."""
    document = "# Title\n\n```bash\nmake up && make verify\n```\n"

    report = check_text(document)

    assert report.judged is False


def test_headings_lists_and_tables_are_excluded() -> None:
    document = "# T\n\n- terse item\n- another\n\n| a | b |\n| - | - |\n"

    assert extract_prose(document).strip() == ""


def test_compression_markers_fail_even_a_short_document() -> None:
    """Markers are unambiguous, so they do not need a second signal."""
    report = check_text("Run the build w/ the cache enabled.")

    assert report.ok is False
    assert "compression markers" in report.reasons[0]


def test_the_command_line_returns_a_failing_exit_code() -> None:
    assert main([str(FIXTURE)]) == 1


def test_the_command_line_succeeds_on_good_prose(tmp_path: Path) -> None:
    good = tmp_path / "good.md"
    good.write_text(NORMAL_PROSE, encoding="utf-8")

    assert main([str(good), "--verbose"]) == 0
