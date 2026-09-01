# What it costs to run, per month

Fire rate is measured, not assumed: 101 principal-announceable markets that
did not depend on Trump resolved YES over 120 days, so **~25 fires/month**.
At $10 a fire and ~70% fill that is **$176/month of capital deployed**.

## LLM: not the problem

~200 watched accounts averaging 8 posts/day, each scored against ~1.2
markets, is **~57,600 gate calls/month** — 28.8M input tokens, 3.5M output.

| model class | $/month |
|---|---:|
| mini / flash | **$6** |
| mid | $20 |
| frontier | $138 |

The cheap fast model the strategy calls for costs about **$6/month**. Even a
frontier model would not decide anything. Ignore this line item.

## X API: corrected — my tier figures were stale

I costed this from remembered $200/$5,000 subscription tiers. Checking the
live docs (`docs.x.com/llms.txt` serves markdown, unlike the JS-rendered
portal), that framing looks wrong:

- The rate-limit reference has **no tier breakdown at all** — just
  per-endpoint limits, consistent with usage-based pricing.
- **Filtered stream is not shown as gated**: `/2/tweets/search/stream`
  allows **1,000 rules**, one connection, 250 posts/sec. A thousand rules
  covers 200 accounts many times over.
- **Full-archive search is likewise ungated** in the limits table (1/sec,
  300/15min) — which also means the backtest I earlier called Pro-only may
  be reachable.
- The docs explicitly say *"For real-time data, use filtered stream instead
  of polling"*, confirming the architecture.
- There is **no pricing page in the docs index**; cost lives in
  `console.x.com`, behind a login. So the rate still needs checking there.

The right way to hold this is therefore not a fixed bill but a budget: what
can the strategy afford to pay?

## What the strategy can afford

Gross profit at ~25 fires/month and 70% fill:

| size/fire | deployed/mo | @13.6% ROI | @49.8% ROI |
|---:|---:|---:|---:|
| $10 | $176 | $24 | $88 |
| $50 | $882 | $120 | $439 |
| $100 | $1,764 | $240 | $878 |
| $250 | $4,410 | $600 | $2,196 |

And the volume to be served, which is what usage pricing bills against:

| accounts watched | posts/month |
|---:|---:|
| 200 | 48,000 |
| 50 | 12,000 |
| 20 | 6,000 |

At 50 accounts (12,000 posts/month), the affordable rate per 1,000 posts:

| | @13.6% | @49.8% |
|---|---:|---:|
| $10/fire | $2.00 | $7.32 |
| $50/fire | $10.00 | $36.60 |
| $100/fire | $19.99 | $73.21 |

## The question that decides it

Not "which tier" but **what does X charge per post delivered**, checkable in
`console.x.com`. Read it off and compare against the table above.

If the rate is single-digit dollars per thousand posts, a 50-account watch
list is affordable even at $10 a fire. If it is tens of dollars per
thousand, the fix is fewer accounts rather than more capital, since volume
is the thing being billed and it is concentrated in a handful of prolific
accounts that mostly post noise.

## The way to make it fit

Volume drives the API bill, and it is concentrated: a handful of accounts
generate most of the traffic while a handful of markets carry most of the
value. Watching the **20 best accounts instead of 200** cuts reads roughly
tenfold — bringing ~4,800 posts/month, which plausibly fits a cheap tier —
while keeping the largest markets. Fewer fires, each sized larger, is the
shape that survives the arithmetic.

At $10 a fire the answer is simply no: the data costs an order of magnitude
more than the strategy makes.
