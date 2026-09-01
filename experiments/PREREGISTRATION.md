# Pre-registration: automated X-driven news trading on Polymarket

**Committed before any test-set data was examined.** The git timestamp on
this file is the evidence. Everything below is fixed; the test is run once,
without tuning.

## Why pre-register

The question is whether a rule *chosen in advance* would have made money.
If the target markets or the entry rule are picked after seeing which
markets moved, the answer is guaranteed to be yes and worth nothing. So the
selection rule, the entry rule, the sizing and the metrics are all fixed
here, and the test set is not inspected until they are.

## What cannot be tested here, and why

X's API returns 401 without credentials; the full-archive search that
historical tweet timestamps would require is Pro-tier (~$5k/month) in any case.
So **no claim below rests on an observed tweet.** Specifically:

- I cannot verify that a named account actually broke a given story first.
  The account list in the strategy is a design artefact from domain
  knowledge, explicitly unvalidated.
- I cannot measure tweet-to-market latency directly.

What I *can* measure is the thing that decides whether the strategy is
viable at all: **how long the market leaves the price gettable after a news
repricing begins.** A tweet-driven bot enters at `tweet + own latency`. The
market's repricing onset is driven by the fastest readers of that same
tweet, so onset is the right zero point, and the question becomes how much
latency budget exists after it. That is measurable from the tape.

## Universe (fixed)

- Source: `gamma-api` markets, `closed=true`, ordered by `volumeNum`.
- Window: markets resolving in the last 365 days.
- Excluded: in-play markets (`game_start_time` set). A live match reprices
  continuously with play; its moves are not news breaks.
- Excluded: markets whose visible tape spans < 2h (server 12k-print cap).

## Split (fixed, and the reason for it)

Split by market **end date**, at the median of the universe:

- **TRAIN** = older half. Used to characterise news repricings and to write
  the strategy.
- **TEST** = newer half. **Not fetched or inspected until the strategy file
  is committed.**

Chronological rather than random, because a news-trading strategy is
deployed forward in time and a random split would leak contemporaneous
information between halves.

## Entry rule (fixed)

For each detected repricing (jump) in a targeted market:

1. Enter at `onset + L` seconds, in the direction of the jump.
2. Limit price = price at entry time + 2c cap (the cap that beat 1c earlier).
3. Fill only from prints that actually executed in the following 10 minutes,
   at or inside the limit. Lower bound, as always.
4. Hold to resolution.
5. Fixed $500 per signal. No target notional exists to scale from here.

## Latency levels (fixed)

| label | L | what it represents |
|---|---|---|
| oracle | 0s | unattainable; upper bound only |
| powerstream | 2s | enterprise firehose, colocated, pre-warmed order path |
| good API | 15s | authenticated streaming, ordinary hosting |
| **no powerstream** | 45s | **polling the public API, the user's actual case** |
| slow poll | 120s | conservative polling |
| human | 300s | someone reading a feed |

The powerstream / no-powerstream comparison the user asked for is the 2s row
against the 45s row.

## Direction assumption (fixed, and its penalty)

Entering "in the direction of the jump" assumes the bot reads the news
correctly every time. That is an upper bound. Results are therefore also
reported at direction accuracies of 90%, 80% and 70%, applied as a random
sign flip on that fraction of signals under a fixed seed.

## Metrics (fixed)

Per latency level: signals, fill rate, mean fill fraction, total PnL, ROI on
deployed capital, and a cluster-bootstrapped CI **resampling markets**.

## Decision rule (fixed, stated before seeing the result)

The strategy is called viable only if, on the TEST set at **45s latency and
80% direction accuracy**, ROI is positive with a bootstrap p < 0.05.
Anything weaker is reported as not demonstrated.

## Deviations

Any departure from this document is recorded in `experiments/RESULTS.md`
with its reason.
