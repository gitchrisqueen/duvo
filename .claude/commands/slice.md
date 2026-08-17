---
description: Build one vertical slice from the locked plan, with tests and a commit
---

Build exactly one slice. If an idea arrives that is not in this slice, it goes
into the deferred list in `docs/06-assumptions-and-risks.md` and is not built.

1. State which slice and which requirement identifiers it satisfies.
2. Invoke `implementer` for the code.
3. Invoke `unit-tester` for the tests. The suite stays under five seconds.
4. Run `scripts/test.sh` and read the real output.
5. Append one paragraph to `docs/PRESENTATION.md` covering what this slice does
   and why it is built this way. Writing this now costs thirty seconds; writing
   it at minute fifty costs the walkthrough.
6. Commit with `scripts/commit.sh "feat(scope): what changed"`.

Stop after the commit. Do not begin the next slice in the same turn.

Time check: building ends at minute thirty eight, whatever state it is in.

$ARGUMENTS
