#!/usr/bin/env bash
# Execute every command the documentation claims works.
#
# Documentation is a claim. This is what turns "all commands were validated"
# from an assertion into a fact, locally and in continuous integration.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

# Documentation may legitimately tell a reader to run the verification sweep,
# and that block is itself executed here. Without this guard the verifier would
# re-enter itself and never finish. Stepping aside is correct: the outer run is
# already covering these documents.
if [[ "${DOC_VERIFIER_ACTIVE:-0}" == "1" ]]; then
  ok "documentation verification is already running; not re-entering"
  exit 0
fi

mapfile -t documents < <(
  if [[ $# -gt 0 ]]; then
    printf '%s\n' "$@"
  else
    git ls-files --cached --others --exclude-standard '*.md' 2>/dev/null |
      grep -v '^tests/fixtures/' || true
  fi
)

if ((${#documents[@]} == 0)); then
  ok "no documentation to verify"
  exit 0
fi

if py python -m tools.doc_verifier "${documents[@]}" --root "$REPO_ROOT"; then
  record_evidence "PASS" "every documented command executed successfully"
  ok "documented commands work"
else
  record_evidence "FAIL" "a documented command did not behave as written"
  die "A documented command failed. Fix the command or fix the documentation."
fi
