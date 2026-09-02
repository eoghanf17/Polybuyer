# FootballFan98 cluster: copy strategies against recorded liquidity

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
