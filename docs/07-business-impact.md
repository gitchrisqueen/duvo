# Business impact

Every figure here is either taken from the brief, measured from a run of this
software, or estimated. Estimates are labelled as estimates, and the arithmetic
is shown rather than summarised, because a number a reader cannot reproduce is
worse than no number at all.

## Whose time this saves

| | |
| --- | --- |
| Role | Category buyer, chilled dairy, at Korral |
| Task | The morning availability check: for each stock keeping unit on the watchlist, at each store that matters, compare what is on the shelf against what sold yesterday and decide whether to replenish |
| How often | Every trading morning, before the afternoon the brief describes as the moment a store runs empty |
| Minutes per occurrence today | About three minutes per store and stock keeping unit pair (estimated) |
| Minutes per occurrence with this | About twenty seconds per pair, plus two minutes to brief the agent and read its report (estimated) |

The three minutes are not typing speed. They are the cost of opening the
inventory view for a store, opening the point of sale report for the same stock
keeping unit, reading two numbers off two screens, subtracting them, deciding
against a threshold held in the buyer's head, and then filling in a
replenishment form if the answer is yes. The brief describes this estate as
roughly one hundred and eighty stores and eighteen thousand active stock keeping
units, so no buyer checks everything. They check a watchlist.

## The arithmetic

**Inputs, all estimated except where noted.**

| Input | Value | Where it comes from |
| --- | --- | --- |
| Store and stock keeping unit pairs checked each morning | 40 | Estimated. This is the input most likely to be wrong |
| Minutes per pair today | 3 | Estimated |
| Minutes per pair with this | 0.33 | Estimated, from reading one result line |
| Fixed briefing and review time each morning | 2 minutes | Estimated |
| Trading weeks per year | 46 | Estimated, allowing for leave |
| Category buyers at Korral | 12 | Estimated. Not stated anywhere in the brief |

**The calculation.**

```
Today:      40 pairs x 3 minutes                    = 120 minutes per morning
With this:  40 pairs x 0.33 minutes + 2 minutes     =  15 minutes per morning
Saved:      120 - 15                                = 105 minutes per morning

Per buyer:  105 minutes x 5 mornings                = 525 minutes per week
            525 / 60 x 46 weeks                     = 402 hours per buyer per year

Estate:     402 hours x 12 buyers                   = 4,830 hours per year
            4,830 / 1,850 hours per full time year  = 2.6 full time equivalents
```

**Sensitivity.** Two inputs move this answer more than the rest. Halve the pairs
checked each morning and the saving halves with it. Take the three minutes down
to ninety seconds, which is plausible for a buyer who knows the screens well,
and the saving falls by about a third. The buyer count is the third, and it is
the one Korral can correct in a sentence. Nothing here depends on the estimate
being generous: even at half the pairs and half the minutes, the figure is over
a hundred hours per buyer per year.

**What is measured rather than estimated.** The decision itself. Against the
fixtures drawn from the brief, this server assesses store 47 as a gap of
nineteen units and raises an order for nineteen, and assesses store 102 as a gap
of exactly six and refuses, because the rule is that the gap must exceed six.
Both are asserted by `scripts/demo_proof.sh` on every run.

## What errors this prevents

Time is the easy half. These are the mistakes, and each one is prevented by a
specific piece of this design rather than by care.

| Error | How often today | What one instance costs | Basis |
| --- | --- | --- | --- |
| A retried order counted twice in the spend report | Whenever a caller retries, which for an agent is routine rather than exceptional | The order value, roughly forty euros at the fixture price, plus a spend figure that is wrong in a way nobody investigates | The order itself was correct both times, so nothing looks broken |
| A failed point of sale read treated as zero units sold | Whenever the upstream is briefly unavailable, which is a network question rather than an application one | A day of lost sales on that stock keeping unit at that store, roughly sixty-eight euros at the fixture volume and price, plus the shopper who did not find it | A zero makes the gap negative, so an empty store is reported as healthy |
| The gap computed in the wrong direction | Once, at design time, and then in every result thereafter | Stock pushed into stores that do not need it, on a chilled product with a short life | The brief does not state the direction, so it has to be chosen and disclosed |

**The first one is the one worth dwelling on with a commercial audience.** The
duplicate order is not a bug that makes something fail. It is a bug that makes a
number wrong. The order was right, the shelf is right, the system reports
success, and the only thing that is wrong is the total a buyer reads the next
morning and makes their next decision from. That is why
`OperationResult.counts_towards_totals` exists and why the replay flag is
carried all the way through to the audit line rather than being consumed by the
layer that detected it. Preventing the duplicate write is the easy half.

## What Korral can measure in week one, without our help

If a customer cannot verify the benefit themselves, they will not believe it,
and they would be right not to. All three of these are read from the audit
trail, which is written in plain language for exactly this reader.

| Measure | Where it comes from | What good looks like |
| --- | --- | --- |
| Orders raised | Audit lines reading `replenishment_order_raised -> created` | The count matches StoreLink's own order list for the same day, exactly |
| Retries suppressed | Audit lines reading `replenishment_order_raised -> duplicate`, each carrying `counts towards the daily total: False` | Every retry appears here and none of them appears in StoreLink as a second order |
| Stores not assessed | Any store reported with an explicit non-assessment rather than a decision | The number is visible. A silent zero would be the failure; a stated gap in coverage is the feature |

The third measure is the one that builds trust fastest, because it is the one
that admits something. A system that never reports a store it could not check is
either perfect or lying, and Korral's information technology team will assume
the second.

## Benchmark

Duvo states publicly that early adopters reduce manual work across core retail
processes by around forty per cent on average.

The honest reading is that this lands above that figure on a narrower base. The
morning availability check goes from about a hundred and twenty minutes to about
fifteen, which is a reduction of roughly eighty-seven per cent of that one task.
But that task is one of a buyer's several, alongside supplier negotiation,
promotional planning and assortment work, none of which this touches. The
published forty per cent is an average across a portfolio of processes, and a
single process taken most of the way is exactly what averages to a number like
that. This result is consistent with the benchmark rather than an improvement on
it, and claiming otherwise would invite a comparison the claim cannot survive.

## What this does not do

Being specific about the limits is what makes the rest credible.

- **One store and one stock keeping unit per call.** Working across the estate
  means calling the tools once per store, which the agent orchestrates. The
  server never fans out on its own and never guesses which stores were meant.
- **No general listing of stores.** The endpoint exists upstream and its
  pagination behaviour is undocumented, so a tool that returned a silently
  truncated first page would be worse than no tool.
- **Deduplication does not survive a restart or span replicas.** It is held in
  process, which is correct for the single replica a pilot assumes and wrong for
  anything larger. This is the first thing to fix for production.
- **The order quantity is the measured gap, not lead time cover.** The brief
  states when to order and is silent on how much. Ordering the gap restores
  roughly one day of observed demand. Korral may well want cover for the
  supplier's lead time instead, which is a policy decision for a buyer and one
  function to change here.
- **No promotional, seasonal or supplier judgement.** This automates a
  subtraction and a comparison. It does not automate a buyer.
