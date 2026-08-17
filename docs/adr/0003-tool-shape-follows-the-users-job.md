# 3. Tools follow the user's job, not the upstream interface

Status: accepted

## Context

There are two obvious ways to expose an upstream system to an assistant.

The first is to mirror it: one tool per endpoint, arguments matching the
parameters. It is fast to build, it is easy to justify, and it is complete by
construction.

The second is to design a small number of tools around what the user is actually
trying to accomplish, and to put the work behind them.

## Decision

Tools are shaped around the user's job.

The mirror looks attractive and fails in a specific way. Accomplishing one
intention takes several calls, so the assistant has to orchestrate them, and
every step of that orchestration is a chance to compose something incorrect.
Worse, the logic *between* the calls, which is where the business rules live,
ends up in the model by default, because there is nowhere else for it to go.

A task-shaped tool resolves an intention in one call, keeps the rules and the
arithmetic on the server where they are deterministic and tested, and offers a
much smaller surface to misuse.

## Consequences

Fewer tools, each doing more. Adding a capability the upstream already supports
may require a code change here rather than a new argument, which is a real cost
and the right trade.

The test applied when adding a tool: can a business user describe what it does
in one sentence, without mentioning the upstream system? If not, it is shaped
around the wrong thing.
