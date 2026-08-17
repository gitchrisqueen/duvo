#!/usr/bin/env bash
# Push with exponential backoff.
#
# Network trouble during the session must never become a reason to stop working.
# Commits are local and safe; pushing is best effort and retried.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

branch="${1:-$(git rev-parse --abbrev-ref HEAD)}"
delays=(2 4 8 16)

step "pushing ${branch}"
if git push -u origin "$branch"; then
  ok "pushed ${branch}"
  exit 0
fi

for delay in "${delays[@]}"; do
  warn "push failed; retrying in ${delay}s"
  sleep "$delay"
  if git push -u origin "$branch"; then
    ok "pushed ${branch}"
    exit 0
  fi
done

fail "could not push ${branch} after $((${#delays[@]} + 1)) attempts"
warn "The work is committed locally and is not lost. Keep going and push later."
exit 1
