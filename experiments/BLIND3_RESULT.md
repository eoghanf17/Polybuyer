# Blind test 3 — result

Pre-registered in `BLIND3.md`, committed before the first search.

## Headline: the first verified wins

**2 of 21 markets hit**, at both the 0 and 10,000 follower floors. Unlike
the earlier tests, these are markets where a trade provably existed before
any post was read — and both hits pay.

### 1. US × Iran permanent peace deal

**@CMShehbaz** (Shehbaz Sharif, 6,745,585 followers), 2026-06-14T21:15:

> *"Following intensive talks, we are pleased to announce that the Peace
> Deal between the United States of America and Islamic Republic of Iran
> has been r…"*

Entry 0.860 → terminal 1.0. Guards **pass**.

| cap | fillable | vwap | PnL | ROI |
|---|---|---|---|---|
| 1c | $1,810 | 0.870 | $271 | 15% |
| 2c | $5,708 | 0.877 | $802 | 14% |
| 5c | $34,479 | 0.896 | $4,009 | 12% |
| 10c | $222,043 | 0.936 | $15,138 | 7% |

### 2. Israel × Hezbollah ceasefire by April 18

**@TimesNow** (9,820,969 followers), 2026-04-16T17:52, relaying Trump's
announcement of a 10-day Lebanon–Israel ceasefire. Entry 0.870 → terminal
1.0. Guards **pass**.

| cap | fillable | vwap | PnL | ROI |
|---|---|---|---|---|
| 5c | $26,572 | 0.907 | $2,728 | 10% |
| 10c | $175,780 | 0.939 | $11,389 | 6% |

Nothing fillable at 1c or 2c — the book gapped straight past 0.89.

At the desk's configured sizes these are **$0.42** and **$1.03**. The wins
are real; capturing them needs $5k–$35k tickets, not $3.

## The expensive miss, and what causes it

The largest opportunity in the whole candidate set — **US strikes Iran by
Feb 28**, 0.50→0.91, $68,036 fillable, **$66,094** of demonstrable PnL —
was missed. The window was not empty:

> @emilykschrader (234,595f): *"The State of Israel has launched a
> preemptive strike against Iran — Defense Minister Israel Katz declares…"*

Ten of the twenty-two posts are about **Israel** striking Iran, and none
of those ten mentions the US. The market asks about the **US**. The gate
dropped them, and by the market's rules it was right to.

The market repriced anyway, from 0.50 to 0.91, because traders inferred
what followed from what was announced.

**This is the central finding of the run: the gate is more literal than
the market.** `resolves` was written to reject exactly this — "the market
is on the US striking Iran and the news is Israel striking Iran" is the
worked example in its own docstring — and that rule, working as designed,
costs the single largest trade available. Whether a market reprices is an
empirical question about traders, not a logical one about resolution
criteria, and the gate currently answers the wrong one.

That is not a bug to patch casually. Loosening `resolves` to fire on
correlated news reopens the false-alarm class that cost 36 points of ROI
in the original out-of-sample work. The honest statement is that the
current setting has a measured price ($66k on one market) and the
alternative has a measured price too, and nothing here says which is
larger.

## The other misses

Sampled from the corpus, free:

- **Epstein note released** — all 22 posts are retweets of Stephen King's
  "RELEASE THE EPSTEIN FILES" and similar. No announcement. Correct drop.
- **Finland win Eurovision** — commentary on Israel/Ukraine voting. The
  result announcement is not in the window. Correct drop, missed event.
- **US or Israel strike Iran by Jan 31** — 17 of 22 posts are US-related
  and the market explicitly covers both parties, so the near-miss
  explanation does *not* apply here. Unexplained.

## The guards are still untested

Both hits **passed** the guards even entering at the post timestamp, which
was supposed to be the configuration that finally exercised them.

The reason is structural. Both posts lead the onset by **0 minutes** — a
genuine breaking announcement, and the market reacts within the minute. So
the hour before the post is quiet, and the guards see nothing to block.

The guards protect against firing on a post that arrives *after* the move.
This test cannot generate one, because its search window **ends** at the
onset. Testing them requires searching `[onset, onset + 6h]` and asking
whether late posts would trigger fires the guards then block. That is the
next cheap test, and it is not done here.

So: no evidence the thresholds need refining, and no evidence they work.

## Recall

2/21 is worse than blind test 2's 3/8, on much better markets. The
pre-registered suspect is the **two-hour window**, accepted deliberately
to make the test affordable — blind test 2's Burnham signal led by eight
hours and would be invisible here. Widening it to 6h on the 19 misses
would cost roughly $2 and is the obvious next experiment.

## Cost

**433 posts, $2.17.** 20 searches covered 21 markets (the two Romanian
election markets share a rule and a window). Project total to date: ~$6.09
of X reads.
