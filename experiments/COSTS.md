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

## X API: $0.005 per post read

Confirmed from the docs. Pay-per-usage, **no subscription** — my earlier
$200/$5,000 tier figures were simply wrong. Credits are bought upfront and
deducted per resource returned; pay-per-usage is capped at 3M post reads a
month, far above anything needed here.

The bill is therefore set by **how chatty the watched accounts are**, not by
how many markets are watched. Musk at ~50 posts/day costs $7.50/month on his
own; a crypto project posting three times a day costs $0.45.

| watch list | posts/mo | X $/mo | +LLM | total |
|---|---:|---:|---:|---:|
| 200 accounts, everything | 48,000 | $240 | $7 | **$247** |
| 50 accounts, everything | 12,000 | $60 | $2 | $62 |
| 20 accounts, everything | 6,000 | $30 | $1 | $31 |
| 50 accounts, keyword-filtered rules | 960 | $5 | $0 | **$5** |
| 20 accounts, keyword-filtered rules | 480 | $2 | $0 | **$2** |

## The optimisation that matters: filter in the stream rule

Filtered-stream rules take 1,024 characters and you get 1,000 of them, so the
relevance test belongs in the rule rather than only in the LLM:

    from:megaeth_labs (token OR TGE OR mainnet OR launch)

You are then billed only for posts that match. Musk posts ~50 times a day but
mentions FSD perhaps weekly, so the saving is roughly an order of magnitude —
and it cuts LLM calls by the same factor, since only matching posts get
scored. Two birds.

The keyword filter must stay deliberately loose. A rule that is too tight
misses the announcement outright, and a miss costs the whole trade whereas a
false match costs half a cent and one cheap LLM call. Asymmetric, so err wide.

## What this does to the economics

| size/fire | gross @13.6% | gross @49.8% | vs $5/mo running cost |
|---:|---:|---:|---|
| $10 | $24 | $88 | profitable at both |
| $25 | $60 | $220 | profitable at both |
| $50 | $120 | $439 | profitable at both |
| $100 | $240 | $878 | profitable at both |

At 20 keyword-filtered accounts the whole thing runs for about **$5 a
month**, so it clears its costs even at $10 a fire and the honest ROI. The
earlier conclusion — that the strategy could not pay for its own data — was
an artefact of my wrong pricing model and is withdrawn.

Costs are no longer the constraint. The constraints are the ones already
measured: ~25 fires a month, thin fills, and an edge that has never been
demonstrated at p<0.05.
