# What the blind-test-2 hits would actually have paid

Computed from tapes already in `.polycache`. No API calls.
Reproduce with `python3 experiments/hit_pnl.py`.

## First, a correction to how blind test 2 was scored

`blind2.py` located each market's "repricing" as **the first print at
ref ≥ 0.90 that held six hours**. That is not a news jump — for a market
that opens high it is just the market's first print. Running the real
detector (`jumps.detect`) over the same tapes:

| market | blind2 "repricing" | nearest real jump | post vs. jump |
|---|---|---|---|
| Squid | first print at 0.90 | one jump, 32 days later | post predates the whole tape |
| Burnham | drift through 0.90 | 0.84→0.93 | post falls **between** two jumps |
| OBJ | 0.60→0.98, genuine | 0.60→0.98 | post at **+0.0h** — on the onset |

So blind test 2's 3/8 measures **whether the rule caught a post about the
story**. That is real, and it is still 3 against blind test 1's 0. It does
**not** measure whether the story was tradeable, and the two were conflated
when the result was first reported.

## Did the signal win? Yes, 3 for 3.

All three markets resolved YES, and all three were priced below 1.0 when
the post landed. Direction was right every time.

## Could the trade be made? Once, for $10.

| market | lifetime volume | price at post | prints in next 10 min | best demonstrable fill |
|---|---|---|---|---|
| Squid | $11,293 | — | — | **untradeable**: post lands 3.3h before the market's first ever print |
| OBJ | $3,521 | 0.600 (13.1h stale) | 2 | **no fillable liquidity** at any cap or window |
| Burnham | $5,634 | 0.890 (38.1h stale) | 0 | $94 at a 2c cap, resting to close |

### Burnham, the only one with a fill

Resting from the post to market close, taking only prints that actually
executed on our side inside the cap:

| aggression | fillable | vwap | PnL | ROI |
|---|---|---|---|---|
| 1c | $18 | 0.890 | $2 | 12% |
| **2c** | **$94** | 0.906 | **$10** | 10% |
| 5c | $578 | 0.928 | $45 | 8% |
| 10c | $2,457 | 0.960 | $102 | 4% |

**To make $100 you need 10c of aggression and ~$2,500 resting to close in a
market with $5,634 of lifetime volume** — i.e. you become 44% of everything
that market ever traded, at a price 7 cents through the pre-news level, and
you clear 4%.

At the desk's configured sizes the numbers are: tier 2 ($3 at 2c) → **$0.31**.
Tier 1 ($10 at 5c) → **$0.78**.

And Burnham is the flattering case. The market was already at 0.89 when the
post landed and the post sits between two jumps, so that $10 is not news
alpha — it is buy-at-0.89-and-hold-to-resolution. The strategy gets no
credit for it.

## What this actually says

Signal quality is not the binding constraint. Depth is.

Three markets where the net caught the breaking post and the direction was
right, and the aggregate demonstrable PnL is about ten dollars. The rules
work; the markets carrying these stories have $3.5k–$11.3k of lifetime
volume and cannot absorb the desk's own ticket, let alone pay for an X
subscription and a gate call per post.

### The fill numbers are a lower bound

`simulate_fill` consumes only prints that demonstrably executed — no
historical order books exist, so every resting offer nobody hit is
invisible to it. Real fills would be better. But gamma's reported volume
($5.5k–$17k lifetime, and that double-counts sides) says the correction is
a factor, not an order of magnitude. A market with $5k of lifetime volume
does not have $50k of hidden depth.

## The change this justifies

`discover.screen()` flagged thin books but never dropped one, and its
"little volume" flag fired below $1,000 — every market here cleared it
comfortably. It now takes `min_volume` (default $25,000) as a **hard drop**.

The default is a judgement call off three observations, not a fitted
threshold, so it is an argument rather than a constant. The honest test is
whether markets above it exist in enough number to be worth running the
desk for — which the next discovery sweep answers, and which is now the
open question rather than "does the gate work".
