# Deployment

Everything a reviewer or an operator needs to run this, change a credential, and
roll it back.

Commands marked `<!-- verify -->` in this file are executed by
`tools/doc_verifier.py` on every push. A command that stops working fails the
build. Commands that genuinely cannot be checked in continuous integration are
marked as skipped and are reported as unverified rather than presented as
working, so you always know which is which.

## Requirements

- Docker with Compose, for the container path.
- Or Python 3.12 and [uv](https://docs.astral.sh/uv/), for the direct path.

Both paths are supported deliberately. If Docker is unavailable or misbehaving,
the service still runs, and the deliverable does not depend on a single tool
working on the day.

## First run

<!-- verify: skip -->
```bash
git clone https://github.com/gitchrisqueen/duvo.git
cd duvo
make setup
```

`make setup` installs dependencies, installs the git hooks, writes a local
development credential into `secrets/`, and warms the container layer cache.
It is safe to run more than once.

## Running with containers

<!-- verify: skip -->
```bash
make up
docker compose ps
```

This starts two services:

| Service | What it is |
| --- | --- |
| `server` | The tool server. |
| `mock-upstream` | A stand-in for the customer's system, serving `fixtures/upstream.json`. |

`make up` waits for both to report healthy rather than returning immediately, so
a success here means the stack is genuinely serving.

Exercise it end to end:

<!-- verify: skip -->
```bash
scripts/smoke.sh
```

Stop it and remove its volumes:

<!-- verify: skip -->
```bash
make down
```

## Running without containers

<!-- verify -->
```bash
uv sync --all-extras
uv run python -m duvo_fde config
uv run python -m duvo_fde health
```

`config` prints the resolved settings, which contain no secret values by design.
`health` prints both health payloads and exits non-zero when the service is not
ready, which is what the container health check uses.

## Configuration

Every setting is read from the environment with a `DUVO_` prefix. See
`.env.example` for a working starting point.

| Variable | Default | What it does |
| --- | --- | --- |
| `DUVO_SECRETS_DIR` | `./secrets` | Directory holding one file per secret. |
| `DUVO_UPSTREAM_BASE_URL` | `http://localhost:8080` | The upstream system. |
| `DUVO_UPSTREAM_TIMEOUT_SECONDS` | `10.0` | Per-request timeout. |
| `DUVO_LOG_FORMAT` | `json` | `json` for aggregation, `console` for development. |
| `DUVO_LOG_LEVEL` | `INFO` | Standard level names. |
| `DUVO_AUDIT_LOG_PATH` | `./audit.log` | Audit trail. Empty disables the file. |

No credential is ever a configuration value. Secrets are read through the
secrets provider so that rotation works without a restart.

## Secrets, and why the directory is mounted rather than the file

Each secret is a single file inside `DUVO_SECRETS_DIR`, and the filename is the
secret name.

**Mount the directory. Never mount an individual secret file.** This is not a
style preference. Bind mounting a single file pins its inode inside the
container. A secret manager rotating a credential writes a new file and renames
it over the old one, which produces a new inode, so a container with the old
file mounted never observes the change. The service then serves a stale
credential indefinitely while reporting itself perfectly healthy, which is the
worst possible combination.

`docker-compose.yml` mounts `./secrets` as a directory, read only. The provider
re-resolves the path and compares identity on every read, so a rename, an
in-place write, and a symlink swap are all detected.

## Rotating a credential

No restart, no downtime, no coordination.

<!-- verify: skip -->
```bash
# Write the new value beside the old one, then rename it into place. This is
# what a secret manager does, and it is the case a naive implementation misses.
printf '%s' "$NEW_KEY" > secrets/.upstream_api_key.new
mv secrets/.upstream_api_key.new secrets/upstream_api_key

# The next request uses the new value. Confirm it.
scripts/smoke.sh
```

`scripts/smoke.sh` performs exactly this rotation against the running stack and
asserts that the new credential is accepted, that the previous one stops
working, and that the original works again once restored.

If a credential file becomes temporarily unreadable, the service keeps working
on the last value it read successfully and reports itself **degraded** through
readiness. It does not fail. Failing there would cause an orchestrator to
restart a container that is serving correctly.

## Health

Two endpoints, answering two different questions.

| Check | Question | On failure |
| --- | --- | --- |
| Liveness | Is the process broken beyond recovery? | Restart the container. |
| Readiness | Should traffic arrive right now? | Remove from rotation, keep running. |

Readiness reports three states: `ready`, `degraded`, and `not_ready`. Degraded
means a dependency is impaired but the service is still answering correctly, and
it stays in service. Only `not_ready` removes it.

<!-- verify -->
```bash
uv run python -m duvo_fde health
```

## Rollback

The image is immutable and tagged, so rolling back is redeploying the previous
tag. Nothing in this service writes persistent state that a rollback would
strand, except the audit log, which is append only and safe to keep.

<!-- verify: skip -->
```bash
docker compose down
docker compose up --detach --wait
```

Recovery time is one container start, which is a few seconds. Nothing is lost,
because no request state survives a restart by design. An in-flight request
fails and is retried by the caller, and the idempotency key means a retry cannot
duplicate a write.

The one caveat, stated plainly: the idempotency store is in memory and process
local. A restart clears it, so a retry that spans a restart is not deduplicated,
and a horizontally scaled deployment needs shared state. This is a real
limitation and it is recorded in `docs/06-assumptions-and-risks.md` rather than
left for a reviewer to discover.

## Ownership

Who owns what after handover is set out in `docs/04-operations.md`, along with a
first-day checklist. The test applied there is whether the customer can operate
this without us.

## Verifying a deployment

<!-- verify -->
```bash
scripts/check_prose.sh
scripts/verify_docs.sh
```

The full sweep, which additionally builds the image, starts the stack, and runs
the smoke test:

<!-- verify: skip -->
```bash
make verify
```

Results are appended to `docs/05-verification.md` by the scripts themselves.
That file is never edited by hand, which is what makes it evidence rather than a
claim.

## Troubleshooting

**The stack will not start.** Check that `secrets/upstream_api_key` exists;
`make setup` creates it. Then read the logs with
`docker compose logs --tail 50`.

**The server reports not ready.** Run `uv run python -m duvo_fde health` and read
the `checks` object. A secret reporting `failed` has never been readable, which
usually means the mount path is wrong.

**A rotation did not take effect.** Confirm the directory is mounted rather than
the individual file. This is the failure this design exists to prevent, and a
file mount is the only way to reintroduce it.

**The image will not build.** Run `scripts/docker_build.sh` on its own to see
the full output. Continuous integration builds the same image on every push, so
comparing against a recent green run isolates whether the problem is local.
