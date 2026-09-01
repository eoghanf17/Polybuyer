# What a month of this would have made

Measured over the 45 days to 2026-09-01, on markets that passed the filters
and resolved YES.

## The payoff per fire is small, because the market has already moved

Median price of the reference outcome, at intervals before the market
committed to certainty (44 markets with usable tapes):

| entry point | median mid | our price at +5c | PnL per $10 |
|---|---:|---:|---:|
| 7 days before | 0.63 | 0.68 | $4.71 |
| 24h before | 0.57 | 0.62 | $6.13 |
| 1h before | 0.76 | 0.81 | $2.35 |
| **5 min before** | **0.83** | **0.88** | **$1.36** |

Contrary to what I expected, these markets have *not* fully converged: none
of the 44 was above 0.90 even five minutes out. There is genuine edge left.

But it is thin at the moment a bot would act. Reacting to an announcement
means entering at ~0.83 and collecting the last 17 points, which after the
5c aggression is **$1.36 on a $10 stake**. The money is in the 24-hour
window, where the price is 0.57 — and that is a forecasting edge, not a
reaction one. Nothing in this design captures it.

## The fire rate is the problem, and it looks close to zero

The gate was run against every post the identified principal made in the 48
hours before each repricing, across **33 markets**. It produced **no
qualifying fires at all**.

Not because the gate is broken — it scores 16/17 on the labelled set with no
false negatives. Because the posts were not there:

- **@megaeth** posted through its own token launch window about apps,
  builders and ecosystem partners. The "MegaETH (MEGA) goes live" posts came
  from third-party promo accounts, not the project.
- **@edgeX_exchange** posted about USDC support, Arbitrum, Chainlink and
  Privy. No token-launch announcement.
- **@elonmusk** around the FSD repricing: Diablo, the Sun, gambling.
- **@ZelenskyyUa** named a new Commander-in-Chief 31 hours *after* the
  market had already moved.

## Monthly PnL

| fires/month | deployed | gross | net of $5 running costs |
|---:|---:|---:|---:|
| 61 (every filter-passing YES market) | $610 | $83.18 | **$78.18** |
| 25 (earlier 120-day estimate) | $250 | $34.09 | **$29.09** |
| 5 | $50 | $6.82 | $1.82 |
| 2 | $20 | $2.73 | −$2.27 |
| **0 (what actually fired)** | $0 | $0 | **−$5.00** |

Break-even is about **four fires a month**.

## What this says

The ceiling is low and the floor is negative. Even catching *every* market
that passed the filters and resolved YES — which no signal will — the
strategy makes about **$78 a month at $10 a fire**. Scaling the stake scales
that linearly until fills bind, so $100 a fire is roughly $780 a month at
the same hit rate.

But the measured hit rate on the principal-only filter is zero over 33
markets. The binding constraint is not the gate, the latency or the cost. It
is that **the principals largely do not post the thing the market resolves
on** — and when they do, they can be a day late.

Two ways forward, neither free:

1. **Widen past principals to beat reporters**, accepting the rumour risk
   the design deliberately excluded. Coverage would rise sharply; the
   false-alarm rate is what killed the earlier news-trading variant.
2. **Move earlier in the curve.** The payoff at 24 hours is $6.13 against
   $1.36 at five minutes — 4.5x. Whatever is repricing these markets a day
   ahead is worth more than the announcement itself, and it is not a tweet.
