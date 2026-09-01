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

## Choosing which markets to look at

This turned out to matter as much as the detector, and only became visible
against live data.

**Sweeping recent large trades finds the wrong markets.** The first live run
took the 120 markets carrying the most recent large-trade activity and got a
sample that was **57% esports, 24% live sport, 1% macro, 0% politics** -- The
International and weekend football. Informed news flow does not trade there.

**gamma-api is usable, contrary to the handoff.** The prior phase recorded
`gamma-api.polymarket.com/markets` as returning `[]`, but that applies only
to its `condition_ids` filter. The plain listing works, honours
`order=volumeNum` and `end_date_min`, and paginates by offset -- which is the
only way to enumerate markets by anything other than "recently traded". It
surfaces the right population immediately: the 2024 election, *US forces
enter Iran by April 30*, *MicroStrategy sells any Bitcoin*. Note `tag_slug`
is silently ignored, so category filtering must be done client-side.

**A date window is required, not optional.** All-time volume ranking spans
2024-2026 across unrelated topics, and almost no wallet appears in enough of
those markets to clear the breadth screens. Restricting to a recent window
gives a cohort that actually shares traders.

### The in-play confound

Scheduled match markets have to be separated from news markets, and the
reason is not squeamishness about sport.

In a live game the price tracks the game. Being "positioned before the
repricing" is therefore satisfied by anyone watching a faster stream than the
market -- and streams run on delays that differ by tens of seconds between
providers. That is a real, monetisable edge, but it is a **latency edge on a
public broadcast**, not information, and nothing in the tape distinguishes
the two. An anticipation score computed over match markets is measuring
something quite different from the same score over an election market.

The CLOB's `game_start_time` marks these markets precisely -- populated for
scheduled matches, null for everything else -- so they are excluded by
default rather than guessed at from the title.

### Tape truncation is the binding constraint on big markets

`/trades?market=` returns at most ~12,000 prints, newest first, and **every**
market in the top volume ranking hits that cap. Observed spans:

| market | visible tape |
|---|---|
| Will Donald Trump win the 2024 US Presidential Election? | final **8.9 hours** |
| Will Kamala Harris win... | final 14 hours |
| US forces enter Iran by April 30? | final 44 hours |
| Will Nicolae Ciucă win the 2024 Romanian Presidential... | final 49 days |

So on those markets every figure -- PnL, capital, ROI -- describes the
visible window, not a trader's full record there. A position built before the
window is invisible, and mark-to-terminal on the remainder is internally
consistent but partial. Runs report how many tapes truncated; markets whose
visible span is too short to establish a baseline are skipped entirely rather
than analysed against a baseline that does not exist.

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
