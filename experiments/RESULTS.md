# Results — X news-trading strategy, out-of-sample

Test half: 511 markets, **208** in the frozen target categories, 134 tapes
truncated at the 12k cap. Strategy fixed in `STRATEGY.md` (commit `1f4adb6`)
before any of this was fetched.

## Verdict against the pre-registered bar: NOT DEMONSTRATED

The bar was: TEST set, 45s latency, 80% direction accuracy, positive ROI at
bootstrap **p < 0.05**, on the honest signal set.

**Result: +13.6%, p = 0.124.** Fails.

It would have passed comfortably on the flattering signal set (+49.8%,
p=0.000), which is precisely why the all-alarms set was added to the
protocol before the test was opened.

## The two signal sets

At 45s latency (the user's actual case), by direction accuracy:

| accuracy | persistent only | **all alarms** |
|---|---:|---:|
| 100% | +53.7% (p=0.000) | +26.6% (p=0.004) |
| 90% | +51.6% (p=0.000) | +16.7% (p=0.054) |
| **80%** | +49.8% (p=0.000) | **+13.6% (p=0.124)** |
| 70% | +30.3% (p=0.009) | +7.6% (p=0.291) |

483 signals become 636 once moves that reverted are included. Those 153
false alarms — 24% of what a feed would fire on — cost **36 points** of ROI.
They, not latency, are what stands between this strategy and viability.

## Powerstream is worth nothing here

The question that prompted the experiment, answered in both signal sets:

| latency | persistent (80% acc) | all alarms (80% acc) |
|---|---:|---:|
| oracle 0s | +46.8% | +13.6% |
| **powerstream 2s** | +47.5% | **+13.7%** |
| good API 15s | +48.9% | +16.9% |
| **NO powerstream 45s** | +49.8% | **+13.6%** |
| slow poll 120s | +38.2% | +4.2% |
| human 300s | +29.7% | −1.6% |

2s and 45s are indistinguishable, and 45s scores marginally *higher* in the
persistent set — the signature of no latency edge at all in that range. This
follows directly from the training half, where not one repricing in 877
cleared a 2c cap inside 2 seconds and the median target move stayed gettable
for two to four minutes.

There is a cliff, but it sits between **45s and 120s**, not at 2s. Being
under a minute matters; being under a second does not.

## The design conclusion this forces

Latency below ~60s is free, and false alarms cost 36 points. So the budget
should be spent on **confirmation, not speed**: waiting 30–45s for a second
source before firing costs nothing measurable in edge and is the only lever
that attacks the thing actually killing the strategy.

That inverts the usual instinct, and it also argues against the fastest
sources. OSINT relays lead the wires by minutes and are sometimes wrong;
that lead is worth nothing here, while their error rate is worth 36 points.
For this market, **wire services beat fast-but-wrong feeds**.

Direction accuracy is the other dominant lever: on the honest set, going
from 100% to 80% costs 13 points, more than the entire latency range does.

## What this does not establish

- **No claim rests on an observed tweet.** X returns 401 without credentials
  and archive search is enterprise-tier. Repricing onset is the proxy for
  "when the news landed", and the account list is unvalidated.
- The 80% direction-accuracy figure is an assumption, not a measurement.
  Real accuracy depends on sources and parsing, and the result is highly
  sensitive to it.
- Fill is ~31% of intended size at $500 per signal, so capacity is thin.
- 134 of 208 tapes are truncated, so signals are drawn from visible windows.
- Categories come from a keyword classifier over question text.

## Honest summary

A tweet-triggered bot on Polymarket geopolitics/politics/corporate markets
is **plausibly profitable and not demonstrated**. Every latency variant is
positive on the honest set; none reaches significance at realistic direction
accuracy. The infrastructure question is settled — a firehose buys nothing —
and the real engineering problem is not being fast but being right.
