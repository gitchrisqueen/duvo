# Cheat sheet

One page. Print it and keep it beside the keyboard.

## The clock

| At | Do this | Gate |
| --- | --- | --- |
| 0 | Read the brief aloud. No typing. | |
| 3 | `/brief` | Traps section is not empty |
| 8 | Plan, lock scope, open the draft pull request | Must list fits 26 minutes |
| 12 | `/slice`, repeatedly | Suite green, under 5 seconds |
| **38** | **STOP BUILDING.** Probe, run the stack, exercise it | A real end-to-end run seen |
| **45** | **FREEZE.** `/verify` | Zero unverified claims |
| 50 | Merge, ship | Continuous integration green |
| 52 | `/walkthrough` | Delivered |

## Commands

```
make test      fast suite            make up       start the stack
make lint      format, types, prose  make verify   everything, one verdict
make sec       security sweep        make ship     push and open the pull request
make clock     the timer             make down     stop the stack

scripts/mcp_check.sh    handshake, and real tool calls when an upstream is up
scripts/demo_client.sh  bring the stack up for a live assistant, then block
scripts/demo_audit.sh   read the audit trail, prove no key is in it
scripts/commit.sh "feat(scope): message"
scripts/walkthrough.sh  rehearse the demonstration
scripts/finalize.sh     after the recording stops
```

## The rules

1. Never claim what you did not run.
2. Business logic on the server, never in the model.
3. A stated rule is a constant, never a parameter.
4. Validate at the boundary: unknown identifiers, negative quantities.
5. Only read fields the upstream actually returns.
6. Pass the whole result, so reporting can see a replay.
7. Secrets never reach logs, errors, images, or git.
8. Degraded is not unhealthy.
9. Whatever reaches the model has left the boundary.
10. Documentation is always full English. Nothing to switch off.

## When it goes wrong

| Problem | Answer |
| --- | --- |
| Container build fails | Use the direct path, say so, keep going |
| Slice overruns | Cut it, park it, move on |
| Flaky test | Delete or mark slow. Never bypass the gate |
| Behind at 38 | Stop anyway. Smaller and verified wins |
| Agent unhelpful | `INTERVIEW_KILL_HOOKS=1`, continue by hand |
| Network drops | Commit locally, keep talking, push later |

## Say these out loud

- The requirement identifier, every time you implement one.
- "Parked, not forgotten," whenever an idea arrives mid-slice.
- Every assumption, named as an assumption.
- Where you disagree with the brief, and why your reading is safer.
- The scaffold, before you open the brief.

## After stopping the recording

`scripts/finalize.sh`, then: confirm camera and audio in playback, make the
repository public, open the link in a private window, follow `DEPLOYMENT.md`
from a clean clone, then send.
