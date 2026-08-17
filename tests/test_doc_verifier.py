"""The documentation verifier must actually run things and actually fail."""

from __future__ import annotations

from pathlib import Path

from tools.doc_verifier import VerifiableBlock, extract_blocks, main, run_block


def test_a_marked_block_is_extracted() -> None:
    document = "Intro.\n\n<!-- verify -->\n```bash\necho hello\n```\n"

    blocks = extract_blocks(document)

    assert len(blocks) == 1
    assert blocks[0].code == "echo hello"
    assert blocks[0].option is None


def test_an_unmarked_block_is_ignored() -> None:
    """Illustrative and destructive snippets must never be executed."""
    document = "```bash\nrm -rf /\n```\n"

    assert extract_blocks(document) == []


def test_options_are_parsed() -> None:
    document = (
        "<!-- verify: expect-fail -->\n```bash\nfalse\n```\n\n"
        "<!-- verify: skip -->\n```bash\ndeploy-to-production\n```\n"
    )

    blocks = extract_blocks(document)

    assert [block.option for block in blocks] == ["expect-fail", "skip"]


def test_a_blank_line_between_marker_and_fence_is_allowed() -> None:
    document = "<!-- verify -->\n\n```bash\necho hi\n```\n"

    assert len(extract_blocks(document)) == 1


def test_a_marker_without_a_following_fence_is_ignored() -> None:
    document = "<!-- verify -->\nJust prose, no code.\n"

    assert extract_blocks(document) == []


def test_a_passing_block_passes(tmp_path: Path) -> None:
    block = VerifiableBlock(path=Path("doc.md"), line=1, code="exit 0")

    passed, _ = run_block(block, cwd=tmp_path)

    assert passed is True


def test_a_failing_block_fails(tmp_path: Path) -> None:
    """The whole point: a documented command that breaks breaks the build."""
    block = VerifiableBlock(path=Path("doc.md"), line=1, code="exit 3")

    passed, _ = run_block(block, cwd=tmp_path)

    assert passed is False


def test_expect_fail_inverts_the_check(tmp_path: Path) -> None:
    block = VerifiableBlock(path=Path("doc.md"), line=1, code="exit 1", option="expect-fail")

    passed, _ = run_block(block, cwd=tmp_path)

    assert passed is True


def test_a_skipped_block_is_reported_not_silently_passed(tmp_path: Path) -> None:
    block = VerifiableBlock(path=Path("doc.md"), line=1, code="exit 1", option="skip")

    passed, detail = run_block(block, cwd=tmp_path)

    assert passed is True
    assert "skipped" in detail


def test_a_block_that_hangs_is_failed_not_waited_on(tmp_path: Path) -> None:
    block = VerifiableBlock(path=Path("doc.md"), line=1, code="sleep 5")

    passed, detail = run_block(block, cwd=tmp_path, timeout=1)

    assert passed is False
    assert "timed out" in detail


def test_executed_blocks_are_marked_so_the_verifier_cannot_re_enter_itself(
    tmp_path: Path,
) -> None:
    """Documentation may tell a reader to run the verification sweep.

    That block is executed here, so without a marker the verifier would invoke
    itself endlessly. The wrapper scripts step aside when they see it.
    """
    block = VerifiableBlock(path=Path("doc.md"), line=1, code='echo "$DOC_VERIFIER_ACTIVE"')

    passed, output = run_block(block, cwd=tmp_path)

    assert passed is True
    assert output.strip() == "1"


def test_the_command_line_fails_when_a_documented_command_fails(tmp_path: Path) -> None:
    document = tmp_path / "doc.md"
    document.write_text("<!-- verify -->\n```bash\nexit 1\n```\n", encoding="utf-8")

    assert main([str(document), "--root", str(tmp_path)]) == 1


def test_the_command_line_succeeds_when_documented_commands_work(tmp_path: Path) -> None:
    document = tmp_path / "doc.md"
    document.write_text("<!-- verify -->\n```bash\ntrue\n```\n", encoding="utf-8")

    assert main([str(document), "--root", str(tmp_path)]) == 0
