#!/usr/bin/env bash
# The interview clock. Run this in a visible pane for the whole session.
#
# Phase boundaries are announced out loud so that time discipline does not
# depend on remembering to look. The three that matter are stop building at
# thirty eight minutes, freeze verification at forty five, and start the
# walkthrough at fifty.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

TOTAL_MINUTES="${TOTAL_MINUTES:-60}"
START_EPOCH="${START_EPOCH:-$(date +%s)}"

# minute:phase:note
PHASES=(
  "0:Read:Read the brief aloud. No typing."
  "3:Analyse:Requirements, assumptions, traps. Nothing is built yet."
  "8:Plan:Lock the must-have list. Open the draft pull request."
  "12:Build:Vertical slices. Tests at every commit."
  "38:Integrate:STOP BUILDING. Probe the transport, run the stack, exercise it."
  "45:Verify:FREEZE. Run the full verification. Strip every unverified claim."
  "50:Ship:Merge, then rehearse nothing new. Start the walkthrough."
  "52:Walkthrough:Five minutes. Problem, demonstration, decisions, security, gaps."
  "57:Buffer:Contingency only."
)

announce() {
  printf '\n%s%s  >>> %s  <<<%s\n\n' "$C_BOLD" "$C_YELLOW" "$1" "$C_RESET"
  printf '\a'
}

current_phase() {
  local elapsed_min="$1" name="" note=""
  for entry in "${PHASES[@]}"; do
    local at="${entry%%:*}" rest="${entry#*:}"
    ((elapsed_min >= at)) && { name="${rest%%:*}"; note="${rest#*:}"; }
  done
  printf '%s|%s' "$name" "$note"
}

last_phase=""
printf 'Session clock started. %s minutes total. Ctrl-C to stop.\n\n' "$TOTAL_MINUTES"

while true; do
  now=$(date +%s)
  elapsed=$((now - START_EPOCH))
  elapsed_min=$((elapsed / 60))
  remaining=$((TOTAL_MINUTES * 60 - elapsed))

  IFS='|' read -r phase note <<<"$(current_phase "$elapsed_min")"

  if [[ "$phase" != "$last_phase" ]]; then
    announce "T+${elapsed_min} ${phase}: ${note}"
    last_phase="$phase"
  fi

  if ((remaining <= 0)); then
    announce "TIME. Stop the recording and run scripts/finalize.sh"
    break
  fi

  printf '\r  T+%02d:%02d   %-12s  %02d:%02d remaining   ' \
    $((elapsed / 60)) $((elapsed % 60)) "$phase" $((remaining / 60)) $((remaining % 60))
  sleep 5
done
