# Instructions for GitHub Copilot

## What this repository is

A tool server built during a one hour Forward Deployed Engineer exercise. An
assistant calls its tools on behalf of a business user, and the server does the
work against an upstream system. The submission is reviewed by a chief
technology officer, so correctness, honesty, and operational readiness matter
more than volume.

Stack: Python 3.12, `uv`, pydantic, pytest, ruff, mypy in strict mode, Docker
and Compose.

## Rules that are not negotiable

1. **Business logic lives on the server.** Calculations and rules are
   deterministic Python, unit tested. Never delegate arithmetic or a threshold
   to a language model. A model applying a rule will eventually get it wrong on
   one input in a hundred, silently, and nobody will notice.
2. **A fixed business rule is a constant, never a parameter.** If a rule is
   stated in the brief, a caller must not be able to override it. A rule
   appearing as a function argument or a tool parameter is a defect.
3. **Validate at the boundary.** Unknown identifiers, negative or zero
   quantities, malformed payloads, and missing fields are rejected with a typed
   error from `duvo_fde.errors` before anything else runs.
4. **Only read fields the upstream actually returns.** Check
   `fixtures/upstream.json`. Reading an invented field is the most common way a
   demonstration that works locally fails on real data.
5. **Preserve the outcome, not just the payload.** Pass `OperationResult`
   onwards. Unwrapping the response and discarding the replay flag causes
   reported totals to count a retry as a second purchase.
6. **Secrets never reach logs, errors, images, or git.** Read them through
   `SecretsProvider`. Never put a credential in configuration, an error message
   returned to a caller, or a container image.
7. **Liveness and readiness are separate questions.** A dependency that is
   degraded but still serving is reported as degraded, and stays in service.
   Failing a health check there causes an orchestrator to restart a container
   that is working correctly.
8. **Never claim something works without running it.** This applies to code
   comments, documentation, and pull request descriptions alike.

## Documentation

Every Markdown file here is read by a human reviewer and later presented to
company leadership. Write documentation in full, clear English, always. Token
compression applies to code and command output only and never to prose;
`tools/prose_guard.py` fails the build on compressed documentation.

Any shell command in documentation must carry a `<!-- verify -->` marker above
its code fence so that `tools/doc_verifier.py` executes it in continuous
integration. If a command cannot be verified, mark it `<!-- verify: skip -->`,
which reports it as unverified rather than hiding it.

## Style

- Google-style docstrings on every public function and class, with `Args`,
  `Returns`, and `Raises`.
- Full type annotations. `mypy --strict` must pass.
- Comments explain why, never what.
- Tests are named as sentences describing behaviour, not after the function.
- No network, no `time.sleep`, and no wall-clock dependency in unit tests. Use
  `FrozenClock` from `duvo_fde.clock`. The whole suite stays under five seconds.

## Reuse before writing

`src/duvo_fde/` already provides configuration, secret rotation, redacting
structured logs, split health endpoints, idempotent writes, an audit trail, an
injectable clock, and typed errors. Read it before adding anything. New
infrastructure in a one hour exercise is almost always a mistake.

## When reviewing a pull request

Prioritise, in this order: correctness defects, reads of fields that may not
exist, missing boundary validation, business rules a caller can change, outcome
information dropped before reporting, and secret exposure. Skip style comments;
`ruff` and `mypy` already run in continuous integration and repeating them
wastes the reviewer's attention.

Be specific. Name the file, the line, what goes wrong, and what to do about it.
If you are not certain something is a defect, say so rather than presenting a
suspicion as a finding.
