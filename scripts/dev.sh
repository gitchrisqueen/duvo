#!/usr/bin/env bash
# Run the server on the host against the mock upstream in a container.
#
# This is the fast inner loop: the mock keeps running while the server restarts
# in under a second, so there is no image rebuild between edits.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

export DUVO_SECRETS_DIR="${DUVO_SECRETS_DIR:-$REPO_ROOT/secrets}"
export DUVO_UPSTREAM_BASE_URL="${DUVO_UPSTREAM_BASE_URL:-http://localhost:8080}"
export DUVO_LOG_FORMAT="${DUVO_LOG_FORMAT:-console}"
export DUVO_AUDIT_LOG_PATH="${DUVO_AUDIT_LOG_PATH:-$REPO_ROOT/var/audit.log}"

if have docker && docker info >/dev/null 2>&1; then
  if ! docker compose ps --services --filter status=running 2>/dev/null | grep -q mock-upstream; then
    step "starting the mock upstream"
    docker compose up --detach --wait mock-upstream || warn "could not start the mock upstream"
  fi
else
  warn "Docker is unavailable; starting the mock upstream on the host instead"
  export MOCK_UPSTREAM_FIXTURES="$REPO_ROOT/fixtures/upstream.json"
  export MOCK_UPSTREAM_API_KEY_FILE="$REPO_ROOT/secrets/upstream_api_key"
  py uvicorn duvo_fde.testing.mock_upstream:app --host 127.0.0.1 --port 8080 &
  trap 'kill %1 2>/dev/null || true' EXIT
fi

step "starting the server"
exec_args=("${@:-serve}")
py python -m duvo_fde "${exec_args[@]}"
