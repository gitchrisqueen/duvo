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


## Where this runs, and why it has to run there

Korral's information technology team told us three things that between them
decide the architecture. StoreLink is not reachable from the public internet. No
customer data may leave Korral's Google Cloud tenancy. Updates ship frequently
after go live.

The first of those settles the question on its own: **this server runs inside
Korral's Google Cloud tenancy, on the network that can already reach StoreLink.**
Any design in which Duvo hosted infrastructure calls StoreLink is dead on
arrival, because there is nothing for it to call. Concretely, that means Cloud
Run on the customer's project with serverless virtual private cloud access to
the StoreLink subnet, or a deployment on their existing Google Kubernetes Engine
cluster if they already run one and would rather not add a surface. Either is
fine. What matters is that the process sits inside the perimeter and that no
StoreLink traffic ever crosses it.

**The export boundary is not the network diagram.** Everything a tool returns is
placed into the calling agent's model context, and if that model is hosted
outside Korral's tenancy then every tool response is an export of Korral data no
matter where this container runs. That is why the tools return an aggregated
unit count and a transaction count rather than till transaction rows: no basket,
loyalty, payment, timestamp level or staff detail is ever serialised, so the
minimum that answers the buyer's question is the maximum that crosses. Where the
model runs is the first question on the day one list below, and it has two
acceptable answers.

## How it gets there, and who owns the pipeline

**Duvo owns the pipeline. Korral owns the runtime and the credentials.** That
split is deliberate and it is the one that survives contact with an incident at
eleven at night.

Duvo builds the image in Duvo's continuous integration, runs the full
verification sweep against it, and pushes it to Artifact Registry inside
**Korral's** project. Korral grants Duvo push rights to that one repository and
deploy rights to that one service, and nothing else. Duvo never holds a Korral
StoreLink key and never needs one: keys are written by Korral's information
technology team into the secrets mount, and this server reads them at runtime.

The consequence worth saying out loud: Duvo can ship a fix without a Korral
engineer being awake, and Duvo still cannot read a single StoreLink credential.
Those two properties usually trade against each other, and separating the
artifact's lifecycle from the credential's is what buys both.

## How secrets are handled

One key per store, one file per key, named `korral_store_key_{store_id}`, in a
mounted **directory**. In Google Cloud that is Secret Manager, with each store's
key as its own secret and the whole set projected into the container as a
volume.

The directory is mounted rather than the individual files, and that detail is
load bearing rather than stylistic. Mounting a single file pins its inode inside
the container, so a rotation on the host is never observed by the process and a
key rotation that appears to work silently does not. This is a failure a previous
implementation shipped, and `scripts/smoke.sh` rotates a key by rename against
the running stack specifically to prove this one does not.

The provider re-reads the file on every access, so a weekly rotation is picked up
with **no restart and no redeploy**. Key values are registered with the redacting
logger the moment they are read, so a key cannot reach a log line, an error
payload, or the audit trail even if a bug put it there.

Two failure paths, because Korral's information technology team is judging both:

**A key rotates while a request is in flight.** On a rejected credential this
server re-reads the key and compares it against the one it just sent. If they
differ, the key rotated underneath the request, and a **read** is retried once,
which is free because a read has no side effect. If they are the same, the key is
wrong or revoked, and retrying would produce an identical rejection, so it does
not. A **write is never retried, under any circumstance.** A blind retry across a
rotation can place a second real order against Korral's supplier, so the caller
is told plainly that the order's state is unknown, that nothing was recorded
here, and to confirm the store's outstanding orders in StoreLink before trying
again.

**The agent asks for a store we hold no credential for.** The request fails
before any network call is made, so that store is never queried at all. The error
names only the store the caller itself supplied, gives the exact filename that
would fix it, and never enumerates which stores are configured, so it cannot be
used to probe the rest of the estate. It carries its own error code,
`store_credential_missing`, distinct from an unknown store, because the two have
different owners: a missing credential is Korral's to fix and an unknown store is
the caller's mistake.

