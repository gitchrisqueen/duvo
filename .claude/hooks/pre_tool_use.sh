#!/usr/bin/env bash
# Runs before a tool call. Fast, and never chatty.
#
# Two jobs:
#   1. Before any documentation write, force token compression off for that
#      write and restate the rule. Documentation is read by a reviewer, so it is
#      written in full English, always.
#   2. Before a push, require that the current commit has actually been verified.
#
# Every gate here is one-shot and guarded by a sentinel keyed on the commit, so
# it cannot loop. INTERVIEW_KILL_HOOKS=1 disables all of them.

set -uo pipefail
[[ "${INTERVIEW_KILL_HOOKS:-0}" == "1" ]] && exit 0

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATE_DIR="$REPO_ROOT/.claude/state"
mkdir -p "$STATE_DIR"

payload="$(cat)"

read -r tool_name file_path command <<<"$(
  python3 - "$payload" <<'PYTHON'
import json, sys
try:
    data = json.loads(sys.argv[1])
except Exception:
    data = {}
tool = data.get("tool_name", "")
tool_input = data.get("tool_input") or {}
print(
    tool or "-",
    (tool_input.get("file_path") or "-").replace(" ", "_"),
    "-",
)
PYTHON
)"

raw_command="$(python3 -c '
import json, sys
try:
    data = json.loads(sys.argv[1])
except Exception:
    data = {}
print(((data.get("tool_input") or {}).get("command") or ""))
' "$payload" 2>/dev/null || true)"

# --- Documentation writes --------------------------------------------------
if [[ "$tool_name" == "Write" || "$tool_name" == "Edit" ]]; then
  if [[ "$file_path" == *.md ]]; then
    export CAVEMAN_DISABLE=1
    cat <<'REMINDER'
Reminder for this write: this is a documentation file. Write it in full, clear
English for a human reviewer. Token compression applies to code and command
output only, never to prose. A compressed document fails scripts/check_prose.sh
and fails the build.
REMINDER
  fi
  exit 0
fi

# --- Pushes ----------------------------------------------------------------
if [[ "$tool_name" == "Bash" && "$raw_command" == *"git push"* ]]; then
  head_sha="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo unknown)"
  stamp="$STATE_DIR/verified-$head_sha"
  if [[ -f "$stamp" ]]; then
    exit 0
  fi
  cat >&2 <<REMINDER
This commit ($head_sha) has no verification evidence.

Run scripts/verify_all.sh, or invoke the qa-verifier agent, before pushing.
Pushing unverified work is how documented commands end up failing in front of a
reviewer.

If the push is deliberate and you accept that, record why:
  touch .claude/state/verified-$head_sha
REMINDER
  exit 2
fi

exit 0
