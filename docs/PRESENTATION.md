# Walkthrough

> **Written as you go.** Append a paragraph after each slice. Thirty seconds
> then costs nothing; writing this from scratch at minute fifty costs the
> walkthrough. `scripts/walkthrough.sh` rehearses the demonstration and prints
> this with real numbers filled in.

## 0:00 — The problem (45 seconds)

Whose job is this? What does their day look like without it, and what decision
do they make, how often?

Name the person, not the system. A chief technology officer has heard a hundred
descriptions of software. They have heard far fewer accurate descriptions of a
customer's afternoon.

## 0:45 — The demonstration (90 seconds)

`scripts/demo.sh`. Every command in it already passed during verification.

Show the thing working. Do not show the code.

## 2:15 — Decisions and trade-offs (90 seconds)

The four that matter:

1. **Why the tools match the job rather than the upstream interface.** Mirroring
   an API produces a large surface and forces the assistant to orchestrate,
   which is where mistakes come from.
2. **Why the calculations sit on the server.** Deterministic and unit tested. A
   model applying a threshold gets it wrong eventually, quietly.
3. **Where the brief was read differently from its literal wording, and why.**
   This is the part that demonstrates judgement rather than compliance.
4. **What was deliberately not built.** Scope discipline, stated as a decision.

## 3:45 — Security, deployment, ownership (45 seconds)

- Where customer data goes, **including what reaches the assistant's context**,
  which is a real export path whether or not it looks like one.
- How a credential is rotated, and how that was proven rather than assumed.
- What the customer owns, what we own, and how to roll back.

## 4:30 — Gaps and next steps (30 seconds)

State them plainly. A reviewer finds them anyway, and finding them first is the
stronger position.

## The line about the scaffold

Say it, unprompted:

> "This repository already had my standard engineering scaffold in it before I
> opened the brief. It is tagged `pre-brief`, so you can see exactly where it
> ends and where this hour's work begins."

---

## Slice notes

> Appended as you build. One short paragraph per slice: what it does, and why it
> is built this way.
