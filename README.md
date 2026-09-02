# Duvo Forward Deployed Engineer exercise

A tool server that an assistant calls on behalf of a business user. The
assistant decides *what* to do; this server decides *how*, and does the
arithmetic itself.

That split is the whole design. Every calculation and every business rule is
deterministic Python on the server, unit tested, and never delegated to a
language model. A model asked to apply a threshold will eventually get it wrong
on one input in a hundred, quietly, and nobody will notice until the numbers
matter.

<!-- BEGIN:status -->
| | |
| --- | --- |
| Branch | `fix/demo-client-wrong-directory` |
| Commit | `055906a` |
| Tests | 183 |
| Coverage | 80% |
| Last verified | 2026-09-02T22:32:12Z |

This table is written by `scripts/update_readme.sh` from what actually ran. It
is never edited by hand.
<!-- END:status -->


## The agent facing tool surface

The brief grades which tools are exposed, which are deliberately not, what shapes
come back, and how things are named. Those decisions are recorded here.

### One invariant governs the whole surface

Tools accept identifiers only. Identifiers select data; they never select
outcomes. Every number that takes part in Korral's threshold comparison is
fetched by this server moments before the comparison is made, so there is no
model supplied arithmetic to validate and no vocabulary in which a caller could
express an order that Korral's policy does not permit.

### Three tools

| Tool | Kind | What it does |
| --- | --- | --- |
| `check_stock_position(store_id, sku)` | read only | Units on hand against units sold through the till in the trailing twenty four hours, the gap, and this server's decision. |
| `raise_replenishment_order(store_id, sku)` | write, deduplicated | Re-reads the position, re-applies the rule, and raises an order only when Korral's policy requires one. |
| `get_replenishment_order_status(store_id, order_id)` | read only | StoreLink's current status for an order already raised. |

**No tool takes a threshold, a quantity, a gap, or an override.** The threshold
is a rule the brief states as fact, so it is the constant
`REPLENISHMENT_GAP_THRESHOLD_UNITS` in `duvo_fde.domain.policy` and not a
setting, not a default argument, and not a parameter. "Exceeds" is read strictly:
a gap of exactly six does not raise an order.

**The write tool re-reads rather than trusting the caller.** If the two tools
were separate and the write simply accepted what it was told, the model would be
the thing applying Korral's threshold. Instead the order tool independently
fetches the position again, recomputes the gap, applies the rule itself, and
refuses when the policy is not met, whatever an earlier result said. Stock moves
between a check and an order, so this is also the more correct observation
rather than duplicated work.

**Quantity is a specification hole we closed on the server.** The brief says when
to order and never says how much. This server orders the gap, which restores
roughly one day of observed demand. It is recorded as an assumption, isolated in
one function, and shown in every response.

**One store per call.** A batch tool spanning several stores has no single
correct credential, because each key is scoped to one store, and a partly failed
batch has no honest return shape. Two stores is four tool calls, and each
store's decision stays individually visible and individually auditable.

### What is deliberately not exposed

| Endpoint | Why not |
| --- | --- |
| `GET /v1/stores` | Names no store, so under per-store key scoping there is no principled credential to sign it with. Signing it with some arbitrary store's key would put one store's credential on a request returning data about all one hundred and eighty. Its pagination behaviour is also undocumented. |
| `GET /v1/stores/{id}` | Called internally for the store's timezone. Its name and address change no decision and are customer identifying, so nothing from it reaches a model. |
| `GET /v1/stores/{id}/inventory` | Called internally. Exposed raw it would be a thin proxy inviting the model to do the arithmetic itself. |
| `GET /v1/stores/{id}/pos` | Called internally. It returns till transactions carrying basket, loyalty, payment and staff detail. Only two integers, the unit total and the row count, cross the boundary. |
| `GET /v1/skus/{sku}` | Called internally for the display name. As a tool it would be a catalogue browsing surface over eighteen thousand products with no store context. |
| `GET /v1/suppliers/{id}` | Called internally. Lead time is returned as context and never enters the trigger arithmetic; exposed as its own tool it invites a model to reason that a long lead time justifies ordering early, which would be a caller modifying a stated rule. |

### Shapes and naming

Every quantity field carries its unit in its name: `on_hand_units`,
`pos_units_sold_24h`, `gap_units`, `order_quantity_units`,
`replenishment_threshold_units`. Grocery replenishment is often placed in cases
and the product name embeds a weight, so a bare `quantity` is how an order comes
out wrong by a case multiple. No conversion happens anywhere.

Every response carries the threshold that was applied and an `explanation`
holding the arithmetic in one plain English sentence. The same sentence goes into
the audit trail, so what the buyer reads the next morning and what the agent
reported are the same words, and a divergence between them is a bug anybody can
see.

Every response and every error carries a `correlation_id`. A buyer can hand an
engineer that one string, and it appears on every diagnostic line for the call.

### Observability, for two different readers

