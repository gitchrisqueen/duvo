#!/usr/bin/env bash
# Build and start the stack, then wait until it is genuinely serving.
#
# Waiting on a health check rather than sleeping is what makes this usable in a
# live demonstration: it either comes up or it tells you why, and it never
# reports success against a container that is still starting.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

TIMEOUT_SECONDS="${TIMEOUT_SECONDS:-90}"

have docker || die "Docker is not installed."
docker info >/dev/null 2>&1 || die "The Docker daemon is not reachable."

[[ -f secrets/upstream_api_key ]] || die "No local key found. Run scripts/bootstrap.sh first."

scripts/docker_build.sh

step "starting the stack"
shrink docker compose up --detach --wait --wait-timeout "$TIMEOUT_SECONDS" || {
  fail "the stack did not become healthy"
  docker compose ps
  docker compose logs --tail 50
  record_evidence "FAIL" "docker compose did not reach a healthy state"
  exit 1
}

docker compose ps
record_evidence "PASS" "docker compose stack healthy"
ok "stack is up"
