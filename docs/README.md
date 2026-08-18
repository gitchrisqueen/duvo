# Documentation

Numbered so that the folder reads in the order the work happened.

| Document | What it answers |
| --- | --- |
| [00-scaffold-provenance](00-scaffold-provenance.md) | What was prepared in advance, and what was written during the hour |
| [00-brief-analysis](00-brief-analysis.md) | What the brief asked for, what it assumed, and where it contradicts itself |
| [01-plan](01-plan.md) | What is being built, in what order, and what is not |
| [02-architecture](02-architecture.md) | Why it is shaped this way |
| [03-security](03-security.md) | Where customer data goes, including into a model's context |
| [04-operations](04-operations.md) | Rotation, rollback, ownership, and the first day |
| [05-verification](05-verification.md) | What has actually been run. Written by scripts, never by hand |
| [06-assumptions-and-risks](06-assumptions-and-risks.md) | What we assumed, what is deferred, what is missing |
| [07-business-impact](07-business-impact.md) | What this is worth, with the arithmetic shown |
| [PRESENTATION](PRESENTATION.md) | The five minute walkthrough |
| [EXEC-SUMMARY](EXEC-SUMMARY.md) | One page for a reader who will never open the code |
| [INTERVIEW-RUNBOOK](INTERVIEW-RUNBOOK.md) | The operating manual for the hour |
| [CHEATSHEET](CHEATSHEET.md) | One printable page |
| [adr/](adr/) | Individual decisions with real trade-offs |

## How to read these

A reviewer with five minutes should read `00-brief-analysis.md` and
`03-security.md`. Those two carry the judgement.

A reviewer with twenty minutes should add `02-architecture.md`,
`04-operations.md`, and `05-verification.md`. The last of those is the one that
says which claims are supported by something that actually ran.

## The rule these all follow

Nothing is claimed unless a command produced it. `05-verification.md` is written
by the scripts themselves, every shell block marked `<!-- verify -->` is executed
in continuous integration, and `doc-truth-auditor` strips anything the evidence
does not support before the final push.

Prose here is written in full English, always, and that is enforced rather than
intended. See `04-operations.md` for the five guards that make it structural.
