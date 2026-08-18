# Provenance of this repository

## What was prepared in advance

This repository was set up before the exercise brief was opened. It carries a
personal engineering scaffold that I bring to any project:

- Project configuration, linting, type checking, and test setup.
- A container build ordered so that only changed layers rebuild.
- Continuous integration covering quality, security, and documentation.
- Assistant agent definitions and quality gates.
- Shell scripts wrapping the commands I run repeatedly.
- Infrastructure modules that every integration server needs regardless of its
  domain: configuration, secret rotation, redacting logs, health endpoints,
  idempotent writes, an audit trail, an injectable clock, and typed errors.

None of it is specific to the task. `src/duvo_fde/domain/`, where the task
itself lives, was deliberately left empty.

## What was written during the recorded hour

Every line of task-specific code, every test covering it, and every document
describing it. The commit tagged `pre-brief` marks the boundary exactly:

<!-- verify: skip -->
```bash
git log --oneline pre-brief..HEAD
git diff --stat pre-brief..HEAD
```

## Why this is stated up front

Two reasons, and the second matters more than the first.

The first is fairness. A reviewer inspecting the commit history should not have
to work out which parts predate the brief. The tag makes it a single command.

The second is that hiding it would be the same failure this exercise is designed
to catch. A submission that quietly presents prepared work as though it were
produced under time pressure is making an unverified claim, which is precisely
the thing this repository spends considerable effort preventing everywhere else.
Stating it plainly costs nothing and is consistent with how everything else here
is documented.

## What the gates caught while this was being built

Worth recording, because it is the argument for the gates existing at all. Four
real defects were found in the scaffold itself before any human looked at it,
and none of them would have been visible from reading the code.

1. **A test that passed locally and failed in continuous integration.** The
   provider reported a credential file as healthy after read access was lost,
   because the file's identity had not changed so it was never re-read. The
   local run was as root, and root can read a file whatever its mode, so the
   test was skipped. The next rotation would have failed silently, which is the
   exact problem the module exists to prevent. Both the code and the test were
   corrected, and the new test fakes read access instead of relying on file
   permissions so that it holds for any user.

2. **A container stack that could not start.** The images built correctly, and
   the server exited immediately because the placeholder entry point printed a
   message and returned. `docker compose up --wait` fails on a container that is
   already gone. The placeholder now stays alive and reports its state honestly.

3. **A smoke test that broke outside a development environment.** A shell helper
   fell back to `python -m python` when `uv` was absent, which is precisely the
   situation in the container job. Found only because the smoke test runs where
   a reviewer would run it, not only where it was written.

4. **A broken pipe in the same smoke test.** Reading only the status line by
   piping into `head -1` closed the pipe underneath the process still writing the
   body. Found by running the script against a live upstream rather than reading
   it.

The first three were found by continuous integration. The fourth was found by
executing the script. Not one of them would have been caught by review.

## Is preparation reasonable?

I think so, and it is worth saying why rather than assuming agreement.

An hour is not enough time to build a production-shaped service *and* decide on
a linter configuration, remember a container layer ordering, and reconstruct a
health check design. Preparing the parts that are the same on every project is
what lets the hour be spent on the parts that are not: understanding the brief,
finding what it gets wrong, building the domain, and verifying it.

This is also how the role works in practice. A forward deployed engineer arriving
at a customer does not start from an empty directory. They arrive with tooling
and patterns, and the value they add is judgement about the customer's actual
problem.

If the exercise intends a genuinely empty starting point, the tag makes it
straightforward to review only what came after it.
