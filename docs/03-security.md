# Security and data boundaries

## The path that is easy to miss

A tool server can be perfectly secured and still export customer data, because
**whatever the server returns to an assistant enters that assistant's context
and is sent to whoever hosts the model.**

That is a real data export. It happens on every call, it does not appear in a
network diagram, and it is not addressed by hosting the server inside the
customer's tenant. If a requirement says customer data must not leave the
tenant, this path either satisfies it or breaks it, and the answer depends
entirely on what the tools return.

Three mitigations, in order of preference:

1. **Return identifiers and aggregates rather than records.** The assistant needs
   to know that three locations require replenishment, not the full row for each
   one. This is a technical control, it costs nothing, and it is decided by the
   shape of the tool interface rather than bolted on afterwards.
2. **Run the model inside the tenant.** Many enterprise customers already do.
   This is a technical control and it is the customer's decision, not ours.
3. **Accept the flow under a data processing agreement.** This is a
   *contractual* control, not a technical one. It is a legitimate answer, and it
   must be labelled honestly, because a customer's security team will ask which
   of the two it is and will notice if the answer is blurred.

Settle this with the customer's technology team before implementation. It
changes the tool interface rather than sitting on top of it, so discovering it
late is expensive.

## Trust boundaries

| Boundary | What crosses it | Control |
| --- | --- | --- |
| Assistant to server | Tool calls and their results | Typed schemas, boundary validation |
| Server to upstream | Authenticated requests | Credential from the mounted secrets directory |
| Server to logs | Structured records | Redaction filter, secret registry |
| Server to audit trail | Actor, action, target, outcome | Append only, redacted |
| **Server to model context** | **Whatever a tool returns** | **Decided by tool design. See above.** |

## Secrets

Read through `SecretsProvider`, never through configuration and never baked into
an image.

- The **directory** is mounted, not the individual file. Mounting a file pins its
  inode, so a rotation performed by rename is never observed, and the service
  serves a stale credential while reporting itself healthy. This is covered in
  `DEPLOYMENT.md` and tested in `tests/test_secrets_rotation.py`.
- Values are registered with the redaction filter the moment they are read,
  including after a rotation, so a newly rotated credential is protected from
  logs immediately.
- A credential that becomes temporarily unreadable leaves the service running on
  its last known good value, reported as degraded rather than failed.
- `tests/test_redaction.py` asserts that a registered secret cannot appear in a
  log message, in an interpolated argument, in a structured field, in a nested
  structure, or in exception text.

## Input validation

Everything is rejected at the boundary with a typed error from
`duvo_fde.errors`, before any upstream call:

- Unknown identifiers, rather than passing them through and failing upstream.
- Negative and zero quantities.
- Missing required fields.
- Malformed payloads.

A caller-facing error carries a stable code and a message written for an
external audience. Internal detail stays in `details` and is only ever emitted
through the redacting logger.

## Business rules are not parameters

A rule stated in the brief is a module constant. It is never a function
argument, a configuration value, or a tool parameter, because anything a caller
can pass is something an assistant can be persuaded to change. This is a defect
class, not a style preference, and `code-reviewer` and `adversarial-reviewer`
both check for it explicitly.

## Container hardening

- Runs as an unprivileged user with a fixed identifier.
- Read-only root filesystem, with a writable temporary filesystem only.
- All Linux capabilities dropped, and privilege escalation disabled.
- No build tooling in the runtime image; it is a separate stage.
- Dependencies installed from a committed lock file.
- Base images pinned by digest, written by `scripts/pin_base_images.sh` rather
  than typed by hand.
- The secrets mount is read only. The service never writes a credential.

## Tooling, stated honestly

| Tool | Where it runs | Speed |
| --- | --- | --- |
| gitleaks | Commit, push, and continuous integration | Under a second, offline |
| detect-secrets | Local sweep | Seconds |
| GitGuardian | Continuous integration, when a key is present | Seconds |
| bandit | Local sweep and continuous integration | Seconds |
| semgrep | Local sweep, when installed | Seconds |
| pip-audit | Local sweep and continuous integration | Seconds |
| **CodeQL** | **Continuous integration, and optionally in the background locally** | **Minutes, not seconds** |

CodeQL is worth running and it is not fast. Building a Python database takes
minutes, so describing it as a quick local check would be untrue, and this
repository does not make claims it cannot support. Locally, semgrep and bandit
are the fast equivalents. `scripts/codeql.sh` exists for a background run
against a database prepared ahead of time.

A scan that could not run is reported as skipped, never as passing. GitGuardian
is guarded so that a missing key skips it rather than failing the build, because
a scan that did not happen is not a finding either way.

## What is deliberately not addressed

Recorded here rather than left for a reviewer to find:

- **Authentication of the assistant to the server.** Assumed to be handled by
  the deployment environment. If it is not, that is a gap and it is a real one.
- **Rate limiting.** No protection against a caller in a loop.
- **Multi-tenant isolation.** This runs as a single tenant deployment.
- **Idempotency across restarts or replicas.** The store is in memory and
  process local, so a retry spanning a restart is not deduplicated.
