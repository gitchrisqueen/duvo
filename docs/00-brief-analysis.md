# Brief analysis

> **Template.** This is filled in during the first eight minutes, before any
> code is written. Requirement identifiers assigned here are used for the rest
> of the session, in commit messages, in the pull request, and in the
> walkthrough.

## Requirements

Separate what the brief states from what it assumes. An implied requirement is
still a requirement, but it is one we chose to read into the text, and saying so
is the difference between analysis and guessing.

| ID | Requirement (quote the brief) | Kind | Our reading | Confidence |
| --- | --- | --- | --- | --- |
| R1 | | explicit | | |
| R2 | | implied | | |

## Traps and contradictions

**This section is never empty.** If nothing is found, write "None found" and
list what was checked, because the check itself is the evidence.

For each finding: the concern, the evidence in the brief, the resolution, and
why the resolution does not violate anything the brief states.

### Checked for

1. An upstream recommendation or default that conflicts with a stated business
   rule.
2. A fixed business rule that the interface invites a caller to override.
3. A requirement whose literal implementation moves customer data somewhere it
   should not go, including into a model's context.
4. Duplicate submissions, retries, and idempotency.
5. Unknown, malformed, or out-of-range identifiers and quantities.
6. Credential lifecycle: rotation, revocation, and mid-request behaviour.
7. Timezone, trading hours, and calendar arithmetic.
8. Unit mismatches between cases and units, currency, or time periods.
9. Pagination, partial data, and upstream failure semantics.
10. Health, restart, and rollback behaviour under partial degradation.

### Findings

| # | Concern | Evidence | Resolution | Why this does not break the brief |
| --- | --- | --- | --- | --- |

## Assumptions

| ID | Assumption | Why it is needed | What changes if it is wrong |
| --- | --- | --- | --- |

## Data flow

Where customer data comes from, what the server holds, what it returns, and what
reaches a model's context. That last path is a real export of customer data
whether or not the brief describes it that way, so it is drawn explicitly here
rather than left implicit.

## Reference material match

A percentage and one sentence of reasoning. Below seventy per cent, the local
reference material is ignored for the rest of the session and that decision is
recorded here.
