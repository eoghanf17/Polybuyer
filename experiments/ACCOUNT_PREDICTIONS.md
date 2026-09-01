# Blind account predictions

**Written before searching X for any of these markets.** Handles are my
best guess and deliberately unverified — checking whether a handle exists
risks stumbling onto the announcement, which would spoil the test. The
commit timestamp is the evidence.

Probability is my estimate that *this specific account* posts the resolving
announcement, at or before the market repriced. The bar the strategy needs
is ≥1% each, ideally ≥5%.

Scoring: a market is a HIT if the account that actually broke it appears in
my list. Unreachable-by-design markets are called out in advance, and
counting them as hits later would be cheating.

---

## 1. Khamenei out as Supreme Leader of Iran in 2026?
No principal announces their own removal. This resolves via Iranian state
media or a fast opposition outlet, so the "principal" framing fails and it
becomes a wire trade.
- `@IranIntl_En` 15% — consistently first on Iranian leadership news
- `@Reuters` 20% · `@AP` 15% — wires confirm
- `@PressTV` 10% — Iranian state
- `@khamenei_ir` 3% — own account, would not announce this
**Expect: MISS on principal-only. Included as a control.**

## 2. US announces halt in Iran offensive operations by July 31?
## 3. Will the US announce a blockade on Iran by July 31?
- `@WhiteHouse` 30% · `@POTUS` 25% · `@SecDef` 15% · `@StateDept` 10%
**Expect: UNREACHABLE.** Trump announces on Truth Social; the X repost is
late if it comes. The keyword filter missed these because "Trump" is not in
the question — a gap worth fixing.

## 4. Will Graham Platner drop out before the Midterms?
Candidates announce their own withdrawals, usually as a statement posted by
the campaign.
- `@GrahamPlatner` 45% — the candidate
- `@politico` 15% · `@AP` 10% · `@NBCNews` 8%

## 5. SHEIN IPO before 2027?
IPO news breaks through filings and wires, not the company's own marketing
feed.
- `@Reuters` 25% · `@business` 25% · `@FT` 12%
- `@SHEIN_Official` 5% — a marketing account, not investor relations

## 6. Will SpaceX or OpenAI IPO first?
Both principals are unusually X-native, which makes this the best-case
market for the whole design.
- `@elonmusk` 40% — would post a SpaceX listing himself
- `@sama` 30% · `@OpenAI` 20%
- `@SpaceX` 15%

## 7. Will Binance launch stock tokens in 2026?
Binance ships product announcements on X as a matter of routine.
- `@binance` 60% · `@_RichardTeng` 20% (CEO) · `@cz_binance` 15%

## 8. Will Infrared launch a token by December 31 2025?
Crypto project; token launches are announced on X essentially always.
- `@InfraredFinance` 55% · `@infrared_fi` 20% (handle uncertain)

## 9. Pep Guardiola out as Man City manager by the end of 2026?
Football personnel news has a dedicated breaker who beats the clubs.
- `@FabrizioRomano` 50% — reliably first on manager moves
- `@ManCity` 35% — the club's own confirmation
- `@David_Ornstein` 30%

## 10. Will Tria launch a token by March 31, 2026?
- `@tria` 40% · `@triaprotocol` 20% (handle uncertain)

## 11. Will GRVT launch a token by September 30, 2026?
- `@grvt_io` 50% · `@GRVT_official` 20% (handle uncertain)

## 12. Will António Costa visit Ukraine by December 31, 2026?
Visits get announced by the host as often as the visitor, and Zelensky
posts every one.
- `@ZelenskyyUa` 50% · `@eucopresident` 45% · `@antoniocostapm` 20%

## 13. Will o1 launch a token by September 30, 2026?
- `@o1_labs` 45% · `@o1protocol` 15% (handle uncertain)

## 14. Will Keith Kellogg visit Ukraine by December 31, 2026?
- `@generalkellogg` 40% · `@ZelenskyyUa` 45% · `@StateDept` 10%

## 15. Will Bitmine announce that it holds more than 5M ETH before 2027?
Treasury-holding companies post their own numbers, the way Saylor does.
- `@BitMNR` 40% · `@fundstrat` 25% · `@fundstratTom` 20% (Tom Lee, chairman)

---

## What I expect before checking

- **Crypto token launches (8, 10, 11, 13)** should be the strongest: the
  project's own account announcing is near-universal. My risk is the
  *handle*, not the behaviour.
- **6, 7, 15** should hit — X-native principals.
- **9, 12, 14** are coin-flips between principal and beat reporter.
- **1** should miss and **2, 3** are unreachable. Both are predicted
  failures, not excuses made afterwards.

If the crypto launches miss on handles rather than behaviour, the fix is a
handle-resolution step, not a different strategy.
