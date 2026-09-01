# Blind test 2: topic rules instead of account rules

**Committed before any search.** Same discipline as the first blind test:
the rules and the quality thresholds are fixed here, the test runs once.

## Why topic rules

The first blind test scored 0/10. A third of those markets repriced on
accounts nobody could have enumerated -- a Beijing filing approval surfaced
by a 277-follower account, a report in The Information relayed by
aggregators. Account lists cannot be written in advance for those. A keyword
rule catches whoever happens to be carrying it.

The cost is noise, and noise is what the gate is for.

## Quality filtering: what X actually supports

Tested against the live API:

- `is:verified` — **works**. Weak now that verification is purchasable, but
  it is free to apply in the rule and cuts obvious spam.
- `min_faves:` / `min_retweets:` — **rejected, HTTP 400**. Not available.
- `lang:en`, `has:links`, `-is:retweet` — all work.

So follower filtering has to happen **after** delivery, from
`user.fields=public_metrics`. That does not save the $0.005 per post, but it
removes the LLM call and, more importantly, the false alarm.

Retweets are deliberately **kept**. Excluding them lost Fabrizio Romano's
signal in the first test.

## Rules (fixed)

| # | market | rule |
|---|---|---|
| 1 | Andy Burnham visits Ukraine | `(Burnham) (Kyiv OR Ukraine OR visit)` |
| 2 | Cap launches a token | `(Cap OR $CAP) (token OR TGE OR airdrop OR launch)` |
| 3 | Squid launches a token | `(Squid OR $SQUID) (token OR TGE OR airdrop OR launch)` |
| 4 | Citrea launches a token | `(Citrea OR $CBTC) (token OR TGE OR airdrop OR mainnet)` |
| 5 | SpaceX added to Nasdaq-100 | `(SpaceX) (Nasdaq OR index OR listing)` |
| 6 | Arcium launches a token | `(Arcium OR $ARX) (token OR TGE OR airdrop)` |
| 7 | Maia Sandu visits Ukraine | `(Sandu) (Kyiv OR Ukraine OR visit)` |
| 8 | OBJ signs with a team | `(OBJ OR "Odell Beckham") (sign OR signs OR signed OR agrees)` |

Rule 2 is knowingly weak: "Cap" is a common English word and will pull
enormous noise. It is left in rather than quietly improved, because a
strategy that needs every rule hand-tuned by someone who already knows the
answer is not a strategy. How badly it fails is part of the result.

## Thresholds to be swept (fixed in advance)

Follower minimums of **0, 10k, 50k, 250k**, reported at each. Sweeping a
pre-declared set is not the same as picking the best number afterwards.

## Scoring

A market is a HIT if, among posts matching the rule in the 24 hours BEFORE
the market repriced and clearing the follower threshold, at least one passes
the gate. Anything after the repricing is not a signal.

## Prediction

Recall should improve on 0/10 -- the aggregator cloud is now inside the net.
Precision is the open question, and the follower threshold is the only
instrument for it. My guess is that 10k removes most junk while keeping the
breakers, and that rule 2 fails regardless of threshold.

## If it works: two-tier firing

A principal on the watch list posting a gate-passing announcement is a
different quality of signal from an unknown account matching a keyword. The
two should not be sized alike:

- **principal + gate pass** -> full aggression, full size
- **keyword match + gate pass, above threshold** -> reduced aggression,
  reduced size

That is only worth building if this test shows the keyword tier catches
things the account tier missed.