One gap, stated rather than hidden: the provider raises only when a secret has
**never** been readable, so a deleted key file keeps serving its last known good
value and reports itself degraded. That is correct for rotation, which is what it
exists for, and wrong for revocation. Revocation is therefore caught at the
StoreLink boundary instead, where a rejected credential produces the error above.

## Shipping a fix at eleven at night

1. Branch, fix, and push. Continuous integration runs lint, types, the suite, the
   security sweep, the image build, the stack, and the smoke test.
2. `make verify` locally if the pipeline is the thing that is broken.
3. Merge. The pipeline builds and pushes the image to Korral's Artifact Registry
   and deploys the new revision.
4. If it is worse, roll back to the previous revision. **Secrets are not in the
   image**, so a rollback never touches a credential and never forces a rotation.
   The previous revision is still holding the same keys it always was.

The realistic worst case is not a bad deploy, it is a network path problem, since
StoreLink is on a private network. That is why liveness and readiness answer
different questions here: an instance serving correctly from a last known good
key reports itself degraded and **stays in service**, rather than being restarted
into a loop.

## What to confirm with Korral's information technology team before day one

Ordered by how much rework the wrong answer causes.

1. **Where does the calling agent's model run?** If it is outside Korral's
   tenancy, every tool response is an export. Two acceptable answers: a model
   served inside Korral's own tenancy, or a written agreement that aggregated,
   non-personal stock figures fall outside Korral's definition of customer data.
2. **Does the replenishment endpoint honour an idempotency key?** This server
   deduplicates successful writes itself, but a write that fails ambiguously
   cannot be made safe from our side of the wire. If StoreLink honours a key,
   that gap closes entirely.
3. **Is a store's key accepted on `/v1/skus/{sku}` and `/v1/suppliers/{id}`?**
   Those paths carry no store, yet every request must carry a per-store key. We
   sign them with the acting store's key. If StoreLink refuses that, those two
   lookups are withdrawn and the product name and lead time leave the responses.
   The ordering decision does not depend on either.
4. **Is the replenishment quantity expressed in units or in cases, and what is
   the case size?** The threshold in the brief is in units, so this server works
   in units and performs no conversion anywhere. If StoreLink expects cases,
   every order is wrong by the case multiple, which is a serious commercial
   error rather than a cosmetic one.
5. **How much should an order be for?** The brief specifies when to order and is
   silent on how much. This server orders the measured gap, which restores
   roughly one day of observed demand and deliberately does not reach for the
   supplier's lead time, because the brief states the trigger as a fixed rule.
   Korral may well want cover for the lead time instead. That is a policy change
   for a buyer to make, and it is one function to change.
6. **What format does the `since` parameter accept?** We send an ISO 8601
   timestamp with an explicit offset. A silently misinterpreted window is worse
   than a rejected one.
7. **Should the transport be standard input and output, or streamable HTTP?**
   The pilot uses standard input and output, where the client launches this
   server as a subprocess. If the agent runs elsewhere in Korral's tenancy it
   needs streamable HTTP instead, which is an argument to `run` rather than a
   rewrite, plus a decision about how the agent authenticates to us.
8. **Is one replica enough?** Deduplication is currently in process. More than
   one replica moves it to shared state.

## Proving the buyer task works

<!-- verify: skip -->
```bash
scripts/demo_proof.sh
```

This starts the mock StoreLink, refuses to continue if anything else is already
holding the port, completes a real protocol handshake, runs the exact instruction
from the brief through the real tools over real HTTP with real per-store
authentication, and asserts every outcome: store 47 orders nineteen units, store
102 is refused at exactly the threshold, a retry is deduplicated, an unknown
store fails closed, and a malformed identifier is rejected. It then prints the
audit trail and checks that neither store key appears anywhere in it. It is
marked as unverified above only because it binds a port, which continuous
integration already covers through the container job.

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
