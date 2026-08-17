"""Fails any documentation written in compressed, telegraphic style.

Why this exists
---------------

This repository uses a token-reduction tool so that agent runs stay cheap. That
tool is useful for code generation and for compressing command output. It is
actively harmful applied to documentation, because every Markdown file here is
read by a human reviewer.

Relying on someone remembering to switch a mode off is not a control; it is a
hope. This module is one of several structural guards, and the one that has the
final say: it runs after every documentation write, in the full verification
sweep, and in continuous integration, so compressed prose fails the build
rather than reaching a reader.

How it decides
--------------

Only ordinary paragraph text is examined. Headings, list items, tables, code
fences, inline code, URLs, and front matter are stripped first, because those
are legitimately terse in normal technical writing and would otherwise produce
false alarms. A file with less than :data:`MIN_WORDS` of paragraph text is not
judged at all.

Three statistical signals are measured, and a file fails when at least two trip
together, or when an explicit compression marker appears:

* **Article density.** Dropping "the", "a", and "an" is the single most
  characteristic feature of compressed prose.
* **Mean sentence length.** Compression produces fragments.
* **Verbless sentence ratio.** Copulas are the first thing compression removes.

Requiring two signals rather than one keeps terse-but-normal writing, such as a
short caption or a definition list, from being flagged.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

__all__ = ["ProseReport", "check_paths", "check_text", "extract_prose"]

#: Files shorter than this many words of paragraph text are not judged.
MIN_WORDS: Final = 40

#: Occurrences of "the", "a", "an" per 100 words. Ordinary technical prose sits
#: comfortably above this; compressed prose falls far below it.
MIN_ARTICLE_DENSITY: Final = 3.0

#: Mean words per sentence.
MIN_MEAN_SENTENCE_WORDS: Final = 8.0

#: Share of sentences containing no recognisable verb.
MAX_VERBLESS_RATIO: Final = 0.5

#: Number of statistical signals that must trip together for a failure.
SIGNALS_REQUIRED: Final = 2

#: Substrings that only appear deliberately, and never in reviewer-facing prose.
COMPRESSION_MARKERS: Final = (
    " w/ ",
    " b/c ",
    " wo/ ",
    " retval ",
    " cfg ",
    " impl ",
    " fn ",
    " pkg ",
    " req ",
    " resp ",
    " val ",
    " arg ",
)

_ARTICLES: Final = frozenset({"the", "a", "an"})

_VERBS: Final = frozenset(
    """
    is are was were be been being am has have had do does did will would shall should
    can could may might must run runs ran return returns use uses used make makes made
    take takes took give gives gave write writes wrote read reads keep keeps kept stay
    stays stayed get gets got need needs needed work works worked fail fails failed
    pass passes passed show shows showed mean means meant come comes came go goes went
    see sees saw know knows knew happen happens happened exist exists existed apply
    applies applied report reports reported record records recorded check checks
    checked build builds built add adds added set sets put puts let lets say says said
    tell tells told ask asks asked find finds found hold holds held carry carries live
    lives belong belongs depend depends produce produces produced remove removes
    removed replace replaces replaced treat treats treated turn turns turned call
    calls called leave leaves left create creates created start starts started stop
    stops stopped mount mounts mounted rotate rotates rotated serve serves served
    catch catches caught assert asserts asserted describe describes described
    """.split()
)

_SENTENCE_SPLIT: Final = re.compile(r"(?<=[.!?])\s+")
_WORD: Final = re.compile(r"[A-Za-z][A-Za-z'\-]*")


@dataclass
class ProseReport:
    """Outcome of checking one file.

    Attributes:
        path: The file that was checked.
        words: Number of words of paragraph text found.
        article_density: Articles per 100 words.
        mean_sentence_words: Mean words per sentence.
        verbless_ratio: Share of sentences with no recognisable verb.
        judged: Whether the file had enough prose to be assessed.
        reasons: Human-readable explanations for a failure.
    """

    path: Path
    words: int = 0
    article_density: float = 0.0
    mean_sentence_words: float = 0.0
    verbless_ratio: float = 0.0
    judged: bool = False
    reasons: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """Whether the file passed.

        Returns:
            ``True`` when no failure reasons were recorded.
        """
        return not self.reasons


def extract_prose(text: str) -> str:
    """Strip everything that is legitimately terse, leaving paragraph text.

    Args:
        text: Raw Markdown.

    Returns:
        Only the ordinary paragraph prose from the document.
    """
    without_fences = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    without_front_matter = re.sub(r"\A---\n.*?\n---\n", " ", without_fences, flags=re.DOTALL)
    without_inline_code = re.sub(r"`[^`]*`", " ", without_front_matter)
    without_links = re.sub(r"https?://\S+", " ", without_inline_code)
    without_link_text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", without_links)

    kept: list[str] = []
    for raw_line in without_link_text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(("#", ">", "|", "-", "*", "+", ":", "<!--", "<")):
            continue
        if re.match(r"^\d+[.)]\s", line):
            continue
        if line.startswith("    "):
            continue
        kept.append(line)
    return " ".join(kept)


def check_text(text: str, path: Path | None = None) -> ProseReport:
    """Assess one document's prose.

    Args:
        text: Raw Markdown.
        path: Path recorded on the report, for display only.

    Returns:
        The report for this document.
    """
    report = ProseReport(path=path or Path("<text>"))
    prose = extract_prose(text)
    words = _WORD.findall(prose)
    report.words = len(words)

    lowered = f" {prose.lower()} "
    markers = [marker.strip() for marker in COMPRESSION_MARKERS if marker in lowered]
    if markers:
        report.reasons.append(f"compression markers present: {', '.join(sorted(markers))}")

    if report.words < MIN_WORDS:
        return report

    report.judged = True

    articles = sum(1 for word in words if word.lower() in _ARTICLES)
    report.article_density = 100.0 * articles / report.words

    sentences = [s for s in _SENTENCE_SPLIT.split(prose) if _WORD.search(s)]
    if sentences:
        report.mean_sentence_words = report.words / len(sentences)
        verbless = sum(
            1
            for sentence in sentences
            if not any(word.lower() in _VERBS for word in _WORD.findall(sentence))
        )
        report.verbless_ratio = verbless / len(sentences)

    signals: list[str] = []
    if report.article_density < MIN_ARTICLE_DENSITY:
        signals.append(
            f"article density {report.article_density:.1f} per 100 words "
            f"(minimum {MIN_ARTICLE_DENSITY})"
        )
    if report.mean_sentence_words < MIN_MEAN_SENTENCE_WORDS:
        signals.append(
            f"mean sentence length {report.mean_sentence_words:.1f} words "
            f"(minimum {MIN_MEAN_SENTENCE_WORDS})"
        )
    if report.verbless_ratio > MAX_VERBLESS_RATIO:
        signals.append(
            f"verbless sentences {report.verbless_ratio:.0%} (maximum {MAX_VERBLESS_RATIO:.0%})"
        )

    if len(signals) >= SIGNALS_REQUIRED:
        report.reasons.extend(signals)
    return report


def check_paths(paths: list[Path]) -> list[ProseReport]:
    """Assess several files.

    Args:
        paths: Markdown files to check.

    Returns:
        One report per readable file.
    """
    reports: list[ProseReport] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        reports.append(check_text(text, path))
    return reports


def main(argv: list[str] | None = None) -> int:
    """Run the guard over the given files.

    Args:
        argv: Argument list. Defaults to ``sys.argv[1:]``.

    Returns:
        ``0`` when every file passes, ``1`` otherwise.
    """
    parser = argparse.ArgumentParser(
        prog="prose-guard",
        description="Fail documentation written in compressed, telegraphic style.",
    )
    parser.add_argument("paths", nargs="+", type=Path, help="Markdown files to check.")
    parser.add_argument("--verbose", action="store_true", help="Print statistics for every file.")
    args = parser.parse_args(argv)

    reports = check_paths(args.paths)
    failed = [report for report in reports if not report.ok]

    if args.verbose:
        for report in reports:
            state = "skipped" if not report.judged else ("ok" if report.ok else "FAIL")
            print(
                f"{state:>7}  {report.path}  "
                f"words={report.words} articles/100={report.article_density:.1f} "
                f"sentence={report.mean_sentence_words:.1f} verbless={report.verbless_ratio:.0%}"
            )

    for report in failed:
        print(f"FAIL {report.path}", file=sys.stderr)
        for reason in report.reasons:
            print(f"     {reason}", file=sys.stderr)

    if failed:
        print(
            "\nDocumentation must be written in full, clear English. "
            "Token compression applies to code and command output only.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
