# CLAUDE.md

Working instructions for this repository. This file is a router: it states the
rules that always apply and points at the document that covers everything else.
Read the pointer, not the whole library.

## The mission

A one hour recorded exercise. Build a tool server that an assistant calls on
behalf of a business user, deliver a runnable artifact and a deployment
document, and present the result to a chief technology officer and later a chief
executive.

Deliverables: a recording with camera and audio, a link to this repository,
`DEPLOYMENT.md`, and something a reviewer can actually run.

## The eleven rules

1. **Never claim what you did not run.** Every documented command is executed by
   `scripts/verify_docs.sh`. If a command was not run, it is marked
   `NOT VERIFIED`, never described as working. This is the single most damaging
   defect this repository can ship.
2. **Business logic is deterministic and lives on the server.** Never delegate a
   calculation or a threshold to a model.
3. **A fixed business rule is a constant, never a parameter.** If the brief
   states a rule, a caller must not be able to change it.
4. **Validate at the boundary.** Unknown identifiers, negative and zero
   quantities, malformed payloads, missing fields. Reject them with a typed
   error from `duvo_fde.errors`.
5. **Only read fields the upstream actually returns.** Check
   `fixtures/upstream.json` first.
6. **Preserve the outcome, not just the payload.** Pass `OperationResult`
   onwards, so reporting can tell a replay from a purchase.
7. **Secrets never reach logs, errors, images, or git.**
8. **Liveness and readiness answer different questions.** Degraded but serving
   stays in service.
9. **The brief is a hypothesis, not a specification.** Contradictions get found,
   documented, and resolved without violating anything it states.
10. **Whatever reaches a model's context has left the boundary.** Treat it as an
    export of customer data, whether or not the brief says so.
11. **Documentation is written in full, clear English, always.** Token
    compression exists to make code generation and command output cheap. It
    never applies to prose. Every Markdown file, commit message, and pull
    request description is written for a human reviewer. This is enforced by
    hooks and by continuous integration, and compressing prose fails the build.

## The clock

Building stops at minute thirty eight regardless of state. A smaller verified
result beats a larger unverified one, every time.

| Minutes | Phase | Gate before moving on |
| --- | --- | --- |
| 0 to 3 | Read the brief aloud, no typing | — |
| 3 to 8 | `/brief`: requirements, traps, assumptions | traps section is not empty |
| 8 to 12 | Plan, lock scope, open the draft pull request | must-have list fits in 26 minutes |
| 12 to 38 | `/slice`, repeatedly | suite green and under five seconds |
| 38 to 45 | Probe the transport, run the stack, exercise it | a real end-to-end run observed |
| 45 to 50 | `/verify`: freeze | zero unverified claims |
| 50 to 52 | Merge and ship | continuous integration green |
| 52 to 57 | `/walkthrough`: five minutes | delivered |
| 57 to 60 | Buffer | — |

`make clock` runs the timer and announces each boundary.

## Scope discipline

An idea that arrives mid-slice goes into the deferred list in
`docs/06-assumptions-and-risks.md`. It is never built on the spot. Say "parked,
not forgotten" out loud and move on. The deferred list is quoted in the
walkthrough as evidence of judgement, so it costs nothing and demonstrates
something.

## Where to look

| Question | Document |
| --- | --- |
| What did the brief actually ask for? | `docs/00-brief-analysis.md` |
| Was this repository prepared in advance? | `docs/00-scaffold-provenance.md` |
| What are we building, in what order? | `docs/01-plan.md` |
| Why is it shaped this way? | `docs/02-architecture.md` and `docs/adr/` |
| Where does customer data go? | `docs/03-security.md` |
| How is a key rotated, how do we roll back, who owns what? | `docs/04-operations.md` |
| What has actually been verified? | `docs/05-verification.md` (written by scripts) |
| What did we assume, and what is deferred? | `docs/06-assumptions-and-risks.md` |
| What is this worth to the customer? | `docs/07-business-impact.md` |
| What do I say in the last five minutes? | `docs/PRESENTATION.md` |
| What do I do, minute by minute? | `docs/INTERVIEW-RUNBOOK.md` |
| How does a reviewer run this? | `DEPLOYMENT.md` |
| How do the agents work? | `.claude/agents/README.md` |

## The agents

Eleven, defined in `.claude/agents/`. Full roster and the authoring standard are
in `.claude/agents/README.md`.

Fire automatically: `adversarial-planner` after any plan, `unit-tester` at
commit, `code-reviewer` and `adversarial-reviewer` on pull requests,
`qa-verifier` before a push, `doc-truth-auditor` before the final push.

