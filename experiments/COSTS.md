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

## X API: the whole problem

Gross profit at $10 a fire, using the two ROIs actually measured:

| | gross/month |
|---|---:|
| honest (all-alarms) +13.6% | **$24** |
| persistent-only +49.8% | **$88** |

So the strategy generates **$24–88/month** at $10 size, against an X bill
with a floor around $200/month. It cannot pay for its own data.

Size needed per fire just to break even on data:

| X tier | at 13.6% | at 49.8% |
|---|---:|---:|
| ~$200/mo cheapest paid | **$88** | $24 |
| ~$5,000/mo Pro | $2,088 | $570 |

## The question that decides it

**Is the filtered stream available below Pro?** I could not confirm — X's
pricing pages are JavaScript-rendered and unreadable from here, so this needs
checking before anything is built.

- If **yes**, and polling or streaming fits inside a ~$200 tier, the strategy
  needs roughly **$90 a fire** rather than $10. That is ~$2,250/month of
  deployed capital across 25 fires, which these markets can absorb.
- If **no**, and the stream is Pro-only, break-even is **$570–2,088 per
  fire**. The markets in this universe run $150k–3M of lifetime volume and
  fill thinly; that size cannot be deployed on a single headline. The
  strategy would be dead at any size it can actually trade.

## The way to make it fit

Volume drives the API bill, and it is concentrated: a handful of accounts
generate most of the traffic while a handful of markets carry most of the
value. Watching the **20 best accounts instead of 200** cuts reads roughly
tenfold — bringing ~4,800 posts/month, which plausibly fits a cheap tier —
while keeping the largest markets. Fewer fires, each sized larger, is the
shape that survives the arithmetic.

At $10 a fire the answer is simply no: the data costs an order of magnitude
more than the strategy makes.
