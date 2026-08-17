#!/usr/bin/env bash
# One command, one verdict.
#
# Run this before every push and again at the verification freeze. If it is
# green, every claim this repository makes has been executed. If it is not, the
# repository is not ready, whatever the documentation says.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

SKIP_DOCKER="${SKIP_DOCKER:-0}"

# `make verify` is itself a documented command, and documentation is executed
# during this sweep. Re-entering would recurse without end.
if [[ "${DOC_VERIFIER_ACTIVE:-0}" == "1" ]]; then
  ok "verification is already running; not re-entering"
  exit 0
fi
started=$(date +%s)
stages_run=()
stages_skipped=()

stage() {
  local label="$1"; shift
  step "$label"
  "$@"
  stages_run+=("$label")
}

stage "lint, types, compression scope, prose" scripts/lint.sh
stage "full test suite with coverage" scripts/test_all.sh
stage "security sweep" scripts/security.sh

if [[ "$SKIP_DOCKER" == "1" ]]; then
  stages_skipped+=("container build" "running stack" "smoke test")
  warn "container stages skipped by request (SKIP_DOCKER=1)"
elif have docker && docker info >/dev/null 2>&1; then
  stage "container build" scripts/docker_build.sh
  stage "running stack" scripts/compose_up.sh
  stage "smoke test" scripts/smoke.sh
else
  stages_skipped+=("container build" "running stack" "smoke test")
  warn "Docker is unavailable on this machine, so the container stages did not run."
  warn "They are covered by continuous integration. Do not describe the image as"
  warn "verified locally until this machine can build it."
  record_evidence "SKIP" "container stages did not run: Docker unavailable on this machine"
fi

stage "tool server handshake" scripts/mcp_check.sh
stage "documented commands" scripts/verify_docs.sh
stage "status block" scripts/update_readme.sh

elapsed=$(($(date +%s) - started))

echo
printf '%s%s verification complete in %ss%s\n' "$C_BOLD" "$C_GREEN" "$elapsed" "$C_RESET"
printf '  stages run:     %s\n' "${#stages_run[@]}"
if ((${#stages_skipped[@]} > 0)); then
  printf '  stages skipped: %s  <- these are NOT verified\n' "${stages_skipped[*]}"
fi

record_evidence "PASS" "full verification sweep completed in ${elapsed}s (${#stages_skipped[@]} stages skipped)"

# Stamp this commit as verified so the pre-push gate can tell the difference
# between work that has been checked and work that merely compiles.
mkdir -p .claude/state
head_sha="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
touch ".claude/state/verified-${head_sha}"
