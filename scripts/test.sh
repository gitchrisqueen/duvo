#!/usr/bin/env bash
# Fast unit suite. This runs at commit time, so it has a hard time budget.
#
# The budget is enforced rather than hoped for: continuous integration fails if
# the suite exceeds MAX_SECONDS. A slow suite stops being run, and a suite that
# stops being run stops being true.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

MAX_SECONDS="${MAX_SECONDS:-10}"

start=$(date +%s%N)
shrink py pytest -q -x -m "not slow" "$@"
elapsed_ms=$((($(date +%s%N) - start) / 1000000))

printf 'suite completed in %sms\n' "$elapsed_ms"

if ((elapsed_ms > MAX_SECONDS * 1000)); then
  record_evidence "FAIL" "unit suite took ${elapsed_ms}ms, budget ${MAX_SECONDS}s"
  die "Unit suite exceeded its ${MAX_SECONDS}s budget (${elapsed_ms}ms). Make it faster, do not raise the budget."
fi

record_evidence "PASS" "unit suite green in ${elapsed_ms}ms"
ok "unit suite green in ${elapsed_ms}ms"