A structured record per upstream call for an engineer debugging late at night:
correlation identifier, method, path without its query string, status, duration,
attempt number, the outcome, and the **name** of the secret used, never its
value. A separate append only audit trail for the buyer the next morning, in
plain English, recording what was checked, the arithmetic behind the decision,
what was ordered, and whether the order was newly created or a replay of one
already placed.

### Credentials

One key per store, read from the mounted secrets directory as
`korral_store_key_{store_id}`. The file is re-read on every access, so Korral's
weekly rotation is picked up with no restart. A store this server holds no key
for fails before any network call is made, naming only the store the caller
itself supplied and never enumerating which stores are configured. On a rejected
credential the key is re-read and compared: a read is retried once if the key
changed underneath it, and the write is never retried, because a blind retry
across a rotation can place a second real order against Korral's supplier.

## Running it

Full instructions, including the container path and how to roll back, are in
[DEPLOYMENT.md](DEPLOYMENT.md). The short version:

<!-- verify -->
```bash
uv sync --all-extras
uv run pytest -q
```

Start the whole stack, which is a server plus a stand-in for the customer's
upstream system:

<!-- verify: skip -->
```bash
make setup
make up
scripts/smoke.sh
```

That second block is marked as unverified here because it needs a Docker daemon.
It runs on every push in continuous integration, which builds the image and
exercises the running stack rather than trusting that it would work.

## What is in the box

| Module | What it does |
| --- | --- |
| `config.py` | Validated settings from the environment. No secrets live here. |
| `secrets_provider.py` | Reads credentials so that rotation takes effect with no restart. |
| `log.py` | Structured JSON logging that cannot emit a registered secret. |
| `health.py` | Liveness and readiness kept apart, deliberately. |
| `idempotency.py` | Replay handling whose outcome survives to the reporting layer. |
| `audit.py` | An append-only trail that is tested to actually write. |
| `clock.py` | Injectable time, so no test ever sleeps. |
| `errors.py` | Typed errors with messages that are safe to return to a caller. |

Domain logic written against the task brief lives in `domain/`.

## Four decisions worth explaining

**Secrets are read from a mounted directory, never a mounted file.** Bind
mounting a single file pins its inode inside the container. When a secret
manager rotates a credential it writes a new file and renames it over the old
one, so a process watching the original inode never sees the change and serves a
stale credential indefinitely while reporting itself perfectly healthy. Mounting
the directory and re-resolving the path on every read makes the rotation
visible. This is covered by `tests/test_secrets_rotation.py` and demonstrated
against the running stack by `scripts/smoke.sh`.

**Liveness and readiness are separate endpoints.** Liveness asks whether the
process is broken beyond recovery, and a failure restarts the container.
Readiness asks whether traffic should arrive right now. A credential file that
becomes briefly unreadable while the service is still serving on its last known
good value is *degraded*, not unhealthy: reporting it as unhealthy would restart
a container that is working correctly and turn a transient blip into an outage.

**A replayed write is flagged all the way to the reporting layer.** Preventing
the duplicate write is the easy half. If the replay flag is dropped before
whatever counts the totals, a retried order is counted as a second purchase and
the number a human reads is wrong. `OperationResult.counts_towards_totals`
exists so that cannot happen silently.

**Documentation is executed, not trusted.** Every shell block marked
`<!-- verify -->` in this repository is run by `tools/doc_verifier.py`, locally
and in continuous integration. A documented command that stops working fails the
build. Anything that genuinely cannot be checked is marked as skipped and
reported as unverified rather than quietly presented as working.

## What was deliberately not built

Scope discipline is a decision, not an omission, so it is written down. The
current list lives in `docs/06-assumptions-and-risks.md` under "Deferred".

The largest one in the scaffold itself: the idempotency store is process-local,
which is correct for a single instance and wrong for a horizontally scaled
deployment. That needs shared state, it is a genuine limitation, and it is
recorded rather than hidden.

## Development

<!-- verify -->
```bash
uv run ruff check .
uv run mypy
uv run python -m tools.prose_guard README.md DEPLOYMENT.md CLAUDE.md
```

| Command | What it does |
| --- | --- |
| `make setup` | Install dependencies and git hooks. Run once. |
| `make test` | Fast suite. Stays under five seconds by construction. |
| `make lint` | Format, lint, types, and check that the documentation reads as English. |
| `make sec` | Secret scan, static analysis, dependency audit. |
| `make verify` | Everything, one verdict. Run before every push. |

`make verify` writes what it observed into `docs/05-verification.md`. That file
is written by scripts and never by hand, which is what makes it evidence rather
than a claim.

## Provenance

This repository was prepared before the exercise brief was opened. It carries a
personal engineering scaffold: tooling, quality gates, agent definitions, and
the infrastructure modules listed above. Every line of task-specific code was
written during the recorded hour. The commit tagged `pre-brief` marks the
boundary, so the split is auditable rather than something you have to take on
trust. See [docs/00-scaffold-provenance.md](docs/00-scaffold-provenance.md).