Invoke manually: `brief-analyst`, `planner`, `implementer`, `repo-scout`.
`fde-advisor` runs once in the background from the plan onwards.

**Budget: at most three agent invocations during the twenty six minutes of
building.** An agent that takes ninety seconds to tell you what you already knew
has cost more than it returned. Adversarial passes are capped at eight to ten
findings.

Hooks are advisory, one-shot, and guarded by sentinels so they cannot loop.
`INTERVIEW_KILL_HOOKS=1` disables all of them.

## Commands

| Command | What it does |
| --- | --- |
| `make setup` | install dependencies and git hooks, before the session |
| `make test` | fast suite, must stay under five seconds |
| `make lint` | format, lint, types, compression scope, documentation prose |
| `make sec` | secret scan, static analysis, dependency audit |
| `make up` / `make down` | build and start the stack, then stop it |
| `make verify` | everything, one verdict |
| `make ship` | verify, push with retry, open a draft pull request |
| `make clock` | the interview timer |

Slash commands: `/brief`, `/slice`, `/verify`, `/walkthrough`, `/finalize`.

Before attaching any client to the tool server, run `scripts/mcp_check.sh`. It
completes the protocol handshake over raw JSON-RPC and, when an upstream is
serving, makes real tool calls and asserts on the results. Debugging a transport
through a language model is the slowest route to an answer that exists.

A handshake alone is a weak check: it passes against a server whose every tool
call would fail, and it cannot see the error message a client is actually
handed, because the in-process tests catch an exception while a client receives
whatever the protocol library decided to put in the result. `--call` is the only
place that difference is observable, and it has caught a real one.

## What already exists, so do not rebuild it

`src/duvo_fde/` provides:

- `config.py` — validated settings from the environment, no secrets in them
- `secrets_provider.py` — key rotation with no restart, and the directory mount
  reasoning that makes it work inside a container
- `log.py` — structured JSON logging that cannot emit a registered secret
- `health.py` — liveness and readiness as separate questions
- `idempotency.py` — `OperationResult`, whose replay flag survives to reporting
- `audit.py` — an append-only trail that is tested to actually write
- `clock.py` — injectable time, so tests never sleep
- `errors.py` — typed errors with messages safe to return to a caller
- `runtime.py` — the composition root

Domain code goes in `src/duvo_fde/domain/`, which is deliberately empty.

## Reference material

A personal pattern library may exist outside this repository. It is consulted
only if `brief-analyst` reports a match of seventy per cent or higher. Below
that, ignore it entirely. Nothing is ever copied in wholesale; patterns are
adapted and understood. Reference paths are excluded by `.gitignore` and checked
again by `scripts/finalize.sh` before anything is published.

## Learned from previous submissions

These are real findings from prior candidates, and each one is already handled
in this scaffold. Do not undo them.

- Deduplication that worked, but whose replay flag was dropped before the
  reporting layer, so retries inflated reported spend. See `idempotency.py`.
- A health check that failed while the service was serving correctly from a last
  known good key, risking a restart loop. See `health.py`.
- Documentation claiming every command had been validated when two failed live.
  See `scripts/verify_docs.sh`.
- A key rotation that appeared to work but was never observed inside the
  container, because a single file was mounted rather than the directory. See
  `secrets_provider.py`.
- A submission whose main path failed on real data because it read a field the
  upstream never returned, and whose image would not build.
- Documentation describing features that did not exist, an audit log that was
  never wired up, and secrets committed alongside a virtual environment.

## Tone on camera

Talk about decisions and trade-offs, not tools. Name the requirement identifier
when implementing it. Say every assumption aloud as an assumption. Flag where
you disagree with the brief and why your reading is safer. Never claim something
works that you have not just run on screen.

## Cross-project context
Global rules for every session live in `~/.claude/CLAUDE.md` (sourced from the CQC Boss Vault, `00-Home/CLAUDE.global.md`). The vault is at `$CQC_VAULT` (fallback: `~/Library/Mobile Documents/iCloud~md~obsidian/Documents/CQC Boss Vault`); read it as plain files.
- This project's vault note: `60-Projects/FDE-Interview-Tracker.md` (Duvo row) (create it per `00-Home/Vault-Conventions.md` if missing).
- Handoff packets: `80-Handoffs/HO-<date>-<n>-<slug>.md` per `80-Handoffs/Handoff-Protocol.md`.
- Tracker: none recorded.
- Other projects: look them up in `00-Home/Source-Map.md`; write anything another project needs to the vault, not to auto-memory.
- Decisions for Christopher: options with a recommendation, in chat (see `00-Home/Working-With-Christopher.md`).
