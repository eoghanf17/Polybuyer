# Finding informed traders in public tape

## The problem

Polymarket publishes every trade. Somewhere in that tape are accounts that
are consistently positioned before news breaks, and accounts that react to
news faster and more accurately than everyone else. Both are worth
following. Neither is identifiable from profit and loss.

PnL cannot separate them because it is silent about *timing*. A wallet that
made $2M might have known something, might have been first to a headline,
might have bought and held for six months, or might have been lucky with
size. Those are four different businesses and only two of them can be
copied.

## The core idea: use repricings as reference clocks

A prediction market's price is flat-ish until information arrives, then it
moves and stays moved. Those moves are the only externally visible
timestamps of when the news landed. Once you have them, every trader in the
market can be timed against them, and three populations fall out that PnL
merges into one:

| Entered | Reads as | Constraint on copying |
|---|---|---|
| hours **before** the move | anticipatory — knew, or guessed repeatedly | liquidity |
| in the **first seconds** of it | professional news flow | latency |
| **after** it is public | the crowd, arriving | no edge to copy |

`polybuyer/jumps.py` finds the repricings; `polybuyer/features.py` times
everyone against them.

### Detecting a repricing

Resample the price path onto a fixed grid, compare a trailing median level
to a leading median level at every point, keep local maxima above a
threshold, and discard anything that reverts. Medians throughout, because
prediction-market tapes are full of single prints that sweep a thin book and
bounce straight back.

Two guards were added only after synthetic tests caught the detector
failing without them:

**Baseline stability.** A candidate whose pre-move window is itself volatile
is rejected. Without this, the *return leg* of a spike is reported as fresh
news: the baseline median sits inside the spike, so the fall back to normal
looks like a large, persistent, downward repricing.

**Onset walk-back.** Onset is anchored to where the price *left* its
baseline, not where it committed to the new level. This matters more than it
sounds. If onset is placed a quarter of the way up the ramp, then everyone
who traded on the first tick of the news — which is exactly what a
professional news desk does — is timestamped *before* the move and misread
as having anticipated it. The archetypes swap places.

### The guard band, and what the data cannot resolve

Tape timestamps are whole seconds and show only executed prints. "Traded two
seconds before the first print of the move" and "was the first to react"
are, at that resolution, the same observation. So a dead band around onset
credits sub-guard entries as *reaction*, not anticipation.

An insider claim then rests on being positioned minutes-to-hours early,
which the data genuinely supports, rather than on sub-second ordering it
does not.

### The null: being right before the move is not, by itself, evidence

In any market about to move, somebody is always positioned correctly by
accident. So anticipation is scored as *excess over the rate achieved by
everyone else who was also positioned in the same pre-move window*, weighted
by size. In an efficient market that baseline is ~50%. Only the excess
counts.

## The finding that changes what you should build

Both archetypes are detectable. But the simulation showed they are blocked
by **opposite constraints**, which is the practically important result:

| | anticipatory | news reaction |
|---|---|---|
| time before price clears a 2c cap | ~1.5 hours | ~5 seconds |
| share of target size actually fillable | ~7–11% | ~95–100% |
| binding constraint | **liquidity** | **latency** |

The reason is mechanical. Anticipatory traders act in the quiet tape
*before* the news, when there is plenty of time to copy them and almost
nothing to copy into. Reaction traders act inside the news burst, when
liquidity is abundant but the price clears a limit in seconds.

This refines the prior phase's "speed above all" conclusion rather than
contradicting it. Speed is decisive for the news-flow archetype and close to
irrelevant for the anticipatory one, where you could copy the trade an hour
later and still get the price — you simply cannot get size. Those call for
different infrastructure: a co-located low-latency firing path for one,
patient scaled-in accumulation for the other.

The verdict names which constraint binds for each candidate, because a
single "followability" number would hide the distinction.

## Statistical guards

Screening hundreds of wallets for unusual timing is an ideal machine for
manufacturing false discoveries. Four guards, each of which changed the
output materially:

**Cluster by market.** Every trade in a market shares one resolution. Two
hundred prints in one football match are one observation, not two hundred.
All bootstraps resample markets.

**Refuse tiny cluster counts.** A bootstrap over one market resamples the
same market every draw: the interval collapses onto the point estimate and
reports `p=0.000` from a single lucky trade. Before this guard, noise
wallets with one well-timed print outranked the planted actors.

**Multiplicative scoring.** An additive blend of components pays out for
*style* — trading early, concentrating PnL in the pre-move window — which
merely describes when someone trades and is satisfied perfectly by a random
punter. Measured accuracy against the baseline is now a necessary condition;
everything else only modulates a score already earned.

**False-discovery control.** Testing a hundred wallets at p<0.05 finds five
by construction. Candidates are held to a Benjamini-Hochberg q-value across
the whole sweep.

On a synthetic universe of 40 markets and 145 wallets, the two planted
actors are the only follow recommendations. On a structurally identical
universe with no planted skill, there are none.

## Screens

Populations that dominate any volume- or PnL-ranked list while carrying no
directional signal:

- **Market makers.** Tested as peak position against gross volume, *not* net
  against gross. The latter also rejects a directional trader who takes
  profit early, since a round trip is indistinguishable from two-sided
  quoting under that measure.
- **Negative-risk arbitrage.** Buying NO on one outcome mints YES on all
  others via the NegRiskAdapter, producing identical position sizes across
  dozens of markets with no matching buy. Structural, not directional.
- **Correlated records.** Forty markets on one World Cup share almost all of
  their information. A record confined to a single event is not a track
  record however many markets it spans.
- **Wallet clusters.** One operator running several proxies appears several
  times in a naive ranking, and a portfolio built from the top N is far less
  diversified than it looks. Direct USDC transfers between proxy wallets
  merge them.

## What this cannot tell you

- **Why** a wallet's timing is good. It identifies accounts that are
  repeatedly positioned before repricings. Inference beyond that is yours.
- **True fill rates.** No historical order books exist for Polymarket. Fills
  are simulated against prints that actually executed, so every fill figure
  is a *lower bound* — resting liquidity that was never lifted is invisible
  and would only improve the number.
- **Anything about periods a tape does not cover.** `/trades?market=` stops
  at ~12,000 prints, newest first. Coverage is returned with the data and
  must be checked before trusting a simulation.
- **Out-of-sample performance.** Every number here is in-sample on a
  candidate pool selected for being interesting. Treat the output as a
  shortlist to paper-trade forward, not a backtest to size from.

## Scope note

This reads public on-chain trade data only. Copying a public trade is a
different act from possessing material non-public information yourself, and
most Polymarket event contracts are not securities — but some markets do
reference regulated events, so that is worth checking per market rather than
assuming in general.
