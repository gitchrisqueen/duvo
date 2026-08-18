# Assumptions, risks, and deferred work

Everything here is stated so that a reviewer does not have to discover it.
Finding your own gaps is a stronger position than having them found for you.

## Assumptions

| ID | Assumption | Why it is needed | What changes if it is wrong |
| --- | --- | --- | --- |
| A1 | A single instance is deployed | The idempotency store is process local | Duplicate writes become possible across replicas; shared state is required |
| A2 | The deployment environment authenticates the assistant | No authentication is implemented at this boundary | An unauthenticated caller can reach the tools |
| A3 | The upstream is the system of record | The server holds no persistent state of its own | Reconciliation logic would be needed |
| A4 | Credentials are delivered as files in a mounted directory | The provider reads from a directory | A different delivery mechanism needs a different provider |

## Known limitations

**Idempotency does not survive a restart or span replicas.** The store is in
memory. A retry that arrives after a restart is treated as a new write. This is
the first thing to fix for production, and it needs shared state such as the
upstream's own idempotency support or a small persistent store.

**No rate limiting.** A caller in a loop reaches the upstream at whatever rate
it manages.

**Single tenant.** Nothing here isolates one customer's data from another's,
because nothing here is designed to hold more than one customer's data.

**Audit trail is local.** Records are appended to a file. Shipping them
somewhere durable is a deployment concern and is not solved here.

## Risks

| Risk | Likelihood | What it costs | What reduces it |
| --- | --- | --- | --- |
| The upstream returns a field shape we did not expect | Medium | The main path fails on real data | Fixtures mirror the documented response; validation at the boundary |
| A model composes a tool call we did not anticipate | Medium | Incorrect action taken | Rules are constants, not parameters; validation rejects the rest |
| Credential rotation is misconfigured as a file mount | Low | Stale credential served indefinitely, reported healthy | Documented in two places, and the smoke test performs a real rotation |
| A degraded dependency triggers restarts | Low | Outage from a recoverable state | Liveness and readiness are separate |

## Deferred

Ideas that arrived while building and were parked rather than implemented.
Parking them is the point: an idea implemented mid-slice is an idea that was
never planned, tested, or verified.

| Idea | Why it was parked | Worth doing later? |
| --- | --- | --- |
| Shared idempotency store | Needs infrastructure the exercise does not have | Yes, first priority |
| Retry with backoff on upstream failure | The caller already retries, and doubling retries hides real failures | Maybe, with a circuit breaker |
| Structured metrics | Logs cover the exercise; metrics are a deployment decision | Yes, with the customer |

## What was deliberately not built

Distinct from deferred work: these are things a reviewer might expect, which
were considered and rejected on purpose.

- **A database.** Nothing here needs persistent state. Adding one commits the
  customer to operating it.
- **A retry layer.** The caller retries, and idempotency makes that safe.
  Retrying underneath as well hides upstream failures rather than surfacing
  them.
- **A configuration file format.** Environment variables are enough, and every
  container platform already understands them.
- **An abstraction over the upstream.** There is one upstream. An interface with
  a single implementation is a guess about a second one.
