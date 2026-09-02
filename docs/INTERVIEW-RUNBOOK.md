# Interview runbook

Read this the day before, and again on the morning. It is the plan for the hour:
what to do, what to run, and what to say. Nothing here is part of the graded
submission; it is the operating manual for the person doing the exercise.

## A. The day before

| | Check |
| --- | --- |
| [ ] | `make setup` has run and finished cleanly |
| [ ] | Container layers are warm, so the first build in the session is fast |
| [ ] | `scripts/pin_base_images.sh` has written real digests |
| [ ] | A CodeQL database is prepared, if you intend to run it locally |
| [ ] | The token reduction tool is pinned, telemetry is off, and no proxy is configured |
| [ ] | A full timed dry run has been completed, including the walkthrough |
| [ ] | Every friction found in the dry run has been fixed |
| [ ] | `make verify` is green from a clean clone |
| [ ] | The recording software has been tested, and playback confirms camera **and** audio |
| [ ] | At least twenty gigabytes of disk are free |
| [ ] | The `pre-brief` tag exists and points at the scaffold commit |

## B. Workspace layout

Fixed and rehearsed, so that nothing is arranged while the clock runs.

| Pane | Contents |
| --- | --- |
| 1 | The assistant session |
| 2 | `make clock`, running for the whole hour |
| 3 | A free terminal for `make verify` and container logs |

Browser tabs: the repository, the actions page, the brief. Increase the font
size before recording; a reviewer watching a video cannot zoom in.

## C. Ten minutes before

1. Run `scripts/preflight.sh`. Resolve every blocker. Understand every warning.
2. Silence notifications on the machine and on your phone.
3. Start the recording. Confirm the camera indicator is on.
4. **Before opening the brief**, say the opening line on camera:

> "I'm Christopher Queen. This is the Duvo Forward Deployed Engineer exercise. I
> have one hour. Before I start I want to be transparent about one thing: this
> repository already has my standard engineering scaffold in it, which is
> tooling, quality gates, and infrastructure I bring to any project. It is
> tagged `pre-brief`, so you can see exactly where it ends. Everything specific
> to this task will be written in the next hour. I'm opening the brief now."

5. Open the brief.

## D. Phase by phase

### Minutes 0 to 3, read

Read the brief aloud. Do not type. Do not open an editor.

> Say: "I'm going to read this all the way through before I touch anything,
> because the most expensive mistake here is building the wrong thing quickly."

### Minutes 3 to 8, analyse

Run `/brief`. It invokes `brief-analyst` and writes `docs/00-brief-analysis.md`.

> Say: "Before I write anything I want to separate what the brief states from
> what it assumes, and look for places where it contradicts itself."

**Gate: the traps section is not empty.** Read at least one trap aloud, with your
reasoning. This is the highest-value ninety seconds in the hour.

### Minutes 8 to 12, plan

Invoke `planner`, write `docs/01-plan.md`. The adversarial pass fires
automatically; act on every high severity finding. Open the draft pull request
now, with `scripts/pr.sh`, so continuous integration and automated review run
for the rest of the session instead of blocking the end of it.

> Say: "I'm locking scope here. Anything that arrives after this goes on the
> deferred list and gets mentioned at the end as a deliberate trade-off."

**Gate: the must-have list fits in twenty six minutes.** If it does not, cut it
now rather than discovering it at minute thirty five.

### Minutes 12 to 38, build

`/slice`, repeatedly. One slice per turn. After each: tests, a paragraph in
`docs/PRESENTATION.md`, and `scripts/commit.sh`.

> Say, while implementing: the requirement identifier. Every time.
> Say, when an idea arrives: "Parked, not forgotten."

**Gate: the suite is green and under five seconds before every commit.**

### Minutes 38 to 45, integrate

Stop building. Whatever state it is in.

1. `scripts/mcp_check.sh` — the protocol handshake, with no model attached.
2. `make up` — the stack.
3. `scripts/smoke.sh` — every tool exercised.
4. Only now attach a client and drive it as a user would.
5. Start a CodeQL run in the background if you are running one.

> Say: "I'm going to prove the transport works before I put an assistant in
> front of it, because debugging a protocol through a language model is the
> slowest way to find an answer."

**Gate: a real end-to-end run has been observed, not inferred.**

### Minutes 45 to 50, verify and freeze

`/verify`. Nothing new is built from here.

`qa-verifier` reports what ran. `doc-truth-auditor` strips every claim the
evidence does not support. `scripts/walkthrough.sh` rehearses the demonstration
headlessly.

**Gate: zero unverified claims anywhere in the documentation.**

### Minutes 50 to 52, ship

Final commit, push, merge the pull request. Write `docs/EXEC-SUMMARY.md`.

### Minutes 52 to 57, walkthrough

Five minutes, from `docs/PRESENTATION.md`. Structure and timings are in section
H below.

### Minutes 57 to 60, buffer

Contingency. If you are here with nothing to fix, stop early. Finishing calmly
reads better than filling time.

## D2. The second round: driving the task from a live assistant

