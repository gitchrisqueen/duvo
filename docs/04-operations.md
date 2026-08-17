# Operations

How this is run, rotated, rolled back, and eventually handed over.

## Ownership

The test applied throughout: can the customer operate this without us? Anywhere
the answer is no, that is named as a gap rather than left implicit.

| Area | Customer owns | We own | Handover |
| --- | --- | --- | --- |
| Container platform | Yes | No | Already theirs |
| Credentials and rotation | Yes | No | Runbook below |
| Upstream system access | Yes | No | Already theirs |
| Server configuration | Shared | Shared | Documented in `DEPLOYMENT.md` |
| Business rules in code | No | Yes | Change requires a release |
| Tool interface design | No | Yes | Change requires a release |
| Incident response | Yes, first line | Second line | Runbook below |

The two rows where we retain ownership are the two that encode judgement about
the customer's process. Handing those over without a release cycle would mean
making the business rules editable, which reintroduces exactly the defect this
design avoids.

## First day checklist

In priority order. The first three are blocking.

1. Confirm the upstream base URL and that the network path to it is open.
2. Place the credential in the secrets **directory**, not as a mounted file, and
   confirm the service reaches readiness.
3. Run the smoke test against the customer's environment. Do not accept a green
   deployment without it.
4. Agree what reaches the assistant's context, with the customer's security
   team. See `03-security.md`. This changes the tool interface, so it is settled
   before rather than after.
5. Confirm where the audit trail is shipped and who reads it.
6. Walk one operator through a credential rotation, with them driving.
7. Agree the escalation path and what the customer handles alone.
8. Set the review date for the business rules encoded in the service.

## Runbook: rotating a credential

No restart and no downtime.

1. Write the new value to a temporary file inside the secrets directory.
2. Rename it over the existing file. Renaming is what a secret manager does, and
   it is what a naive implementation fails to notice.
3. The next request uses the new value.
4. Confirm with `scripts/smoke.sh`, which performs this exact rotation and
   asserts that the new credential is accepted and the old one stops working.

```bash
printf '%s' "$NEW_KEY" > secrets/.upstream_api_key.new
mv secrets/.upstream_api_key.new secrets/upstream_api_key
scripts/smoke.sh
```

**The failure this prevents.** Mounting the individual secret file into the
container pins its inode. The rename creates a new inode, the container keeps
the old one, and the service serves the previous credential indefinitely while
reporting itself perfectly healthy. It was found by writing this runbook and
then actually executing it, which is the argument for writing runbooks as
executable procedures rather than as prose.

## Runbook: the service reports not ready

1. Read the payload: `docker compose exec server python -m duvo_fde health`.
2. Inspect the `checks` object. Each entry is `ok`, `degraded`, or `failed`.
3. `failed` on a secret means it has never been readable. Check the mount path
   and the filename, which must match the secret name exactly.
4. `degraded` is not an incident. The service is answering correctly on its last
   known good value. Investigate the source, but do not restart: restarting
   discards the working value and turns a recoverable state into an outage.
5. Liveness stays green throughout a degraded state, by design.

## Runbook: rolling back

```bash
docker compose down
docker compose up --detach --wait
```

- **Recovery time:** one container start, a few seconds.
- **Data loss:** none. No request state is designed to survive a restart.
- **In flight requests:** fail and are retried by the caller. The idempotency
  key means a retry cannot duplicate a write.
- **The caveat:** the idempotency store is in memory, so a restart clears it. A
  retry that spans a restart is not deduplicated. This is recorded in
  `06-assumptions-and-risks.md` and is the first thing to fix for production.

## What degrades first

| Failure | What the operator sees | What the caller sees |
| --- | --- | --- |
| Upstream slow | Readiness degraded | Timeout, typed error |
| Upstream down | Readiness not ready | Typed upstream error |
| Credential unreadable | Readiness degraded, warning logged | Nothing; still served |
| Credential never present | Readiness not ready | Typed configuration error |
| Disk full | Audit writes fail | Nothing; the request path is unaffected |

## Token reduction, and why documentation is exempt

Agent runs use a token reduction tool so that a long session stays affordable.
It compresses command output and code generation exchanges. It has one hard
boundary: **it never touches documentation.**

Every Markdown file here is read by a reviewer and later presented to company
leadership. Compressed prose in a document is a defect, and relying on somebody
remembering to switch a mode off is not a control. Five independent guards
enforce this, and no human action is required by any of them:

1. `caveman.config.json` excludes every prose path from every transform.
2. The `shrink` helper wraps a command so its *output* is smaller. It is never
   applied to file contents. `scripts/lint.sh` enforces this on the scripts.
3. A pre-write hook forces compression off for any documentation write and
   restates the rule.
4. `tools/prose_guard.py` runs after every documentation write, in the full
   verification sweep, and at commit time. It rejects telegraphic prose using
   article density, sentence length, and verbless sentence ratio.
5. Continuous integration runs the same guard across all documentation, so a
   compressed document fails the build.

The guard is proven rather than assumed. `tests/test_prose_guard.py` points it
at a deliberately compressed fixture and asserts it is rejected, and continuous
integration fails if the guard ever accepts that fixture. Setting
`CAVEMAN_DISABLE=1` removes the tool from every script with no other change.
