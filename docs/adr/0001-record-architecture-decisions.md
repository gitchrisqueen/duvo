# 1. Record architecture decisions

Status: accepted

## Context

An hour of building produces a dozen decisions with real trade-offs. In a
walkthrough there is time to explain three of them. A reviewer reading the
repository afterwards, or a colleague inheriting it, sees the outcome of all
twelve and none of the reasoning.

The expensive failure is not a wrong decision. It is a decision whose reasoning
was never recorded, so nobody can tell whether the circumstances that justified
it still hold.

## Decision

Decisions with a genuine trade-off get a short record here: the context, what
was decided, and what it costs.

Decisions without a trade-off do not. A record explaining why the project uses a
formatter is noise, and noise makes the records that matter harder to find.

## Consequences

Writing one costs about two minutes. A record is written when a reasonable
engineer could have chosen differently, and the walkthrough can then reference
the reasoning rather than reconstructing it live.
