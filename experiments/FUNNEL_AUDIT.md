# Were we too tight? Audit of the market-selection funnel

Prompted by "2 possible trades in 6 months seems incredibly low". It was
low, and mostly for reasons that are not the filters.

## What was actually wrong

### 1. The universe was half-sampled — a parameter, not a filter

`candidates50.py` called `top_markets(pages=10)`, i.e. **the top 1,000 by
volume**. Gamma will serve 2,100 resolved markets in the same window before
it stops. So the first run looked at 48% of what was reachable, and the
"6 months" framing was never a statement about the market, only about how
far I paged.

Note the ceiling is real: asking for 6,000 still returns 2,100, and the
lowest volume in that set is **$2.97M**. Everything reachable through this
endpoint is a large market.

### 2. The jump detector was too strict for this population

Re-running with a deliberately loosened config
(`min_move` 0.08→0.05, `min_market_trades` 60→25, `persistence_frac`
0.5→0.35) recovered 90 markets the shipped detector called "no repricing",
of which **44 were tradeable — 17% of the final total**.

## The corrected count

| stage | markets |
|---|---|
| reachable resolved markets (gamma ceiling) | 2,100 |
| past text screens | 1,137 |
| no repricing under **either** detector | −397 |
| repricing found, but < $200 fillable at 5c | −484 |
| **tradeable** | **256** |
| of which in-play match markets (`gameStartTime`) | −131 |
| **genuine news markets** | **125** |

**35 → 125**, carrying **$483,901** of demonstrable PnL.

## But 125 markets is not 125 opportunities

| cluster | markets | PnL |
|---|---|---|
| Iran/US conflict | 41 | $305,964 |
| Crypto price | 8 | $37,950 |
| Israel/Lebanon | 8 | $7,769 |
| Token launch | 6 | $16,595 |
| Oil | 6 | $9,683 |
| Romania election | 5 | $32,298 |
| Eurovision, US government, Macro | 5 | $14,906 |
| genuinely distinct one-offs | 46 | $58,736 |

**Ten event clusters.** Iran/US alone is 41 markets and 63% of the PnL —
one story, repriced across forty-one contracts. The research phase's rule
that the independent unit is the *event* applies directly.

Honest rate: **roughly 1–3 tradeable news events per month**, not two in
six months, and not 125.

## Filters I am not changing, and why

**In-play / sports exclusion.** 131 of the 256 tradeable markets were
in-play — over half. They have the biggest jumps and the deepest books in
the whole set ("Will England win on 2026-07-11?" alone shows $753k). They
are excluded because the "news" is a goal scored on live television: a
latency race against a broadcast, not an information edge. This audit
accidentally measures how much including them would flatter the numbers.

**No-repricing exclusion (397 markets, 35%).** These drifted to resolution
with no news moment under either detector. There was no trade to find.

**The $200 fillable floor (484 markets).** If anything too loose — the wins
that matter need $5k–$35k tickets.

**The $25,000 volume floor.** Never binds: every reachable market is
≥$2.97M. Harmless, but it does no work and I should stop citing it as
though it does.

## The detector loosening is a real trade-off, not a free win

Measured across the 125 news markets, counting head fakes:

| detector | resolving | PnL | head fakes | PnL | net | hit rate |
|---|---|---|---|---|---|---|
| shipped | 143 | $502,865 | 31 | −$63,490 | $439,375 | **82%** |
| loose | 292 | $985,054 | 139 | −$303,726 | $681,327 | **68%** |

Loosening buys 55% more net PnL and costs 14 points of hit rate. Those are
measured with *perfect* signal identification — live, the gate has to tell
resolving from head fake, and the original out-of-sample work put the cost
of false alarms at 36 points of ROI. Doubling the false-alarm population is
the most expensive thing this strategy can do.

**Resolution:** the detector is a research tool, not a live component —
nothing arms off it. So use the loose config to *generate backtest
candidates* (more markets to test against, and the head fakes it surfaces
are exactly what a live desk would lose on), and keep the strict config
wherever a "win" is being counted.

## What this changes

The X search should be re-run against the expanded set, prioritised by
cluster so the spend buys new information rather than forty more Iran
markets. Roughly 40 markets covering all ten clusters is about **$4**.
