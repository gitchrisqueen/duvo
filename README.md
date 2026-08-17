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
| Branch | `claude/interview-project-setup-541dyg` |
| Commit | `ce94d93` |
| Tests | 83 |
| Coverage | 84% |
| Last verified | 2026-08-17T17:57:30Z |

This table is written by `scripts/update_readme.sh` from what actually ran. It
is never edited by hand.
<!-- END:status -->

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
