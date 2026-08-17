#!/usr/bin/env bash
# Documentation guard.
#
# Compressed, telegraphic prose must never reach a reviewer. This is one of
# several structural guards and the one with the final say: it runs after a
# documentation write, in the full verification sweep, and in continuous
# integration.
#
# The guard itself is unit tested in tests/test_prose_guard.py, including
# against a deliberately terse fixture, so its behaviour is demonstrated rather
# than assumed.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

mapfile -t documents < <(
  if [[ $# -gt 0 ]]; then
    printf '%s\n' "$@"
  else
    # Tracked AND untracked, so a brand new document is checked before it is
    # ever committed. Checking only tracked files would leave the first draft
    # of every document unguarded, which is exactly when it is written fastest.
    git ls-files --cached --others --exclude-standard '*.md' 2>/dev/null ||
      find . -name '*.md' -not -path './.venv/*'
  fi
)

filtered=()
for document in "${documents[@]}"; do
  # The terse fixture exists precisely to fail this check, and is asserted on
  # by the unit tests instead.
  [[ "$document" == *"tests/fixtures/terse_example.md" ]] && continue
  [[ -f "$document" ]] && filtered+=("$document")
done

if ((${#filtered[@]} == 0)); then
  ok "no documentation to check"
  exit 0
fi

if py python -m tools.prose_guard "${filtered[@]}" "${VERBOSE:+--verbose}"; then
  record_evidence "PASS" "prose guard clean across ${#filtered[@]} documents"
  ok "documentation reads as full English (${#filtered[@]} files)"
else
  record_evidence "FAIL" "prose guard rejected compressed documentation"
  die "Documentation must be written in full English. Token compression is for code and command output only."
fi
