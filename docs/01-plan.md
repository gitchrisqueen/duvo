# Plan

> Written between minutes eight and twelve and frozen at minute twelve. Every
> entry cites a requirement identifier from `00-brief-analysis.md`.

**Re-scoped to roughly eighteen minutes of building rather than twenty six**,
because the session began with under twenty minutes remaining. The must list
below was cut to fit that, not to fit the original budget.

## Scope

### Must

The exercise fails without these.

| Entry | Requirements |
| --- | --- |
| A stdio transport for the tool server, launched by `.mcp.json`, advertising three tools | R1, R5 |
| Exactly three tools: `check_stock_position`, `raise_replenishment_order`, `get_replenishment_order_status` | R1, R3 |
| The six unit threshold as a server-side constant, compared strictly, with no tool accepting a threshold, a quantity, or an override | R7, R26, A2, A3 |
| `raise_replenishment_order` independently re-reads the position and re-applies the rule, refusing an order the policy does not permit | R7, R26 |
| Boundary validation of every identifier before any credential lookup or network call | R27, A13 |
| Per-store credentials resolved from `korral_store_key_{store_id}`, failing closed before any network call | R12, R14, R15, R22, R23 |
| Fixtures in which store 47 crosses the threshold and store 102 sits at exactly six | R2 |
| StoreLink shaped routes on the mock upstream, authenticated by `X-Korral-Store-Key` and scoped per store | R2, R22 |
| Point of sale data aggregated to a unit count, with transaction rows never returned to the caller | R6, R19, R28, R30 |
| Orders placed through `IdempotencyStore.execute`, with the created or duplicate outcome carried into the tool response | R8, R25, A4 |
| One audit record per decision and one structured log line per upstream call, joined by a correlation identifier | R10, R11 |
| A README section listing the tool surface decisions and every endpoint deliberately not exposed | R3, R4 |

### Should

Built only if the must list finishes early.

- The rotation policy on an upstream rejection: compare the key and retry a read once, never retry the write (R13).
- The stock keeping unit display name and the supplier lead time folded into responses as context (A7).
- Store local time alongside the coordinated universal time instant in the audit line (A12).

### Will not

Named explicitly, each with one line on why that is the right call. This list is
quoted in the walkthrough.

- **A general store listing tool.** `GET /v1/stores` names no store, so under per-store key scoping there is no principled credential to sign it with, and its pagination behaviour across roughly one hundred and eighty stores is undocumented (T11, T12).
- **Separate stock keeping unit and supplier tools.** Returning a supplier lead time beside a threshold invites a model to reason its way past a stated rule; both are folded into responses as context instead (T1).
- **Any threshold, quantity, or override parameter on any tool.** A caller who can change a stated business rule has changed Korral's policy (R26, T3).
- **A batch tool taking several stores at once.** Each key is scoped to a single store, so a batch call has no single correct credential, and a partially failed batch has no honest return shape (R23, T10).
- **Raw inventory or point of sale passthrough.** The point of sale endpoint returns basket, loyalty, payment and staff detail; only two integers cross into a model's context (T3, R19).
- **Deduplication across replicas.** One replica is the stated assumption, and shared state is infrastructure this exercise does not have (A11).
- **A real StoreLink integration.** The brief grants permission to stub, and StoreLink is not reachable from the public internet in any case (R2, R18).
- **A streamable transport over HTTP.** One transport proven on camera is worth more than two claimed. It is named in `DEPLOYMENT.md` as a day one question, because it is an argument to `run` rather than a rewrite.

## Slices

Minutes are relative to the start of building. Each slice is independently
demonstrable and independently committable.

| # | Slice | Requirements | Minutes | Done when |
| --- | --- | --- | --- | --- |
| 0 | Branch. The transport, three registered tools returning placeholders, `serve --stdio`, `.mcp.json` wired, and the scheduled test break repaired | R1, R5 | 0 to 2 | `scripts/mcp_check.sh` exits zero and reports three advertised tools, and `make test` is green |
| 1 | Fixtures, StoreLink shaped routes on the mock upstream, and the two store key files | R2, R22 | 2 to 6 | A request carrying store 47's key returns twelve units on hand, and the same key against store 102 returns a rejection |
| 2 | `domain/policy.py` and its tests: the constant, validation, the gap, the strict comparison, the quantity, and the not stocked case | R7, R26, R27, A1, A2, A3, A4 | 6 to 10 | `make test` is green with the boundary pinned at gaps of five, six, seven, and a negative value |
| 3 | Credential resolution, the upstream client, the service, both observability streams, and the three tools wired to real behaviour | R6, R8, R10, R11, R12, R13, R14, R15, R25 | 10 to 15 | A test drives both tools in process: store 47 orders nineteen units, store 102 is refused at exactly six, a repeated order returns a duplicate, and the audit trail holds the records |
| 4 | The README decisions section, the `DEPLOYMENT.md` delta, and the final commit | R3, R4, R16, R21 | 15 to 18 | `scripts/verify_docs.sh` and `scripts/check_prose.sh` both exit zero and the branch is pushed |

