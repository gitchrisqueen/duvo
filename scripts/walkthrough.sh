#!/usr/bin/env bash
# Rehearse the demonstration, then print the walkthrough script with real numbers.
#
# Run this at the verification freeze, before speaking. It executes the
# demonstration headlessly first, so a command that is going to fail fails now,
# in private, rather than in front of a reviewer.
source "$(dirname "${BASH_SOURCE[0]}")/_lib.sh"

step "rehearsing the demonstration"
if scripts/demo.sh >/tmp/duvo-demo-rehearsal.log 2>&1; then
  ok "every demonstration command succeeded"
  record_evidence "PASS" "walkthrough demonstration rehearsed successfully"
else
  fail "a demonstration command failed. Output: /tmp/duvo-demo-rehearsal.log"
  record_evidence "FAIL" "walkthrough rehearsal failed; do not demonstrate this command"
  tail -20 /tmp/duvo-demo-rehearsal.log
  die "Fix it or cut it from the walkthrough. Do not demonstrate an unrehearsed command."
fi

tests_total="$(py python -m pytest --collect-only -q 2>/dev/null | awk -F': ' '/: [0-9]+$/ {sum += $2} END {print (sum ? sum : "?")}')"
commits="$(git rev-list --count HEAD 2>/dev/null || echo '?')"
verified_rows="$(grep -c '^| 2' docs/05-verification.md 2>/dev/null || echo 0)"

cat <<EOF

=============================================================
 FIVE MINUTE WALKTHROUGH
 ${tests_total} tests, ${commits} commits, ${verified_rows} recorded verification events
=============================================================

0:00  THE PROBLEM  (45 seconds)
      Whose job is this, and what does their day look like without it?
      Name the person, not the system. State the decision they make and how
      often they make it.

0:45  THE DEMONSTRATION  (90 seconds)
      Run scripts/demo.sh. Every command here has already passed.
      Show the thing working, not the code.

2:15  DECISIONS AND TRADE-OFFS  (90 seconds)
      - Why the tools are shaped around the job rather than the upstream API.
      - Why the calculations sit on the server and never in the model.
      - Where you disagreed with the brief, and why your reading is safer.
      - What you deliberately did not build, and why that was the right call.

3:45  SECURITY, DEPLOYMENT, OWNERSHIP  (45 seconds)
      - Where customer data goes, including what reaches the model.
      - How a credential is rotated, and how you proved it works.
      - What the customer owns, what you own, and how to roll back.

4:30  GAPS AND NEXT STEPS  (30 seconds)
      State the known gaps plainly. A reviewer will find them anyway, and
      finding them yourself is the stronger position.

-------------------------------------------------------------
 Say the scaffold out loud: the repository was prepared before
 the brief was opened, and every task-specific line was written
 in this hour. The pre-brief tag makes that auditable.
-------------------------------------------------------------
EOF
