# Backtesting an X-fired strategy without paying for the firehose

Correcting two things I said earlier, then what actually works.

## Correction 1: it is Pro, not Enterprise

X API v2 full-archive search sits in the **Pro** tier (~$5,000/month), not
Enterprise. Enterprise is a further tier above it. Pro is a self-serve
product, and a backtest needs one month of it, not a standing contract. So
the paid path is ~$5k one-off, not a bespoke negotiation.

## Correction 2: free substitutes exist, and one is verified working

### GDELT — verified from this session

`https://data.gdeltproject.org/gdeltv2/YYYYMMDDHHMMSS.export.CSV.zip`

Fetched a slice from inside the test window and parsed 1,514 events with
source URLs. Free, no key, complete rather than sampled, global.

**Resolution: 15 minutes.** `DATEADDED` carries one stamp per batch file, so
every event in a slice shares a timestamp. It cannot resolve 2s from 45s.

That matters less than it sounds, and this is the point: the experiment
found latency is *not* the binding constraint. What killed the strategy was
a 24% false-alarm rate costing 36 points of ROI, and measuring that needs
only "did a news event occur near this market move" — which 15-minute
resolution answers fine. **The free data addresses the question that
matters; the $5k data addresses the one that turned out not to.**

`mentions.CSV` and `gkg.csv` from the same path add per-article coverage and
entity/theme tagging, useful for category matching and for estimating
direction accuracy from headline text.

### Wikipedia revisions — verified from this session

MediaWiki API, second-precision timestamps, free, complete history. For
events notable enough to have an article, editors update within minutes of a
break. Good for the big geopolitical moves; useless for corporate minutiae.

### Common Crawl News

`data.commoncrawl.org` — per-article publish timestamps, free, very large.
Finer than GDELT but needs real processing.

### Internet Archive Twitter Stream Grab

Monthly archives of the **1% sample**. For a named account's specific
breaking tweet, a 1% sample will almost certainly miss it, so this cannot
support account-level backtesting. It can measure aggregate volume spikes.

## The path I would actually take

**Forward collection.** The free tier gives 7-day recent search; Basic
($200/month) gives more headroom. Run a collector against the frozen account
list, log every hit with a timestamp, and paper-trade against live
Polymarket prices.

Costs time rather than money, and it is the only method that produces the
two things nothing else can:

- **real account attribution** — which handle actually broke it first, the
  thing the strategy's account list currently asserts without evidence;
- **a real false-alarm rate** — how often those accounts fire on something
  that never moves the market.

Rate of accrual, from the test half: 208 target-category markets produced
636 alarms across roughly nine months, so about **70 signals a month**.
Reaching the ~500 signals this experiment needed for power means **six to
eight months** of forward collection. That is the genuine cost, and it is
paid in patience.

## What to conclude

There is no free way to measure sub-minute tweet-to-market latency. There
is also no reason to: the market takes two to four minutes to reprice, 2s
and 45s tested identically, and the cliff sits between 45s and 120s. Buy
the $5k month only if you want to confirm a result the tape has already
made unlikely to matter.
