# Executive summary

One page. No jargon. Written for someone who will never open the code.

## What this does

A Korral category buyer can now ask an assistant, in ordinary language, whether
a product is about to run out at a given store, and have the replenishment order
raised for them when Korral's rule says it should be. The buyer describes the
job; the software makes the decision and records what it did.

## Why it matters

A buyer's morning is spent on a subtraction. What is on the shelf, against what
sold yesterday, store by store, product by product, on two screens that do not
talk to each other. It is roughly two hours a morning of work that requires
almost none of the judgement Korral hired that buyer for. This gives most of
those two hours back, and returns the buyer to the negotiation and planning that
only they can do.

The part worth understanding is not the time. It is the number. When an
assistant retries a request, a naive system places the order once, correctly,
and counts it twice. Nothing fails, nothing alerts, and the only thing that is
wrong is the spend total the buyer reads the next morning and makes their next
decision from. This software carries the fact that a request was a repeat all
the way through to the report, so a retry can never inflate what a human reads.

## What it cost

One hour, recorded. That bought a working tool server with three tools, a
deterministic rule engine, per-store credential handling with rotation, an audit
trail written for the buyer rather than for an engineer, and a deployment
document that answers what Korral's information technology team asked.

It did not buy production scale. The list of what is missing is short, specific
and written down.

## What it does not do yet

- Duplicate protection is held in one process. It is correct for a single
  instance and wrong for more than one. This is the first thing to fix.
- It works one store and one product at a time. Covering the estate means the
  assistant calling it repeatedly, which is deliberate: the software never
  guesses which stores were meant.
- It orders the measured shortfall, not cover for the supplier's lead time.
  Korral may well want the second. That is a policy decision for a buyer to
  make, and one function here to change.
- It automates a subtraction and a comparison. It does not automate a buyer.

## What would happen next

1. Move duplicate protection into shared storage, so it survives a restart and
   works across more than one instance.
2. Confirm eight open questions with Korral's information technology team, in
   the order they appear in `DEPLOYMENT.md`. The first is where the assistant's
   model runs, because that decides whether every result this software returns
   counts as data leaving Korral.
3. Run it against real StoreLink data for one category, for one week, and
   compare its decisions against the buyer's own. That is the only test that
   settles whether the rule as written matches the rule as practised.

## How to check it yourself

<!-- verify: skip -->
```bash
scripts/demo_proof.sh
```

That runs the buyer's task end to end and asserts every outcome rather than
printing them: the store that should order does, the store at exactly the
threshold does not, a retry is recognised as a retry, and a store this software
holds no credential for fails safely and says what to do about it.

What has actually been executed, and when, is recorded in
`docs/05-verification.md`. That file is written by the scripts themselves and
never by hand, which is what makes it evidence rather than a claim.
