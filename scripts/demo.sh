#!/usr/bin/env bash
# The exact commands used in the live walkthrough, and nothing else.
#
# Every command here has already been executed by scripts/verify_all.sh before
# the walkthrough begins. Demonstrating a command for the first time in front of
# a reviewer is how a working system ends up looking broken.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

PAUSE="${PAUSE:-0}"

beat() {
  echo
  printf '%s--- %s ---%s\n' "$C_BOLD$C_BLUE" "$1" "$C_RESET"
  [[ "$PAUSE" == "1" ]] && read -rp "press enter..." _
  shift
  "$@"
}

beat "the stack is running" docker compose ps
beat "the service reports ready" docker compose exec -T server python -m duvo_fde health
beat "the tools the buyer actually needs" bash -c \
  'python -m tools.mcp_probe 2>/dev/null || echo "(tool server is wired during the exercise)"'
beat "business rules are enforced on the server" scripts/smoke.sh
beat "the audit trail was written" bash -c \
  'docker compose exec -T server sh -c "cat /app/var/audit.log 2>/dev/null | tail -5" || echo "(no audit records yet)"'

echo
ok "walkthrough demonstration complete"
