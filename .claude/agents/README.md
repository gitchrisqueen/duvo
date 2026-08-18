# The agent fleet

Eleven agents, each written to one house standard so that automatic delegation
is reliable and token cost stays bounded.

| Agent | When it runs | Model | Can write? |
| --- | --- | --- | --- |
| `brief-analyst` | manually, once the brief is open | opus | no |
| `planner` | manually, after the requirements table exists | opus | no |
| `adversarial-planner` | automatically, after any plan is written | opus | no |
| `implementer` | manually, one slice per invocation | opus | yes |
| `unit-tester` | automatically, before every commit | sonnet | tests only |
| `code-reviewer` | automatically, before every push and on pull requests | opus | no |
| `adversarial-reviewer` | automatically, on pull requests | opus | no |
| `qa-verifier` | automatically, before every push and at the freeze | sonnet | no |
| `doc-truth-auditor` | automatically, before the final push | sonnet | documentation only |
| `fde-advisor` | once, in the background, from the plan onwards | opus | no |
| `repo-scout` | on demand | haiku | no |

## The house standard

Every definition follows the same rules, and a new agent should too.

**Least privilege in the front matter.** Analysis and review agents declare
`tools: ["Read", "Grep", "Glob"]` and `disallowedTools: ["Bash", "Edit",
"Write"]`, so they are structurally incapable of changing the repository during
a recorded session. Only `implementer`, `unit-tester`, and `doc-truth-auditor`
can write, and the last of those is restricted to documentation.

**Model tiering.** Mechanical work runs on `haiku`, bounded and well-specified
work on `sonnet`, and judgement-heavy work on `opus`. Running everything on the
largest model is slower and buys nothing on a file search.

**Backgrounding.** Only `fde-advisor` sets `background: true`. Its analysis is
valuable but never on the critical path, so it runs alongside implementation.

**Worktree isolation is deliberately unused.** `isolation: worktree` would put
an agent in a separate checkout, which breaks the compose stack, the relative
paths in the scripts, and the live demonstration. The reasoning is recorded in
`docs/adr/0002-no-worktree-isolation-during-the-session.md`.

**Descriptions are activation signals.** Each one is third-person and active,
names the artifacts and situations it applies to, and uses proactive wording
only where the agent genuinely should activate on its own. A vague description
is the most common reason an agent never runs, or the wrong one does.

**Names are plain slugs.** The tracer emoji lives at the front of the
description rather than in `name`, because the name is how the agent is
resolved and addressed. The emoji still gives the visual trace in the terminal
without risking a lookup failure mid-session.

**Bodies share one shape.** A common preamble carrying the time budget, the
output cap, the non-fabrication clause, and the prose clause; then explicit
prohibitions; then a fixed output format; then short worked examples of a good
and a bad response. Examples teach far faster than prose, and every body is kept
under roughly one hundred and fifty lines so it loads quickly.

**Single-turn contract.** A sub-agent cannot be asked a follow-up question, so
each one is instructed to return a complete, self-contained artifact, to ask
nothing, and to skip the closing offer of further help.

## The agent budget during the session

At most **three** agent invocations during the twenty six minutes of building.
Adversarial passes are capped at eight to ten findings. `fde-advisor` runs in
the background and never blocks. Agents are a force multiplier on thinking, not
a substitute for typing, and an agent that takes ninety seconds to tell you
something you already knew has cost more than it returned.
