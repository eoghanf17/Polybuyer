# The FootballFan98 cluster: full study

Everything this project has established about the cluster, its trading, and
whether it can be copied. Scripts: `ff_timeline.py` (simulation),
`ff_verify.py` (statistics), `ff_cluster_evidence.py` (membership, timing,
fills). Results: `ff_timeline.json`, `ff_series.json`, `ff_verify.json`,
`ff_cluster_evidence.json`.

> **Verdict up front.** The ladder returns +12.6% to +15.7% on recorded
> liquidity, marginally significant (p = 0.031–0.044). Dropping the best 5
> markets halves it to +6–7% at p ≈ 0.18 — but that cut is deliberately
> one-sided. A **symmetric trim** of the best *and* worst 5, which is the
> unbiased version, leaves it essentially unchanged at **+12.2% to +15.1%**
> and *improves* significance. The tails nearly cancel: best 5 = +57% of
> net PnL, worst 5 = −44%, and **the middle 386 markets carry 87%**.
>
> The real weaknesses are elsewhere: the intervals straddle zero, the
> out-of-time halves disagree (+6.1% vs +19.8%), and the lineup mechanism
> is refuted — the cluster trades when the book is deep, not on team news.

---

## 1. The cluster

Four wallets, pinned in `polybuyer/targets.py`. Verified as a **closed
network** on 2026-09-02 — all 6 pairs connected by direct on-chain
transfers, every member degree 3, 5 of 6 edges carrying USDC.

| handle | address | volume | rank | PnL |
|---|---|---|---|---|
| FootballFan98 | `0xc31d0a0d63d760d72a1236d16beaa6a71c854ebe` | $45.4M | #519 | **−$1.07M** |
| (unnamed) | `0x006cc834cc092684f1b56626e23bedb3835c16ea` | $64.9M | #324 | **+$4.72M** |
| Airpods123 | `0xb90494d9a5d8f71f1930b2aa4b599f95c344c255` | $40.0M | #583 | +$1.02M |
| RBax | `0x4366ab8b8b27e4139d94a532e3cec94a83d1c73e` | $2.8M | #7,882 | +$91K |
| **combined** | | | | **+$4.76M** |

| pair | transfers | of which USDC |
|---|---|---|
| (unnamed) ↔ RBax | 70 | 12 |
| (unnamed) ↔ FootballFan98 | 65 | 55 |
| (unnamed) ↔ Airpods123 | 36 | 36 |
| RBax ↔ Airpods123 | 16 | 12 |
| RBax ↔ FootballFan98 | 14 | 0 |
| Airpods123 ↔ FootballFan98 | 13 | 8 |

The unnamed wallet is the hub on every measure — most transfers to each of
the other three, largest USDC flows, and essentially all the profit.

**Provenance caveat.** Volume, rank and PnL are as displayed by Polymarket
and supplied by the account owner; they are not independently measured
here. What *is* measured: 365-day traded notional from trade history comes
to 45%, 47%, 46% and 31% of the stated lifetime figures respectively. Three
of four landing in the same narrow band is a strong check that the
addresses are correct — a wrong address would not.

### Rediscovery does not work

Four approaches failed before the addresses were supplied directly, and the
reasons are recorded in `newsdesk.learnings` so nobody repeats them:
`fetch_and_build` only merges wallets already in the seed set;
`find_siblings` is blind because Blockscout serves only the most recent
10,000 transfers (two months here) and the founding USDC transfers are
older; the funding counterparties in that window are shared deposit hubs
touching 5,564 addresses; and co-occurrence across 96 tapes was diffuse.
Every candidate set formed a **star**, never the closed network above.

---

## 2. What the cluster trades

365-day intake: **41,728 prints, $69.4M notional, 1,533 markets**.

| wallet | prints | notional |
|---|---|---|
| FootballFan98 | 21,978 | $20.2M |
| (unnamed) | 6,291 | $30.3M |
| Airpods123 | 7,038 | $18.3M |
| RBax | 6,449 | $0.87M |

### It is pre-match football, not in-play

| when the cluster entered | positions |
|---|---|
| 0–2h before kickoff | **301** |
| 2–24h before | 70 |
| >24h before | 2 |
| after kickoff (in-play) | **19** |
| no kickoff time | 4 |

**373 of 392 (95%) entered before kickoff**, median **+0.5h**. Official
team lineups land about an hour before kickoff, which is the window most of
these sit in — consistent with trading team news, though nothing here
establishes that.

An earlier version of this document called it 392-of-396 in-play and
dismissed it as a broadcast latency race. That was wrong: the flag came
from `game_start_time` being *present*, which only says the market is
**about** a scheduled match. `Resolution.game_start_ts` now makes the
distinction measurable.

---

## 3. The copy strategy

Signals are the cluster's **combined** position per market — the four
wallets merged into one trade sequence before the first-above-$10k entry is
taken — with all four excluded from follower liquidity. Fills come only
from prints that actually executed, inside a 2c cap and 10-minute window.

