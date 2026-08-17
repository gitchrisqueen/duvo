#!/usr/bin/env bash
# Runs when the assistant finishes a turn.
#
# Checks one thing: has the documentation drifted ahead of the evidence? If
# documentation changed since the last verification, the claims in it have not
# been checked, and this is the last cheap moment to notice.
#
# Advisory and one-shot. INTERVIEW_KILL_HOOKS=1 disables it.

set -uo pipefail
[[ "${INTERVIEW_KILL_HOOKS:-0}" == "1" ]] && exit 0

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATE_DIR="$REPO_ROOT/.claude/state"
mkdir -p "$STATE_DIR"
cd "$REPO_ROOT" || exit 0

changed_docs="$(git status --porcelain -- '*.md' docs/ 2>/dev/null | wc -l | tr -d ' ')"
[[ "$changed_docs" == "0" ]] && exit 0

fingerprint="$(git status --porcelain -- '*.md' docs/ 2>/dev/null | md5sum | cut -c1-12)"
sentinel="$STATE_DIR/doc-audit-$fingerprint"
[[ -f "$sentinel" ]] && exit 0
touch "$sentinel"

cat <<DIRECTIVE
${changed_docs} documentation file(s) have uncommitted changes.

Before this work is shown to anybody, run the doc-truth-auditor agent over them.
Every capability claim needs code behind it and evidence in
docs/05-verification.md. A claim that a command was validated, with no evidence
row to support it, is the single most damaging defect this repository can ship.
DIRECTIVE

exit 0
