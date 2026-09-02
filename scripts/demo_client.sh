#!/usr/bin/env bash
# Bring the environment up so an assistant can complete the buyer task live.
#
# This is the demonstration where a model chooses the tool calls, which is a
# different thing from scripts/demo_proof.sh, where a script asserts every
# outcome. Both matter. This one shows the job being done; that one proves it.
#
# What this script is defending against, in order of how badly each one would
# read on camera:
#
#   1. A green handshake against a server whose every tool call returns 401.
#      The mock's key directory defaults to a container path, so a local run
#      without MOCK_STORELINK_KEY_DIR set looks healthy and answers nothing.
#      Both environment variables are therefore set here, explicitly, and the
#      per-store scoping is asserted over HTTP before anything is declared ready.
#   2. A first order that reports as a duplicate. Deduplication is in process
#      and the mock holds orders in memory, so a rehearsal leaves state in both.
#      This script starts a clean mock; restarting the assistant's session is
#      the other half and is printed below.
#   3. An audit trail carrying yesterday's rehearsal above today's take, which
#      makes the clearest evidence the hardest to read. Rotated below.
#   4. The mock being killed by this script's own exit trap the moment it
#      finishes printing. It blocks instead, and the terminal stays open.
set -Eeuo pipefail
# shellcheck source=scripts/_lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

PORT="${DEMO_PORT:-8080}"
BASE="http://127.0.0.1:${PORT}"
FALLBACK_PORT="${DEMO_FALLBACK_PORT:-8081}"
MOCK_PID=""

