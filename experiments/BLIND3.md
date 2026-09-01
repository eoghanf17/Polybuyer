# Blind test 3: does a tradeable market have a findable post?

**Committed before any search.** Same discipline as tests 1 and 2.

## What changed

The first two tests searched X for markets chosen because they *resolved*.
Blind test 2 found the breaking post in three of eight and the trade was
worth about ten dollars, because those markets had $3.5k–$11.3k of lifetime
volume. Signal was never the constraint; depth was.

So the selection is inverted here. 315 resolved markets were screened on
tape alone, for free, and only markets that pass **all** of the following
are searched:

1. not sports, in-play, scheduled-settlement, or off-platform
2. gamma volume ≥ $25,000
3. a persistent repricing from a stable baseline (`jumps.detect`)
4. **≥ $200 fillable at a 5c cap in the 30 minutes after the onset**
5. the don't-chase guards pass at the onset

That left 35 markets and 45 resolving repricings carrying **$191k** of
demonstrable PnL, against 11 head fakes at −$19k. These are markets where
a trade provably existed. The open question is whether the post that caused
it was findable.

## Cost control

The onset timestamp comes from the tape, so the search window is
**[onset − 2h, onset]** rather than 24 hours, at `max_results=25`.

This is a real trade-off, stated in advance: a signal that leads the market
by more than two hours is invisible to this test. Blind test 2's Burnham
post led by 8 hours. Accepting that blind spot is what makes the test
affordable — 20 markets × 25 posts ≈ **$2.50**.

Markets sharing a rule with overlapping windows are searched once and
scored twice (the two Romanian election markets have onsets four minutes
apart).

## Excluded on judgement, not on data

Crude Oil $105/$110 and "Bitcoin dip to $60,000" are in the candidate set
and are dropped here. They resolve on a price print, not an announcement;
there is no post to find, and paying to confirm that is waste.

## Rules (fixed)

| # | market | onset | rule |
|---|---|---|---|
| 1 | US strikes Iran by Feb 28 | 2026-02-28T06:17 | `(Iran) (strike OR strikes OR struck OR attack OR bomb OR military action)` |
| 2 | US strikes Iran by Feb 23 | 2026-02-18T20:55 | same as 1 |
| 3 | US strikes Iran by Jan 16 | 2026-01-14T20:02 | same as 1 |
| 4 | US or Israel strike Iran by Jan 31 | 2026-01-15T12:25 | same as 1 |
| 5 | Nicușor Dan wins Romanian presidency | 2025-05-18T17:49 | `(Romania OR Romanian) (election OR exit poll OR wins OR won OR president)` |
| 6 | George Simion wins Romanian presidency | 2025-05-18T17:53 | same as 5 |
| 7 | Starmer out by June 30 | 2026-06-19T02:21 | `(Starmer) (resign OR resigns OR resignation OR quit OR out OR ousted)` |
| 8 | lighter airdrop by Dec 31 | 2025-12-30T04:48 | `(lighter OR $LIGHTER) (airdrop OR claim OR live OR TGE OR token)` |
| 9 | Lighter airdrop on Dec 29 | 2025-12-29T04:02 | same as 8 |
| 10 | Government shutdown on Saturday | 2026-02-13T09:44 | `(shutdown) (government OR Senate OR House OR funding OR bill OR vote)` |
| 11 | MegaETH >$1.2B public sale | 2025-10-29T21:37 | `(MegaETH OR $MEGA) (sale OR raise OR committed OR public sale OR allocation)` |
| 12 | MegaETH FDV >$2B after launch | 2026-05-01T02:06 | `(MegaETH OR $MEGA) (FDV OR market cap OR launch OR listed OR live)` |
| 13 | Epstein suicide note released by May 8 | 2026-05-11T19:41 | `(Epstein) (note OR document OR release OR released OR files)` |
| 14 | US–Iran nuclear deal by June 30 | 2026-06-11T17:24 | `(Iran) (deal OR agreement OR nuclear OR talks OR signed)` |
| 15 | US–Iran permanent peace deal | 2026-06-14T21:15 | same as 14 |
| 16 | US x Iran meeting by April 10 | 2026-04-09T14:17 | `(Iran) (meeting OR meet OR talks OR negotiations OR summit)` |
| 17 | Finland wins Eurovision 2026 | 2026-05-16T22:11 | `(Eurovision) (Finland OR wins OR won OR winner OR points)` |
| 18 | Party for Freedom wins most seats | 2025-10-28T15:03 | `(Netherlands OR Dutch OR PVV OR Wilders) (election OR exit poll OR seats OR wins)` |
| 19 | Israel x Hezbollah ceasefire by Apr 18 | 2026-04-16T17:53 | `(Hezbollah OR Lebanon) (ceasefire OR truce OR agreement OR deal)` |
| 20 | Israel x Hezbollah ceasefire by Apr 15 | 2026-04-15T21:26 | same as 19 |
| 21 | Iran x Israel/US conflict ends by Jun 30 | 2026-04-07T22:22 | `(Iran) (ceasefire OR truce OR ends OR ended OR peace)` |

## Thresholds

Follower floor **10,000**, the value blind test 2 measured. Reported at
0 and 10k only — 50k and 250k both lost real signal there and are not
re-run.

## Scoring

A market is a **HIT** if a post matching the rule, inside the window, above
the floor, passes the gate.

For every hit, PnL is then computed **entering at the post's own
timestamp** — not the onset. This is the first test that can say anything
about the don't-chase guards, because it is the first where entry can be
late.

## Prediction

Recall should be better than blind test 2's 3/8: these are large, heavily
covered markets (Iran strikes, national elections) rather than niche token
launches. The two-hour window is the risk — I expect at least one miss
purely because the signal led by more than two hours.

I expect the guards to block at least one hit, since a post that lands
close to the onset is one where the market may already be moving.
