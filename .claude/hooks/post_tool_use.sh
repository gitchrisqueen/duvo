#!/usr/bin/env bash
# Runs after a tool call.
#
# Two jobs:
#   1. Check any documentation that was just written. Compressed prose is caught
#      here, at the moment it is created, rather than in continuous integration.
#   2. Ask for an adversarial pass after a plan is written. Every plan gets
#      attacked before anybody builds against it.
#
# Sentinel files make each request one-shot, so a plan is not re-reviewed on
# every subsequent edit. INTERVIEW_KILL_HOOKS=1 disables everything here.

set -uo pipefail
[[ "${INTERVIEW_KILL_HOOKS:-0}" == "1" ]] && exit 0

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
STATE_DIR="$REPO_ROOT/.claude/state"
mkdir -p "$STATE_DIR"

payload="$(cat)"
file_path="$(python3 -c '
import json, sys
try:
    data = json.loads(sys.argv[1])
except Exception:
    data = {}
print(((data.get("tool_input") or {}).get("file_path") or ""))
' "$payload" 2>/dev/null || true)"

[[ -n "$file_path" ]] || exit 0
[[ -f "$file_path" ]] || exit 0

# --- Documentation prose ---------------------------------------------------
if [[ "$file_path" == *.md && "$file_path" != *"tests/fixtures/"* ]]; then
  if ! output="$(cd "$REPO_ROOT" && CAVEMAN_DISABLE=1 python3 -m tools.prose_guard "$file_path" 2>&1)"; then
    cat >&2 <<REMINDER
The documentation just written reads as compressed, telegraphic prose.

$output

Rewrite it in full English. Documentation is read by a reviewer, so token
compression never applies to it.
REMINDER
    exit 2
  fi
fi

# --- Plans get attacked ----------------------------------------------------
case "$file_path" in
*docs/01-plan.md | *docs/00-brief-analysis.md)
  sentinel="$STATE_DIR/adversarial-$(basename "$file_path")-$(md5sum "$file_path" | cut -c1-12)"
  if [[ ! -f "$sentinel" ]]; then
    touch "$sentinel"
    cat <<'DIRECTIVE'
A plan was just written. Before any implementation begins, invoke the
adversarial-planner agent against it. Ten findings maximum, ranked, each with a
concrete fix. Act on every high severity finding before starting to build.
DIRECTIVE
  fi
  ;;
esac

exit 0
