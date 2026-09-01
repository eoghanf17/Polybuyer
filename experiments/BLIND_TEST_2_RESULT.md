# Blind test 2: keyword rules — result

Rules and thresholds were fixed in `KEYWORD_RULES.md` and committed at
`bdcc5e1` before the first search ran. Nothing below was tuned afterwards.

## Headline

| follower floor | markets hit | posts that reached the gate |
|---|---|---|
| 0 | 4/8 | 288 |
| **10,000** | **3/8** | **39** |
| 50,000 | 2/8 | 15 |
| 250,000 | 1/8 | 4 |

Blind test 1, using hand-enumerated account lists, scored **0/10**.

## The 4/8 at threshold 0 is really 3 + 1

Reading the four posts that fired:

| market | account | followers | post | verdict |
|---|---|---|---|---|
| Burnham visits Ukraine | @Mario19940 | 757 | RT of @SprinterPress: "Macron, Merz, and Burnham will arrive in Kyiv on August 24th…" | real |
| Squid launches a token | @squidrouterETH | 486 | "The $QUID Season 1 Airdrop Claims go Live June 30 at 1:00pm UTC" | real |
| Arcium launches a token | @Jeffery_xbt | 106 | "They picked the best approach tbh. Shipped / let teams build useful everyday…" | **false alarm** |
| OBJ signs with a team | @GoatHouseNFL | 24,566 | "#Giants signed OBJ, per @MikeGarafolo. He's back!" | real |

The Arcium fire is a conversational reply with no announcement in it. The
gate should have dropped it and did not.

At a 10k floor the false alarm disappears and all three genuine signals
survive — @SprinterPress (797k) replaces the retweeter on Burnham,
@legiondotcc (96k) replaces the project's own small account on Squid,
@GoatHouseNFL (24.5k) is unchanged. That is the finding: **the follower
floor removed the only false positive without costing a single hit**, and
cut gate calls 288 → 39.

50k and 250k both lose real signal (@GoatHouseNFL, then @legiondotcc) and
buy nothing. 10k is the pre-declared value that happens to be right; it was
not chosen after the fact.

## The misses

- **Cap** — the deliberately weak rule (`Cap OR $CAP`). 45 posts of noise,
  no hit at any threshold. Predicted in the pre-registration, confirmed.
- **Citrea** — 19 posts, none an announcement.
- **SpaceX / Nasdaq-100** — 55 posts, no hit at any floor. Index additions
  are announced by a Nasdaq press release, not on X.
- **Maia Sandu** — **0 posts matched the rule at all**. Nothing was said on
  X in the 24h before the market repriced.

Two of the four misses are markets where no X post existed to be caught.
That is blind test 1's enumerability finding restated in a different form:
the ceiling on this strategy is not rule quality, it is that a material
share of markets do not break on X.

## What the precision number does and does not show

Across the five markets that missed at the 10k floor, **22 eligible posts
were gated and none fired**. Those are 22 clean rejections of ordinary
topic chatter — the only direct evidence available that the gate does not
fire on noise.

Two limits on that, both structural:

1. **The harness stopped at the first pass.** On the three markets that
   hit, the remaining eligible posts were never gated, so false alarms are
   undercounted by construction. 22/22 is a lower bound on the rejection
   rate, not a measured precision.
2. **Order is reversed relative to live operation.** `search/all` returns
   newest-first, so the recorded hit is the *last* passing post before the
   repricing. A live stream sees posts oldest-first and would fire on an
   *earlier* one — plausibly a weaker one. Recall transfers (a pass is a
   pass in either order); the specific post and its latency do not.

Fixing either costs more X reads on markets already searched, and buys
less than running the tier live in $3 size would.

## Verdict

The keyword tier catches signal the account tier missed — 3 markets to 0 —
and the quality floor is a real instrument rather than a knob that trades
recall for precision at these levels. That is enough to build the two-tier
firing design, with the tier-2 sizing set by how thin the precision
evidence is rather than by the recall number.

## Cost

~496 posts read across all three experiments (blind test 1, gate
calibration, blind test 2) ≈ **$2.48** at $0.005/post, plus gate calls.
No further searches were run to produce this document.
