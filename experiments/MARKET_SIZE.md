# What trading markets of all sizes would buy

The whole project has been looking through a keyhole. `top_markets()` is a
single gamma query, and gamma caps any one query at **2,100 rows**. Ordered
by volume descending, that ceiling landed at **$2.97M** — so every market
this project has ever screened was in roughly the top tenth by volume, and
the "$25,000 volume floor" added to `discover.screen()` never bound because
nothing below $2.97M was ever visible to it.

Slicing the same nine months **month by month** puts each query under the
ceiling:

| | markets | min volume |
|---|---|---|
| single query (the old view) | 2,100 | $2.97M |
| sliced by month | **18,832** | $177k |

Every month still hit 2,100, so 18,832 is itself a floor. Median volume
across the fuller set is **$769k** — four times below the old cutoff.

## Tradeable yield does not collapse below the old floor

Yield could not be assumed constant: the binding screen is "≥$200 fillable
at a 5c cap in the 30 minutes after the onset", and that is exactly what
thin markets fail. So it was measured, 55 markets sampled per band.

| band | screened | tradeable yield | 95% CI | est. markets | median PnL |
|---|---|---|---|---|---|
| $250k–500k | 740 | 4% | [1.0%, 12.3%] | 27 | $1,240 |
| $500k–1M | 1,704 | **22%** | [12.9%, 34.4%] | 372 | $243 |
| $1M–3M | 1,138 | **20%** | [11.6%, 32.4%] | 228 | $490 |
| $3M+ | 662 | 15% | [7.6%, 26.2%] | 96 | $2,174 |

The mid bands yield **more** than the largest markets, not less. Only the
$250k–500k band falls away, and that estimate rests on 2 hits in 55 — treat
it as "small and uncertain" rather than as a measured 4%.

**723 tradeable news markets** over nine months, against **125** in the old
universe — **5.8×**, with a range of 410–1,218 from the sampling error alone.

## What that means in fires

At the gate hit rate actually measured across blind tests 3 and 4 — 3
distinct hits from 57 searched market-windows, 5.3%:

| | old universe | all sizes |
|---|---|---|
| tradeable markets / 9mo | 125 | 723 |
| fires / 9 months | 7 | **38** (range 22–64) |
| **fires / month** | **0.7** | **4.2** |

So the honest revision to "once every month or two": trading all market
sizes moves it to **roughly one a week**. That is a different strategy
shape — still not a fire or two a day, but no longer something that idles
for six weeks between signals.

## The catch: the new trades are smaller

Median demonstrable PnL per tradeable market is **$2,174** in the $3M+ band
and **$243–$490** in the mid bands. Six times the trades, at a fifth to a
tenth of the size each.

Total across all bands at full fillable size: **~$23,400 over nine months**,
of which the $3M+ band alone contributes $11,000 from 5 fires. The tail is
numerous and thin.

## What is not measured here

The 5.3% hit rate comes from **large** markets. Whether a $600k market gets
broken on X at the same rate is unknown and plausibly worse — fewer
journalists cover it, and blind test 2 showed niche markets where nothing
was posted at all. If the hit rate halves in the mid bands, the estimate
falls to roughly 2.5 fires a month.

X spend scales with markets watched, not markets hit: ~20 posts per market
window puts 723 markets at roughly $72 over nine months, which is not the
constraint.
