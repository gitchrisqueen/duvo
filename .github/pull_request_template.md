## What this changes

<!-- One paragraph. What a reviewer gets that they did not have before. -->

## Requirements covered

<!-- Requirement identifiers from docs/00-brief-analysis.md, for example R1, R4. -->

## Decisions and trade-offs

<!--
Why this shape rather than another. Include anywhere the brief was read
differently from its literal wording, and why that reading is safer.
-->

## What was deliberately not built

<!-- Naming this is a strength. Scope discipline is visible here. -->

## Verification

Evidence is written by scripts into `docs/05-verification.md`. Nothing below is
ticked unless a command produced it.

- [ ] `scripts/test.sh` — fast suite green, under five seconds
- [ ] `scripts/lint.sh` — formatting, types, compression scope, documentation prose
- [ ] `scripts/security.sh` — secret scan and static analysis
- [ ] `scripts/docker_build.sh` — the image a reviewer will build
- [ ] `scripts/compose_up.sh` — the stack reaches health
- [ ] `scripts/smoke.sh` — every tool exercised end to end
- [ ] `scripts/verify_docs.sh` — every documented command executed

Anything not verified:

<!-- List it here rather than leaving a box unticked with no explanation. -->

## Known gaps

<!--
State them plainly. A reviewer finds them anyway, and finding them first is the
stronger position.
-->
