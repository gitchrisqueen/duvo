#!/usr/bin/env bash
# After the recording stops. Checks the things that are embarrassing to miss.
#
# Nothing here touches repository visibility on its own: making a repository
# public is irreversible in practice, so this script checks that it is safe and
# then tells you the command to run.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

blockers=0

step "no secret ever entered the history"
if have gitleaks; then
  if shrink gitleaks detect --no-banner --redact --config .gitleaks.toml \
    --log-opts="--all --full-history"; then
    ok "history is clean"
  else
    fail "gitleaks found something in the history. Do not publish this repository."
    blockers=$((blockers + 1))
  fi
else
  fail "gitleaks is not installed, so the history was not scanned. Install it before publishing."
  blockers=$((blockers + 1))
fi

step "no personal reference material was committed"
if git log --all --name-only --pretty=format: | grep -Eq '(^|/)(\.?refkit)'; then
  fail "reference kit paths appear in the history."
  blockers=$((blockers + 1))
else
  ok "no reference kit paths in the history"
fi

step "no local secrets are tracked"
if git ls-files | grep -Ev '^secrets/\.gitkeep$' | grep -q '^secrets/'; then
  fail "files under secrets/ are tracked."
  blockers=$((blockers + 1))
else
  ok "only the placeholder is tracked under secrets/"
fi

step "the repository states what is true"
scripts/check_prose.sh || blockers=$((blockers + 1))
scripts/verify_docs.sh || blockers=$((blockers + 1))

if grep -rn "SKIP" docs/05-verification.md 2>/dev/null | tail -3 | grep -q SKIP; then
  warn "the evidence log records skipped stages. Make sure the documentation says so too."
fi

echo
printf '%s\n' "-------------------------------------------------------------"
if ((blockers > 0)); then
  fail "${blockers} blocker(s). Resolve these before publishing anything."
  exit 1
fi

cat <<'CHECKLIST'
Ready. Remaining steps, in order:

  1. Confirm the recording file plays back with BOTH camera and audio.
  2. Make the repository public:
       gh repo edit --visibility public --accept-visibility-change-consequences
  3. Open the repository link in a private browser window and click through
     README.md and DEPLOYMENT.md as a stranger would.
  4. Follow DEPLOYMENT.md from a clean clone, in a scratch directory, and
     confirm it works without anything from your machine.
  5. Upload the recording, then send the recording and the repository link.

Send nothing until step 3 and step 4 have actually been done.
CHECKLIST
printf '%s\n' "-------------------------------------------------------------"