cleanup() {
  if [ -n "$MOCK_PID" ]; then
    kill "$MOCK_PID" 2>/dev/null || true
    wait "$MOCK_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

step "Checking the per-store credentials this demonstration needs"
for store in 47 102; do
  if [ ! -f "secrets/korral_store_key_${store}" ]; then
    die "secrets/korral_store_key_${store} is missing. Run scripts/bootstrap.sh."
  fi
  ok "secrets/korral_store_key_${store} present (value never printed)"
done
if [ -f "secrets/korral_store_key_999" ]; then
  die "secrets/korral_store_key_999 exists, which would delete the fail-closed beat."
fi
ok "no credential for store 999, which is what the last beat demonstrates"

step "Checking that nothing else is already holding the port"
if curl -fsS "${BASE}/__health" >/dev/null 2>&1; then
  die "Something is already serving on ${BASE}. Stop it first: pkill -f duvo_fde.testing.mock_upstream"
fi
ok "port ${PORT} is free, so the mock below is the one this script starts"

step "Rotating any audit trail left over from a rehearsal"
if [ -f audit.log ]; then
  mv audit.log "audit.log.$(date -u +%Y%m%dT%H%M%SZ).bak"
  ok "previous audit trail moved aside; today's take starts on an empty file"
else
  ok "no previous audit trail"
fi

step "Starting the mock StoreLink"
# Both variables are set on purpose. MOCK_STORELINK_KEY_DIR defaults to
# /run/secrets, which is correct inside the container and wrong here, and the
# symptom of leaving it unset is a healthy looking mock that rejects every call.
MOCK_UPSTREAM_FIXTURES=fixtures/upstream.json \
MOCK_STORELINK_KEY_DIR=secrets \
  py uvicorn duvo_fde.testing.mock_upstream:app \
    --host 127.0.0.1 --port "$PORT" --log-level warning &
MOCK_PID=$!

for _ in $(seq 1 40); do
  if curl -fsS "${BASE}/__health" >/dev/null 2>&1; then break; fi
  sleep 0.25
done
curl -fsS "${BASE}/__health" >/dev/null || die "The mock StoreLink never became healthy."
kill -0 "$MOCK_PID" 2>/dev/null || die "The mock exited; the port is being served by something else."
ok "mock StoreLink serving on ${BASE}, process ${MOCK_PID}"

step "Confirming the mock starts with no orders on record"
first_order="$(curl -s -o /dev/null -w '%{http_code}' \
  -H "X-Korral-Store-Key: $(cat secrets/korral_store_key_47)" \
  "${BASE}/v1/stores/47/replenishment/REP-1001")"
[ "$first_order" = "404" ] || die "The mock already holds orders. This is not a clean run."
ok "no replenishment orders on record, so every order in the take was raised in the take"

step "Proving per-store key scoping at the transport, before any tool runs"
key47="$(cat secrets/korral_store_key_47)"
status_ok="$(curl -s -o /dev/null -w '%{http_code}' \
  -H "X-Korral-Store-Key: ${key47}" \
  "${BASE}/v1/stores/47/inventory?sku=8847291")"
[ "$status_ok" = "200" ] || die "Store 47's own key was rejected at store 47 (got ${status_ok})."
ok "store 47's key against store 47 returns 200"

status_cross="$(curl -s -o /dev/null -w '%{http_code}' \
  -H "X-Korral-Store-Key: ${key47}" \
  "${BASE}/v1/stores/102/inventory?sku=8847291")"
[ "$status_cross" = "401" ] || die "Store 47's key was accepted at store 102 (got ${status_cross})."
ok "store 47's key against store 102 returns 401, so keys really are per store"

status_none="$(curl -s -o /dev/null -w '%{http_code}' \
  "${BASE}/v1/stores/47/inventory?sku=8847291")"
[ "$status_none" = "401" ] || die "An unauthenticated request was accepted (got ${status_none})."
ok "an unauthenticated request returns 401"

step "Checking that no other copy of this repository holds different keys"
# The trap this catches, because it has already happened once. .mcp.json sets
# DUVO_SECRETS_DIR to ./secrets, which is relative to the directory the CLIENT
# is launched from, while DUVO_UPSTREAM_BASE_URL is absolute. Start the client
# from a git worktree under .claude/worktrees and the tool server reads that
# worktree's keys and sends them to the mock this script started, which only
# knows the keys beside it. Every call then fails with a 401 that reads as a
# revoked credential, and the demonstration looks broken when it is not.
conflicting=0
for other_secrets in .claude/worktrees/*/secrets; do
  [ -d "$other_secrets" ] || continue
  for store in 47 102; do
    other_key="${other_secrets}/korral_store_key_${store}"
    [ -f "$other_key" ] || continue
    # Compared by digest so that no key value is printed, here or anywhere.
    if [ "$(shasum -a 256 "$other_key" | cut -d' ' -f1)" \
       != "$(shasum -a 256 "secrets/korral_store_key_${store}" | cut -d' ' -f1)" ]; then
      warn "${other_key} holds a DIFFERENT key for store ${store}."
      conflicting=1
    fi
  done
done
if [ "$conflicting" = "1" ]; then
  warn "A client started from that directory will fail every call with a 401."
  warn "Start it from ${PWD} instead."
else
  ok "no other copy of this repository holds a conflicting key"
fi

step "Completing a handshake and real tool calls against the tool server"
DUVO_UPSTREAM_BASE_URL="$BASE" scripts/mcp_check.sh --min-tools 3 \
  || die "The tool server did not answer correctly. Do not attach a client yet."

cat <<BANNER

$(printf '%s' "${C_BOLD}${C_GREEN}")Ready. Leave this terminal running for the whole take.${C_RESET}

$(printf '%s' "${C_BOLD}")Start your client from this exact directory:${C_RESET}
  cd ${PWD} && claude

  This matters more than it looks. .mcp.json points the tool server at
  ./secrets, which is relative to wherever the client was launched, while the
  upstream address is absolute. A client started somewhere else reads a
  different secrets directory and every call fails with a 401 that reads as a
  revoked credential rather than as a wrong directory.

$(printf '%s' "${C_BOLD}")Before recording, in this order:${C_RESET}
  1. Stop this script with control-C. It refuses to start while the port is held.
  2. Restart the assistant session. That is what clears the deduplication
     store, which is in process by design. Restarting the mock alone leaves the
     server holding the entry, and the first order of your take then reports as
     a duplicate against a mock that has no order.
  3. Run this script again, then begin.

$(printf '%s' "${C_BOLD}")Within a take, do not reconnect the tool server between beats two and
three.${C_RESET} The session staying alive is what makes the replay beat possible.

$(printf '%s' "${C_BOLD}")Beat one${C_RESET}  /mcp
  Three tools. No quantity parameter, no threshold parameter, no override.

$(printf '%s' "${C_BOLD}")Beat two${C_RESET}  paste the buyer's instruction, verbatim from the brief:
  SKU 8847291 (Madeta butter 250g) is running empty at stores 47 and 102.
  Check on-hand vs. last 24h of POS for both, and raise a replenishment order
  for any store where the gap exceeds 6 units.

$(printf '%s' "${C_BOLD}")Beat three${C_RESET}  Raise that order for store 47 again.
  Same order identifier, and counts_towards_daily_order_total comes back false.

$(printf '%s' "${C_BOLD}")Beat four${C_RESET}  Check the status of that order in StoreLink.

$(printf '%s' "${C_BOLD}")Beat five${C_RESET}  Now do the same check for store 999.
  Then: scripts/demo_audit.sh

$(printf '%s' "${C_BOLD}")If the client stalls, the rehearsed fallback is:${C_RESET}
  DEMO_PORT=${FALLBACK_PORT} scripts/demo_proof.sh
  It binds its own port, so it runs alongside this one without a collision.

BANNER

record_evidence "PASS" "demonstration environment came up clean: per-store scoping asserted, handshake and real tool calls answered correctly"

step "Serving until you stop this script"
wait "$MOCK_PID"