| ladder | positions | deployed | peak exposure | PnL | return |
|---|---|---|---|---|---|
| $50 → $1,000 | 396 | $93,022 | **$4,561** | +$11,755 | +12.6% |
| $250 → $5,000 | 396 | $393,315 | **$21,614** | +$53,193 | +13.5% |
| $500 → $10,000 | 396 | $698,923 | **$40,477** | +$109,993 | +15.7% |

Peak concurrent exposure is roughly a twentieth of cumulative deployment —
positions are short and capital recycles. Exposure is live on 181 of 318
days.

### The fills are credible

Order as a share of same-side executed volume in its window:

| ladder | median | p90 | took everything |
|---|---|---|---|
| $50 → $1,000 | **0.3%** | 7.1% | 0.4% |
| $250 → $5,000 | ~1% | 26% | 1% |
| $500 → $10,000 | ~2% | 39% | 1% |

Median 68 counterparty prints per window. Two limits: **no market impact is
modelled**, and the prints consumed were taken by someone else, so in
reality we would compete for them. Both point at the largest ladder as the
least trustworthy.

---

## 4. Statistics — where it falls down

Cluster bootstrap over markets (4,000 resamples, `min_clusters=20`):

| ladder | all markets | drop best 5 | pre-match only |
|---|---|---|---|
| $50 → $1,000 | +12.6% [−1.5%, +27.2%] p=0.041 | **+6.3% p=0.179** | +11.9% p=0.060 |
| $250 → $5,000 | +13.5% [−2.1%, +28.9%] p=0.044 | **+6.0% p=0.206** | +12.4% p=0.071 |
| $500 → $10,000 | +15.7% [−0.9%, +31.8%] p=0.031 | **+7.4% p=0.171** | +14.4% p=0.052 |

Three things this says, none of them in the point estimates:

1. **Every interval includes or nearly includes zero.** Marginal
   significance at best.
2. **Concentration is real but two-sided.** Removing the best 5 of 396
   halves the return and destroys significance — but that cut removes the
   right tail only. The left tail is nearly as large: best 5 = +57% of net
   PnL, worst 5 = **−44%**, so the extremes net to +13% and the middle 386
   markets carry **87%**. A symmetric trim leaves the result intact. See
   §4b. Only 214 of 396 markets (54%) are profitable, which is normal for
   a strategy whose winners pay more than 1:1.
3. **Pre-match alone is not significant** (p = 0.052–0.071), and pre-match
   is 95% of the strategy.

The in-play (n=19) and non-match (n=4) segments are **underpowered** — the
bootstrap cannot produce a meaningful interval, and their point estimates
(+26.7%, −18.4%) should not be quoted. They were, earlier in this project,
and that was an error.

### 4b. Robustness cuts, with dollars

$250 → $5,000 ladder:

| cut | PnL | deployed | return | 95% interval | p |
|---|---|---|---|---|---|
| full sample | **+$53,193** | $393,315 | +13.5% | [−2.1%, +28.9%] | 0.044 |
| drop best 5 | **+$22,632** | $375,951 | +6.0% | [−8.4%, +20.0%] | 0.206 |
| winsorise top 5 | **+$44,742** | $393,315 | +11.4% | [−3.7%, +26.1%] | 0.064 |
| **trim best + worst 5** | **+$46,085** | $352,498 | **+13.1%** | [−1.3%, +27.1%] | **0.036** |

The same shape holds on the other two ladders; on $500 → $10,000 the
symmetric trim gives +15.1% [+0.6%, +29.1%] at **p = 0.020**, better than
the full sample.

**Why the two cuts disagree.** "Drop the best 5" removes the five largest
contributors by construction, so it is biased low by as much as the full
sample is biased high by whatever luck those five contain. Winsorising —
capping the top 5 at the sixth-largest outcome, keeping the markets and
their capital — costs only 2 points. The symmetric trim costs almost
nothing.

**Tail decomposition ($250 → $5,000):**

| | PnL | share of net |
|---|---|---|
| best 5 markets | +$30,561 | +57% |
| worst 5 markets | **−$23,453** | **−44%** |
| net of both tails | +$7,108 | +13% |
| **middle 386 markets** | **+$46,085** | **87%** |

An earlier version of this document said the top 5 carried the profit and
the rest was net negative. That was arithmetically true of the right tail
alone and misleading: the left tail destroys nearly as much, and the bulk
of the return comes from the middle.

---

## 5. What would settle it

- **More history.** 396 markets over one year is the whole sample. The
  concentration problem may be sample size rather than absence of edge.
- **Out-of-sample.** Fit nothing, take the next three months as they come.
- **A mechanism.** "Trades 30 minutes before kickoff" is consistent with
  lineup news but unverified. A mechanism would justify believing the
  point estimate over the confidence interval; without one, the interval
  is the honest read.

## 6. Status

Not recommended for live capital on this evidence. The result is positive
and could be real, but it rests on twenty resolutions and does not survive
the project's own concentration screen — the same screen that exists
because an earlier wallet scored +40.0% off 11 markets and came back +8.9%
on its full history.
