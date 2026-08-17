#!/usr/bin/env bash
# Full suite with coverage.
#
# The global coverage floor is deliberately modest and lives in pyproject.toml.
# What is gated hard here is the critical path: the modules where a defect is
# expensive. Chasing a high global percentage produces tests written to move a
# number rather than to catch a bug.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

CRITICAL_PATH_MIN="${CRITICAL_PATH_MIN:-90}"
CRITICAL_MODULES=(
  "src/duvo_fde/idempotency.py"
  "src/duvo_fde/secrets_provider.py"
  "src/duvo_fde/health.py"
  "src/duvo_fde/log.py"
  "src/duvo_fde/audit.py"
  "src/duvo_fde/domain"
)

shrink py pytest --cov --cov-report=term-missing --cov-report=xml "$@"

globs=()
for module in "${CRITICAL_MODULES[@]}"; do
  if [[ -d "$module" ]]; then
    globs+=("$module/*")
  elif [[ -f "$module" ]]; then
    globs+=("$module")
  fi
done

if ((${#globs[@]} > 0)); then
  include="$(
    IFS=','
    printf '%s' "${globs[*]}"
  )"
  step "critical path coverage (minimum ${CRITICAL_PATH_MIN}%)"
  shrink py coverage report --include="$include" --fail-under="$CRITICAL_PATH_MIN"
fi

record_evidence "PASS" "full suite green, critical path at or above ${CRITICAL_PATH_MIN}%"
ok "full suite green"