Slice zero is insurance rather than ceremony. It costs two minutes and turns
`scripts/mcp_check.sh` from a script that quietly exits zero into a real gate,
sixteen minutes before a client is attached. Debugging a transport through a
language model during the demonstration window is the slowest available route to
an answer.

## Key decisions taken before building

**Where the code lives.** `domain/policy.py` holds the pure business rule and
nothing else: no network, no clock, no filesystem. Credential resolution, the
upstream client, the service and the transport sit at package top level, outside
`domain/`, because `scripts/test_all.sh` gates that directory at ninety per cent
coverage and protocol plumbing does not belong behind a coverage gate. The
transport is proven instead by a real subprocess handshake, which is stronger
evidence than a mock heavy unit test.

**`serve` keeps its current contract and `serve --stdio` runs the transport.**
This keeps the existing command line tests green, leaves `docker-compose.yml`
untouched, and means the container still starts and stays healthy, so the smoke
test and the continuous integration container job keep working. It is also
correct on the merits: a standard input and output tool server is launched for
each session by the client, not run as a long lived service.

**The invariant everything else serves.** Tools accept identifiers only.
Identifiers select data; they never select outcomes. Every number that
participates in the threshold comparison is fetched by the server moments before
the comparison, so there is no model supplied arithmetic to validate.

## Risks to this plan

| Risk | Early signal | What we do about it |
| --- | --- | --- |
| The test suite treats warnings as errors, so a deprecation inside the newly imported protocol library fails the suite | The first test run in slice zero | Add a narrow filter naming the exact message, never a blanket suppression, and record it |
| The ninety per cent coverage gate on `domain/` fails at the verification freeze, and `make test` runs no coverage so it will not reveal this | Run `scripts/test_all.sh` once at the end of slice two rather than at the freeze | Only pure policy lives in `domain/`, and every function arrives with its test in the same edit |
| Slice three overruns and the write path is half built | Minute fifteen | Do not register a broken tool. Ship the read half and name the gap aloud; an advertised tool that fails is worse than one that was never advertised |
| The client will not connect during the demonstration window | `scripts/mcp_check.sh` green at minute two | Fall back to that script on screen: a real handshake over raw remote procedure calls against the same launch command the client uses, described honestly as the protocol proven without a client |

## Adversarial review

The automatic pass was replaced by a deliberate one, because the session started
with under twenty minutes remaining and a ninety second agent invocation is
charged against building time. Two independent planning passes were run before
this document was written, they disagreed on two material points, and both
disagreements were resolved here rather than deferred.

| Severity | Finding | Action taken |
| --- | --- | --- |
| High | The two passes disagreed on slice order. One argued the transport is the largest unknown and must be retired first; the other argued it carries no business risk and belongs last. If the transport is last and the clock runs out, there is no server and therefore no demonstration, which fails the two most heavily graded steps. | Transport first, as slice zero, with placeholder tool bodies. The cost is two minutes and the failure it prevents is total. |
| High | Running the transport inside `serve` would make the container exit as soon as it reads end of input, breaking `docker compose up --wait`, the smoke test, and the continuous integration container job. That failure would surface during the verification freeze, when there is no time to fix it. | `serve` keeps its current body and `serve --stdio` runs the transport. No compose change, no test break. |
| High | New code under `domain/` is gated at ninety per cent coverage by the full sweep, and the fast suite would not reveal a shortfall. | Only pure policy lives under `domain/`. Everything with input and output sits outside it and is covered by the global floor and by a live handshake. |
| Medium | The two passes disagreed on whether to expose an order status tool. One called it surface bloat that invites a model to poll a purchase it is unsure about. | Exposed. It is read only and cannot place an order, and without it the advice to confirm an ambiguous order before retrying is a paragraph rather than a behaviour that Korral's operators can carry out. |
| Medium | Two known test breaks were scheduled by the scaffold itself: the probe test asserts the client configuration still holds its placeholder, and commits to the default branch are blocked. Rediscovering either mid build costs minutes. | Both handled in slice zero: branch created before any edit, and the probe test rewritten in the same commit that wires the configuration. |
| Medium | The credential provider raises only when a secret has never been readable, so a deleted key file serves its last known good value indefinitely. That is right for rotation and wrong for revocation. | Recorded and split by layer: the secrets layer handles rotation, and a rejection from the upstream handles revocation. Stated aloud rather than left for a reviewer to find. |
| Low | The redacting logger's sensitive key list does not contain the StoreLink header name, and values shorter than six characters are never redacted. | The header name is added to the list, no log field ever carries headers, and both development key files are written long enough to be redactable. |
