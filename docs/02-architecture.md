# Architecture

## The shape

```
Business user
      |
      v
  Assistant  ------ tool calls ------>  This server  ---- HTTP ---->  Upstream system
      ^                                      |
      |                                      +--> audit trail
      +------ results (see the note below) <--+--> structured logs
```

The assistant decides *what* to do. The server decides *how*, and does the work.

## The one decision everything else follows from

**Tools are shaped around the user's job, not around the upstream interface.**

Mirroring an upstream API into tools is the obvious move and it is wrong. It
produces a large surface, it forces the assistant to orchestrate several calls
to accomplish one intention, and every step of that orchestration is a chance
for the model to compose something incorrect. It also hands the model
responsibility for the business logic that sits between the calls, which is
exactly where it should never be.

A tool that matches something the user actually does resolves in one call, keeps
the calculation on the server, and is far harder to misuse. A handful of
task-shaped tools beats a faithful mirror of a REST interface every time.

## Where the logic lives

| Concern | Where | Why |
| --- | --- | --- |
| Business rules and thresholds | Server, as constants | Deterministic and unit tested. A model applying a threshold gets it wrong eventually, quietly. |
| Calculations | Server | Same reason. Arithmetic is not a language task. |
| Deciding which action to take | Assistant | This is genuinely a judgement task. |
| Validation | Server, at the boundary | Before anything else runs. |
| Deduplication | Server | The upstream is not idempotent. Ours must be. |

## Modules

| Module | Responsibility |
| --- | --- |
| `config.py` | Validated settings. Contains no secrets, by design. |
| `secrets_provider.py` | Credentials that survive rotation without a restart. |
| `log.py` | Structured logging that cannot emit a registered secret. |
| `health.py` | Liveness and readiness, kept apart. |
| `idempotency.py` | Replay handling whose outcome reaches the reporting layer. |
| `audit.py` | Append-only trail, tested to actually write. |
| `clock.py` | Injectable time, so no test sleeps. |
| `errors.py` | Typed errors with caller-safe messages. |
| `runtime.py` | Composition root. One place that answers "what does this talk to?" |
| `domain/` | Written against the brief. |

Domain code takes its collaborators as arguments, which is what keeps it
testable without a container.

## Three decisions worth defending

**The result object is passed whole.** `OperationResult` carries the outcome and
the upstream response together. Unwrapping it to get at the payload discards the
replay flag, and a reporting layer that never sees the flag counts a retry as a
second purchase. The number a human reads is then wrong while every underlying
record is correct, which is the hardest kind of defect to notice.

**Degraded is a state, not a failure.** A dependency that is impaired while the
service is still answering correctly is reported and stays in service. Treating
it as a failure causes an orchestrator to restart a working container.

**The mock upstream is deliberately unhelpful.** It is not idempotent, it
authenticates every request against a key it re-reads from disk, and it returns
only the fields in the fixture. A convenient mock hides exactly the defects that
matter: reading a field the real system never sends, and deduplication that was
never actually implemented because the mock silently did it.

## What is deliberately absent

No database, no queue, no cache, and no framework beyond what is needed. Each of
those is a real operational commitment for the customer, and none is required by
the problem. Adding infrastructure inside a one hour exercise is almost always a
mistake, and choosing not to is a decision worth stating rather than an omission
worth hiding.

## Decision records

Individual decisions with real trade-offs are recorded in `adr/`.
