#!/usr/bin/env bash
# Read the audit trail the buyer would read the next morning, and prove no
# credential is in it.
#
# The proof matters as much as the trail. A store key is never printed here:
# each value is read into a shell variable and searched for, so demonstrating
# that secrets stay out of the audit trail does not itself put one on the
# recording. That would be an unusually expensive way to make the point.
set -Eeuo pipefail
# shellcheck source=scripts/_lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

TRAIL="${DUVO_AUDIT_LOG_PATH:-./audit.log}"

step "The audit trail the buyer reads the next morning"
if [ ! -f "$TRAIL" ]; then
  die "No audit trail at ${TRAIL}. Has the assistant made a call yet?"
fi

py python - "$TRAIL" <<'PY'
"""Render the audit trail in the buyer's language rather than as JSON."""

import json
import pathlib
import sys

for line in pathlib.Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
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

step "Proving no credential reached the trail"
found=0
for key_file in secrets/korral_store_key_*; do
  [ -f "$key_file" ] || continue
  value="$(cat "$key_file")"
  if grep -qF "$value" "$TRAIL" 2>/dev/null; then
    fail "A StoreLink key from ${key_file} appears in the audit trail."
    found=1
  fi
done
[ "$found" = "0" ] || die "A credential reached the audit trail."
ok "no store key appears anywhere in the audit trail (no value was printed to find that out)"