The first round proved the buyer task with `scripts/demo_proof.sh`, which
asserts every outcome. The second round is a different demonstration: an
assistant completes the same task through a Model Context Protocol client, so a
model chooses the tool calls and the interesting moments are the ones where the
server refuses to let it choose wrongly.

### Before recording, in this order

Three steps, and the order is not optional.

1. **Stop the mock.** `scripts/demo_client.sh` refuses to start while the port
   is held, so this has to come first.
2. **Restart the assistant's session.** This is what clears the deduplication
   store, which is held in process by design. Restarting the mock on its own
   leaves the tool server still holding the entry, and the first order of the
   take then reports as a duplicate against a mock that has no order. The
   deduplication key carries the store's trading date, which protects tomorrow's
   genuine order and does nothing at all between a rehearsal and a take on the
   same morning.
3. **Run `scripts/demo_client.sh` and leave it running.** It brings the mock up
   with its key directory pointed here rather than at the container path,
   asserts per-store key scoping over HTTP, completes a handshake, makes real
   tool calls, and then blocks.

**Within a take, do not reconnect the tool server between beats two and three.**
The session staying alive is what makes the replay beat possible.

### The five beats

| Beat | What to do | What to say |
| --- | --- | --- |
| One | `/mcp`, before any prompt | Three tools, and none of them takes a quantity, a threshold or an override. There is no vocabulary in which this agent could express an order Korral's policy does not permit. That is structural, and a test pins it |
| Two | Paste the buyer's instruction, verbatim from the brief | The server did the arithmetic and the model reported it. Store 102's gap is exactly six, and the rule says exceeds, so it is refused at the boundary |
| Three | Ask for the same order again | The order was correct both times. Without the replay flag reaching the report, the spend total a buyer reads is wrong, and the decision they make from it is wrong too. That is a commercial defect, not a technical one |
| Four | Ask the assistant to check that order's status | StoreLink is the system of record here, not this server. This is also the only tool the scripted demonstration never drives |
| Five | Ask for store 999, then run `scripts/demo_audit.sh` | It names the one store the caller already named, gives the remediation, and never reveals which other stores have keys. The audit script checks the trail for every key without printing any of their values |

### If it stalls

`scripts/demo_client.sh` prints the rehearsed fallback, which binds a different
port and therefore runs alongside rather than colliding:

```
DEMO_PORT=8081 scripts/demo_proof.sh
```

Neither path needs Docker, so a daemon problem cannot take the demonstration
down.

## E. Commands

| Need | Command |
| --- | --- |
| Fast tests | `make test` |
| Everything, one verdict | `make verify` |
| Start the stack | `make up` |
| Probe the tool server | `scripts/mcp_check.sh` |
| Bring the stack up for a live assistant | `scripts/demo_client.sh` |
| Read the audit trail back | `scripts/demo_audit.sh` |
| Commit with the gate | `scripts/commit.sh "feat(scope): what changed"` |
| Push and open the pull request | `make ship` |
| Rehearse the walkthrough | `scripts/walkthrough.sh` |

Slash commands: `/brief`, `/slice`, `/verify`, `/walkthrough`, `/finalize`.

**Token reduction needs no attention during the hour.** Documentation is
protected structurally, so there is nothing to switch off and nothing to
remember.

## F. When something goes wrong

| Situation | What you do |
| --- | --- |
| The container build fails | Switch to the documented direct path, say so on camera, keep going |
| A slice overruns its budget | Cut it, park it, move on |
| A test is flaky | Delete it or mark it slow. Never bypass the gate |
| Behind at minute 38 | Stop building anyway. A smaller verified result beats a larger unverified one |
| An agent is slow or unhelpful | `INTERVIEW_KILL_HOOKS=1` and continue by hand |
| The network drops | Commit locally, keep narrating, push afterwards |
| Continuous integration is down | Local verification output is valid evidence. Say that it is local |

None of these is a disaster. Handling one calmly on camera demonstrates
something that a smooth run cannot.

## G. Narration

- Talk about decisions and trade-offs, not about tools.
- Name the requirement identifier when you implement it.
- Say every assumption aloud, as an assumption.
- Say where you disagree with the brief, and why your reading is safer.
- Never claim something works that you have not just run on screen.
- When you find your own bug, say so. Transparency reads as competence.

## H. The five minutes

| Time | Beat |
| --- | --- |
| 0:00 | The problem. Whose job, and what their day looks like without this. Name the person. |
| 0:45 | The demonstration. `scripts/demo.sh`. Everything here already passed. |
| 2:15 | Decisions. Tool shape, server-side logic, where you disagreed with the brief, what you did not build. |
| 3:45 | Operations. Data boundaries including the model context, credential rotation, ownership, rollback. |
| 4:30 | Gaps and next steps, stated plainly. |

## I. After the recording stops

Run `scripts/finalize.sh`, then:

1. Play the recording back. Confirm camera and audio.
2. Make the repository public.
3. Open the link in a private browser window. Click through as a stranger would.
4. Follow `DEPLOYMENT.md` from a clean clone in a scratch directory.
5. Upload the recording, then send the recording and the link.

Send nothing until steps three and four have actually been done. Step four is
the one that catches anything working only because of your machine.
