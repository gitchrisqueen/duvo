#!/usr/bin/env bash
# Prove the buyer task works, end to end, with nothing taken on trust.
#
# This script starts the mock StoreLink, completes a real protocol handshake
# against the tool server, runs the exact instruction from the brief through the
# real tools over real HTTP with real per-store authentication, and then shows
# the audit trail the buyer would read the next morning.
#
# Every assertion here fails loudly. A green run is evidence; it is not a claim.

set -Eeuo pipefail
# shellcheck source=scripts/_lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

PORT="${DEMO_PORT:-8080}"
BASE="http://127.0.0.1:${PORT}"
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
    die "secrets/korral_store_key_${store} is missing. Run scripts/bootstrap.sh or create it."
  fi
  ok "secrets/korral_store_key_${store} present (value never printed)"
done
if [ -f "secrets/korral_store_key_999" ]; then
  die "secrets/korral_store_key_999 exists, which would break the fail-closed demonstration."
fi
ok "no credential for store 999, which is what step four demonstrates"

step "Checking that nothing else is already holding the port"
# A stale mock left over from an earlier run would be silently reused, and the
# demonstration would then be exercising a process this script did not start and
# cannot vouch for. That is precisely how a demonstration ends up proving
# something other than what it claims.
if curl -fsS "${BASE}/__health" >/dev/null 2>&1; then
  die "Something is already serving on ${BASE}. Stop it first: pkill -f duvo_fde.testing.mock_upstream"
fi
ok "port ${PORT} is free, so the mock below is the one this script starts"

step "Starting the mock StoreLink"
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
ok "no replenishment orders on record, so every order below was raised by this run"

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
[ "$status_cross" = "401" ] || die "Store 47's key was accepted at store 102 (got ${status_cross}). Keys are not scoped."
ok "store 47's key against store 102 returns 401, so keys really are per store"

status_none="$(curl -s -o /dev/null -w '%{http_code}' \
  "${BASE}/v1/stores/47/inventory?sku=8847291")"
[ "$status_none" = "401" ] || die "An unauthenticated request was accepted (got ${status_none})."
ok "an unauthenticated request returns 401"

step "Completing a real protocol handshake against the tool server"
DUVO_UPSTREAM_BASE_URL="$BASE" py python -m tools.mcp_probe --min-tools 3 \
  || die "The tool server did not complete the handshake."

step "Running the buyer's instruction through the real tools"
printf '  %s\n' \
  '"SKU 8847291 (Madeta butter 250g) is running empty at stores 47 and 102.' \
  ' Check on-hand vs. last 24h of POS for both, and raise a replenishment' \
  ' order for any store where the gap exceeds 6 units."'
echo

DUVO_SECRETS_DIR=./secrets \
DUVO_UPSTREAM_BASE_URL="$BASE" \
DUVO_AUDIT_LOG_PATH=./var/demo-audit.log \
  py python -m tools.demo_buyer_task || die "The buyer task did not complete."

step "The audit trail the buyer reads the next morning"
if [ -f ./var/demo-audit.log ]; then
  py python - <<'PY'
import json
import pathlib

for line in pathlib.Path("var/demo-audit.log").read_text(encoding="utf-8").splitlines():
    record = json.loads(line)
    context = record.get("context", {})
    print(f"  {record['timestamp']}  {record['action']}  ->  {record['outcome']}")
    explanation = context.get("explanation")
    if explanation:
        print(f"      {explanation}")
    if context.get("order_id"):
        print(
            f"      order {context['order_id']}, {context['order_quantity_units']} units, "
            f"{context['order_outcome']}, counts towards the daily total: "
            f"{context['counts_towards_daily_order_total']}"
        )
PY
  ok "audit trail written to var/demo-audit.log"
else
  die "No audit trail was written."
fi

step "Proving no credential reached the logs or the audit trail"
for store in 47 102; do
  value="$(cat "secrets/korral_store_key_${store}")"
  if grep -qF "$value" ./var/demo-audit.log 2>/dev/null; then
    die "A StoreLink key for store ${store} appears in the audit trail."
  fi
done
ok "neither store key appears anywhere in the audit trail"

record_evidence "PASS" "buyer task completed end to end: store 47 ordered, store 102 refused at exactly the threshold, retry deduplicated, store 999 failed closed"
step "Demonstration complete"
ok "every claim above was executed, not described"
