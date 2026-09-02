# FootballFan98 cluster: copy strategies against recorded liquidity

> **Replicated against the full four-wallet cluster.** Every ladder is
> positive: **+12.6% / +13.5% / +15.7%**. An earlier attempt used
> FootballFan98 alone and returned −11.9%, because FootballFan98 is the
> loss-making leg — **−$1.07M** against the cluster's **+$4.76M**. See
> "Cluster replication" below for the numbers and the caveat that matters.


Study run at commits `a96ba1e` (recorded-liquidity evaluation) and
`fb4c1c1` (ladder sizing). Written up here because the results existed
only in commit messages — the ledger covers news-desk markets, and this
is a copy strategy, so it had no home.

## The problem the study found

The prior phase measured copy strategies with **mechanical slippage** —
assume you fill your whole intended size at the target's price plus k
ticks. That is an upper bound. On the one strategy where the same phase
had checked real fills, the gap was large: paying a cent cost ~2.3 points,
while actually competing for the offers cost 14.

Re-measured against **recorded liquidity** — follower orders filling only
from prints that executed after the signal, inside the cap and window,
with the target's whole cluster excluded (you cannot fill against the
order you are copying, nor against the same operator's other wallet firing
the same idea) — **all three headline strategies flip negative.**

## The fix: ladder sizing

Do not mirror their size. Size a small fixed-dollar order from their
notional instead: **$50 at their $10k, rising to $1,000 at their $350k,
first trade per market only, signals above $10k.**

| | mirrored | laddered |
|---|---|---|
| fill rate | 41% | **83%** |
| capital deployable | 44% | **83%** |
| selection | −27.3pt | **+12.6pt** |
| **recorded ROI** | **−11.1%** | **+16.7%** |

The mechanism is not price. Adverse selection cost 0.7pt either way. It
was that **the profitable half of their book could not be reached at their
size** — a few hundred dollars fills out of prints that could never absorb
six figures.

## Robustness

- **Slippage caps 1c–5c:** +15.6% to +16.7%
- **Split-half:** +15.6% first half of year, +18.0% second
- **Dose-response in their trade size:** +4.3% any size, +16.7% >$10k,
  +17.1% >$25k, **+27.9% >$50k**

The gradient is the strongest part of the evidence — the effect grows
monotonically with the conviction of the signal being copied, which is
what a real edge should do and what an artefact usually does not.

## The caveat that has not gone away

**No single cut clears p<0.05 on its own, and many variants were tried.**
The bootstrap floor was raised from 8 to 20 clusters during this work
after a live false positive: a wallet scored +40.0% anticipation with CI
[+14.1%, +55.3%] and q=0.047 off 11 markets, then came back +8.9%
[−12.2%, +27.3%], p=0.21 on its full 65-event history. A bootstrap
resamples only what it was given.

## Capacity

| ladder | deployed | recorded ROI |
|---|---|---|
| $10 → $100 | $2k | 14.2% |
| **$50 → $1,000** | **$15k** | **16.7%** |
| $500 → $5,000 | $86k | 9.1% |

Returns degrade with size exactly as the mechanism predicts. This is a
small-capital strategy by construction — the edge *is* being small enough
to fill where the target cannot.

## Fire rate, against the news desk

$15k deployed at $50–$1,000 a signal implies roughly **50–75 signals a
year, about one a week**. That is inferred from capital ÷ ladder size, not
a recorded count — `follow.evaluate()` reports `n_signals` to stdout and
nothing saves it, which is worth fixing before any live run.

For comparison the X news desk verified 3 tradeable signals across 57
searched market-windows over nine months: **one per six weeks**.

## Status

Built, tested, never run live. Needs no X subscription and no OpenAI
spend. On the evidence here it is the more practical of the two
strategies, with the multiple-testing caveat above unresolved.




## Cluster replication (`experiments/ff_timeline.py`)

All four wallets, the cluster's **combined** position per market as the
signal, all four excluded from follower liquidity. 6 Sep 2025 – 20 Jul 2026.

Intake: 41,728 prints worth **$69.4M** across **1,533 markets**.

| ladder | positions | cumulative deployed | peak exposure | PnL | return |
|---|---|---|---|---|---|
| $50 → $1,000 | 396 | $93,022 | **$4,561** | +$11,755 | **+12.6%** |
| $250 → $5,000 | 396 | $393,315 | **$21,614** | +$53,193 | **+13.5%** |
| $500 → $10,000 | 396 | $698,923 | **$40,477** | +$109,993 | **+15.7%** |

Peak exposure is roughly a twentieth of cumulative deployment on every
ladder — positions are short and capital recycles. Exposure is live on 181
of 318 days.

### Returns rise with size here

The single-wallet study found capacity decaying ($15k at 16.7%, $86k at
9.1%). Across the cluster they *increase* with ladder size. On this
evidence the ceiling is above $40k of peak exposure rather than below it,
but three points is a trend and not a curve.

### It is pre-match, not in-play

An earlier version of this section called it 392-of-396 in-play and
dismissed it as a latency race against television. That was wrong. The flag
came from `game_start_time` being *present*, which only says the market is
**about** a scheduled match.

Comparing each entry against kickoff:

| when the cluster entered | positions |
|---|---|
| 0–2h before kickoff | **301** |
| 2–24h before | 70 |
| >24h before | 2 |
| **after kickoff (in-play)** | **19** |

**373 of 392 (95%) entered before kickoff**, median 30 minutes ahead.
Official team lineups land about an hour before kickoff, which is the
window most of these sit in — consistent with trading team news, though
nothing here establishes that.

| segment | positions | deployed | PnL | return |
|---|---|---|---|---|
| **pre-match** | **373** | $86,648 | +$10,338 | **+11.9%** |
| in-play | 19 | $5,747 | +$1,533 | +26.7% |
| non-match | 4 | $627 | −$115 | −18.4% |

*(at the $50 → $1,000 ladder; pre-match is +12.4% and +14.4% on the larger
two.)*

So this is a **pre-match sports copy strategy**, and the returns are not
explained by watching a faster video feed. It is still not the news-trading
strategy the rest of the project is about.

### Are the fills real?

Yes, within a stated bound. `simulate_fill` consumes only prints that
actually executed on our side after the signal, inside a 2c cap and a
10-minute window, with all four cluster wallets excluded.

Measured against the same-side executed volume in each window:

| ladder | median share of flow | p90 | took 100% |
|---|---|---|---|
| $50 → $1,000 | **0%** | 7% | 0% |
| $250 → $5,000 | **1%** | 26% | 1% |
| $500 → $10,000 | **2%** | 39% | 1% |

Median 68 counterparty prints per window. So the order is a small slice of
demonstrated flow in the typical case, which is what makes the fills
credible rather than theoretical.

Two limits remain: **no market impact is modelled**, which matters at the
p90 end of the largest ladder; and the prints consumed were taken by
someone else, so in reality we would have been competing for them rather
than adding to the queue. Both point the same way — the largest ladder is
the least trustworthy of the three.

### Method

Signals come from each wallet's own trade history, not the market tape:
`market_tape` is capped and newest-first, so the cluster's fifth trade
would read as its first. 25 signals were dropped as unmeasurable because
the tape did not reach back; 1,041 markets produced no qualifying signal.
Fills consume only prints that actually executed, inside a 2c cap and a
10-minute window — a lower bound, since no historical order books exist.
