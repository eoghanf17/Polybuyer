# FootballFan98 cluster: copy strategies against recorded liquidity

> **The replication used one wallet and was wrong twice over.** The cluster
> is four wallets (now pinned in `polybuyer/targets.py`), and FootballFan98
> is the loss-making leg — **−$1.07M** against the cluster's **+$4.76M**.
> Simulating it alone returns −11.9%/−16.0%; that measures the worst member,
> not the strategy. It also included in-play matches, which the original
> study excluded. Both are fixed before any number here is trusted; see
> "Replication attempt" below.


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


## Replication attempt (`experiments/ff_timeline.py`)

Re-run to answer "how much capital would actually have been deployed at any
given time, and what was PnL over time" — which totals cannot answer, since
cumulative deployment counts a dollar again each time it is recycled.

Target resolved to `0xc31d0a0d63d760d72a1236d16beaa6a71c854ebe` via gamma's
profile search. **The address was in no file in this repo** — it existed
only in the original session's HANDOFF.

**This run used that wallet alone, which is the central error.** The cluster
is four wallets, verified 2026-09-02 as a closed network — all six pairs
show direct on-chain transfers, every member has degree 3, five of six
edges carry USDC:

| handle | address | volume | rank | PnL |
|---|---|---|---|---|
| FootballFan98 | `0xc31d…4ebe` | $45.4M | #519 | **−$1.07M** |
| (unnamed) | `0x006cc834…16ea` | $64.9M | #324 | **+$4.72M** |
| Airpods123 | `0xb90494d9…c255` | $40.0M | #583 | +$1.02M |
| RBax | `0x4366ab8b…c73e` | $2.8M | #7,882 | +$91K |
| **combined** | | | | **+$4.76M** |

FootballFan98 is the leg that loses money. A simulation of it alone was
always going to return a loss, and did. Signals must come from the
cluster's combined position per market, with all four excluded from the
liquidity a follower consumes.

### What it found

| | $50→$1,000 | $500→$5,000 |
|---|---|---|
| positions | 96 | 96 |
| peak concurrent exposure | **$1,933** | **$8,699** |
| cumulative deployed | $24,651 | $110,249 |
| PnL | **−$2,931 (−11.9%)** | **−$17,592 (−16.0%)** |

Peak exposure is an eighth of cumulative deployment, because median hold is
**0.2 days** and capital recycles constantly. Exposure is zero on 177 of
228 days.

### Why it disagrees with +16.7%

| segment | positions | deployed | PnL | return |
|---|---|---|---|---|
| in-play matches ($50→$1,000) | 94 | $24,241 | −$2,980 | −12.3% |
| in-play matches ($500→$5,000) | 94 | $107,786 | −$17,897 | −16.6% |
| news markets ($50→$1,000) | 2 | $410 | +$49 | +12.0% |
| news markets ($500→$5,000) | 2 | $2,463 | +$304 | +12.4% |

**The wallet name is literal.** In this window the target trades live
football, and copying them there loses money. The original study ran
against the `discover` market universe, which excludes in-play by default —
so it measured this wallet's *news* trading, which is two positions here.

Either the original covered a period when the wallet traded news markets in
volume, or its universe selection captured a different slice. Unresolved.

### Two methodology notes on the replication

Signals come from the wallet's own history, not the market tape:
`market_tape` is capped and newest-first, so building signals from it
mistakes their fifth trade for their first. That bug was present in the
first pass of this script and cost about 10 points. 19 signals whose tape
does not reach back are dropped as unmeasurable, matching `evaluate()`.

Cluster detection returned **one** wallet. If siblings exist and were
missed, this run filled against orders it should have excluded — which
flatters the fills, so the losses are if anything understated.
