#!/usr/bin/env bash
# Format, lint, typecheck, and check that documentation reads as English.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

FIX="${FIX:-1}"

if [[ "$FIX" == "1" ]]; then
  timed "ruff format" shrink py ruff format .
  timed "ruff check --fix" shrink py ruff check --fix .
else
  timed "ruff format --check" shrink py ruff format --check .
  timed "ruff check" shrink py ruff check .
fi

timed "mypy" shrink py mypy

# ---------------------------------------------------------------------------
# Token compression may only ever wrap a COMMAND, so that its output is smaller
# on the way into an agent's context. Applying it to file contents, or to
# anything a human reads, is the failure mode this repository guards against.
# This check enforces the rule on the scripts themselves.
# ---------------------------------------------------------------------------
step "token compression scope"
violations="$(
  grep -rnE '(shrink|caveman[[:space:]]+shrink)[[:space:]]+--?[[:space:]]*(cat|head|tail|less|bat)\b|shrink[[:space:]]+(cat|head|tail|less|bat)\b' \
    scripts/ .claude/ 2>/dev/null || true
)"
if [[ -n "$violations" ]]; then
  fail "token compression applied to file contents rather than to a command:"
  printf '%s\n' "$violations"
  die "shrink wraps commands only. Documentation and file contents are never compressed."
fi
ok "token compression is scoped to command output only"

timed "documentation prose" scripts/check_prose.sh

if have shellcheck; then
  timed "shellcheck" shellcheck scripts/*.sh
else
  warn "shellcheck not installed; skipping shell linting"
fi

record_evidence "PASS" "lint, types, compression scope, and prose checks clean"
ok "lint clean"
