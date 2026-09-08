# Are they trading lineups? No — they are trading liquidity

The cluster's entries cluster shortly before kickoff, and official lineups
drop at a known time (T-60 in the Premier League, T-60 to T-75 across most
major leagues). That made the mechanism testable rather than merely
plausible, and it was the one thing that would have justified believing the
point estimate over the confidence interval.

**It fails, on the timing shape alone — before any PnL is computed.**

## Step 1: the histogram, examined before returns

Entries by minutes before kickoff:

| window | entries |
|---|---|
| 0–15m | **91** |
| 15–30m | **89** |
| 30–45m | 68 |
| 45–60m | 25 |
| **60–75m** *(lineups drop here)* | **14** |
| 75–90m | 8 |
| 90–120m | 6 |
| 120–180m | 8 |
| 180m+ | 64 |
| in-play | 19 |

If lineup news were the edge, entries would **pile up just after** the
announcement — a spike at 45–75m. Instead the distribution *declines
monotonically* from the last 15 minutes backwards, and the lineup bin is
one of the emptiest on the chart. Only 27% of entries fall in the declared
T-75 to T-30 window at all.

## Step 2: returns confirm it

| subset | $250 → $5,000 | p |
|---|---|---|
| all positions | +13.5% | 0.044 |
| **lineup window T-75..T-30** | **+11.4%** | **0.228** |
| everything else | +14.8% | 0.054 |

Restricting to lineup-timed trades makes the result **worse**, not better,
on every ladder. That is the opposite of what a lineup edge predicts.

## Step 3: the sweep is noise

| window | return | p |
|---|---|---|
| T-30..T-0 | +6.9% | 0.282 |
| T-45..T-15 | +11.9% | 0.196 |
| T-60..T-30 | +8.9% | 0.288 |
| T-75..T-30 | +11.4% | 0.228 |
| T-90..T-45 | **−8.6%** | 0.674 |
| T-120..T-60 | +1.5% | 0.471 |
| T-150..T-75 | **−14.2%** | 0.678 |
| all pre-kickoff | +12.4% | 0.071 |

A real effect degrades smoothly as the window moves off its centre. This
jumps between +11.9% and −14.2% with no coherent structure — noise.

## What actually explains the timing: book depth

Tape volume in the same windows, averaged per market:

| window | volume/market | entries |
|---|---|---|
| T-15..T-0 | **$481,990** | 91 |
| T-30..T-15 | $256,015 | 89 |
| T-45..T-30 | $165,026 | 68 |
| T-60..T-45 | $63,871 | 25 |
| T-75..T-60 | $42,253 | 14 |
| T-90..T-75 | $17,886 | 8 |

**Spearman r = 1.00** — the rank order of entry counts matches the rank
order of available volume exactly, across all six bins. Pearson is 0.887,
lower only because volume rises far faster than entries at the very end.

The cluster trades $10k+ tickets. Match-market books are thin until the
hour before kickoff and then fill rapidly. They enter when the book can
absorb them — a **sizing constraint, not an information edge**. The
30-minute median lead that looked suggestive is just where the money is.

## Consequence

The mechanism hypothesis is refuted, so the interval stands as the honest
read of the strategy: **+13.5% [−2.1%, +28.9%]**, not significant once the
best 5 markets are removed, not stable across time halves, and now without
a candidate explanation for why it should work.

That does not prove there is no edge. It removes the specific reason to
believe in one, and it means any remaining case rests on more data rather
than on a story.
