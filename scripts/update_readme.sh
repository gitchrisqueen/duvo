#!/usr/bin/env bash
# Refresh the generated status block in the README.
#
# The README is the first thing a reviewer opens, so it has to be true at every
# moment rather than at the end. The numbers below are read from what actually
# ran, not typed in, which is the only way a status block stays honest.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

tests_total="$(py python -m pytest --collect-only -q 2>/dev/null | awk -F': ' '/: [0-9]+$/ {sum += $2} END {print (sum ? sum : "?")}')"

coverage_percent="?"
if [[ -f coverage.xml ]]; then
  coverage_percent="$(py python -c "
import re, pathlib
text = pathlib.Path('coverage.xml').read_text()
match = re.search(r'line-rate=\"([0-9.]+)\"', text)
print(f'{float(match.group(1)) * 100:.0f}%' if match else '?')
" 2>/dev/null || echo '?')"
fi

last_verified="never"
if [[ -f docs/05-verification.md ]]; then
  last_verified="$(grep -E '^\| 2' docs/05-verification.md | tail -1 | awk -F'|' '{print $2}' | xargs || echo 'never')"
fi

commit_sha="$(git rev-parse --short HEAD 2>/dev/null || echo 'uncommitted')"
branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'unknown')"

py python - "$tests_total" "$coverage_percent" "$last_verified" "$commit_sha" "$branch" <<'PYTHON'
import pathlib, sys

tests, coverage, verified, sha, branch = sys.argv[1:6]
readme = pathlib.Path("README.md")
text = readme.read_text(encoding="utf-8")

block = f"""<!-- BEGIN:status -->
| | |
| --- | --- |
| Branch | `{branch}` |
| Commit | `{sha}` |
| Tests | {tests} |
| Coverage | {coverage} |
| Last verified | {verified} |

This table is written by `scripts/update_readme.sh` from what actually ran. It
is never edited by hand.
<!-- END:status -->"""

start, end = "<!-- BEGIN:status -->", "<!-- END:status -->"
if start in text and end in text:
    head = text.split(start)[0]
    tail = text.split(end)[1]
    readme.write_text(head + block + tail, encoding="utf-8")
    print("status block refreshed")
else:
    print("no status block found in README.md; nothing to refresh")
PYTHON

ok "README status refreshed"
