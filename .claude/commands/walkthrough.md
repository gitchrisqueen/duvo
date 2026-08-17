---
description: Rehearse and then deliver the five minute closing walkthrough
---

Run `scripts/walkthrough.sh` first. It rehearses every demonstration command
headlessly and prints the script with real numbers filled in.

Deliver it in this shape:

- **Forty five seconds, the problem.** Whose job this is and what their day
  looks like without it. Name the person, not the system.
- **Ninety seconds, the demonstration.** `scripts/demo.sh`. Show it working.
- **Ninety seconds, the decisions.** Why the tools match the job rather than the
  upstream interface. Why the calculations sit on the server and never in the
  model. Where you disagreed with the brief and why your reading is safer. What
  you deliberately did not build.
- **Forty five seconds, the operational picture.** Where customer data goes,
  including what reaches a model's context. How a credential is rotated and how
  you proved it. What the customer owns and how to roll back.
- **Thirty seconds, the gaps.** State them plainly. A reviewer finds them
  anyway, and finding them yourself is the stronger position.

Say the scaffold out loud: the repository was prepared before the brief was
opened, and every task-specific line was written during this hour. The
`pre-brief` tag makes that auditable.

$ARGUMENTS
