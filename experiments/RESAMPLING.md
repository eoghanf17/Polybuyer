# Can subsampling buy significance? No — and it fails silently

Question asked: draw many subsamples of 70–80% of the markets, compute the
return on each, average across them — does that give a more statistically
significant result?

**No.** And the failure mode is dangerous, because it produces a
*narrower* interval that looks better and is wrong.

## The demonstration

$250 → $5,000 ladder, 396 markets. Ordinary cluster bootstrap is the
honest baseline:

| method | estimate | 95% interval | p |
|---|---|---|---|
| **cluster bootstrap** | +13.5% | [−2.1%, +28.9%] | **0.044** |
| 70% subsamples, naive | +13.4% | [+3.1%, +23.7%] | **0.004** |
| 80% subsamples, naive | +13.5% | [+5.4%, +21.4%] | **0.000** |
| 70% subsamples, rescaled | +13.5% | [+1.4%, +25.9%] | — |
| 80% subsamples, rescaled | +13.5% | [+4.7%, +22.6%] | — |

The naive 80% procedure reports **p < 0.001** on data whose honest p is
0.044. It would have turned a marginal result into an apparently
overwhelming one.

## Why

**Resampling cannot create information.** The uncertainty comes from having
396 markets of which ~20 carry the return. Every subsample is drawn from
those same 396. The mean of the subsample estimates returns +13.5% — the
full-sample point estimate — because that is what averaging does. It adds
nothing.

**The spread of subsample means is not the standard error.** A subsample of
size *m* has roughly √(n/m) times the standard error of the full sample, so
the spread of many subsample means is much *tighter* than the true sampling
distribution. Reading significance off that spread understates uncertainty
by exactly that factor.

Subsampling *is* a legitimate technique — Politis & Romano's m-out-of-n
theory supports valid inference — but only with an explicit rescaling by
√(m/n). Rescaled, the last two rows above reproduce the bootstrap. **There
is no free significance in any resampling scheme**; the ordinary bootstrap
already extracts what the 396 markets contain.

## What the data does support

### The concentration is about return, not sizing

A reasonable hope: maybe the top 5 markets dominate because the ladder
deployed more capital into them, in which case it is a sizing artefact
rather than luck.

It is not.

| | share |
|---|---|
| top 5 markets' share of **capital** | **4.4%** |
| top 5 markets' share of **PnL** | **57.5%** |
| their mean return | **+174%** |
| median return across all markets | +42.9% |

Capital Gini 0.51, PnL Gini 0.55. Five markets on 4.4% of the money
produced 57.5% of the profit by returning +174%. That is a return effect —
five exceptional resolutions, not five oversized bets.

### Equal-weighting removes sizing entirely

| estimator | result |
|---|---|
| capital-weighted (headline) | +13.5% [−2.1%, +28.9%] p=0.044 |
| **equal-weighted per market** | **+7.8% [−2.5%, +18.1%] p=0.069** |

Half the headline, and not significant.

### Out-of-time split — the honest replication test

Split at the median entry date, 198 markets each side:

| period | return | interval | p |
|---|---|---|---|
| first half | **+6.1%** | [−13.6%, +26.0%] | 0.274 |
| second half | **+19.8%** | [−2.9%, +42.4%] | 0.041 |

The edge is **not stable across halves**. A three-fold difference with the
first half insignificant is what an unstable or absent edge looks like as
easily as a real one. This is the closest thing to a replication test the
existing data allows, and it does not replicate.

## What would actually help

1. **More markets.** New information, not rearranged information. The
   cluster trades continuously, so a further six months is ~200 more
   markets and costs only time.
2. **Genuine out-of-sample.** Fix the rules now, watch forward, do not
   look. The time split above is the retrospective version and is weaker
   because the rules were chosen after seeing everything.
3. **A mechanism.** Entries cluster 30 minutes before kickoff, which is
   when lineups drop. If that is the edge it is testable directly — does
   the cluster trade *after* lineup announcements specifically? A confirmed
   mechanism justifies believing a point estimate the interval does not
   support; without one the interval is the honest read.
