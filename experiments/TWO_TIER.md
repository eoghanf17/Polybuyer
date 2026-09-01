# Two-tier firing, and the required keyword

Built from blind test 2 (`BLIND_TEST_2_RESULT.md`). Implemented in
`polybuyer/newsdesk/rules.py`.

## The two tiers

| | tier 1 — principal | tier 2 — keyword |
|---|---|---|
| how it matched | a `from:` rule on an account we chose | a topic rule, whoever carries it |
| account tiers | `principal`, `beat`, `wire` | anything else, including `osint` |
| follower floor | none | `min_followers`, default 10,000 |
| aggression | 5c | 2c |
| size | $10 | $3 |
| gate says CORROBORATE | wait for a second source | drop |

Both tiers fire on a clean gate pass. They differ on price, size, and what
they do with a borderline signal.

### Why tier 2 exists

Blind test 1 hand-enumerated accounts and caught **0 of 10** markets. Blind
test 2's topic rules caught **3 of 8** at the 10k floor, and all three were
accounts nobody had listed: @SprinterPress on the Burnham visit,
@legiondotcc on the Squid token, @GoatHouseNFL relaying the OBJ signing.
Without tier 2 those are three markets we watch and never trade.

### Why tier 2 is sized down

Its *recall* is measured; its *precision* is not. The harness stopped
gating a market once a post passed, so false alarms on the three markets
that hit were never counted. 22 clean rejections across the five markets
that missed is a lower bound on the rejection rate, not a rate. $3 at 2c is
the price of acting on evidence with a known hole in it — and the hole
closes by running the tier live and counting, not by more backtesting.

### Why the follower floor is on tier 2 only

At threshold 0 the keyword tier produced its one false alarm — a
106-follower account replying "They picked the best approach tbh" on
Arcium. The 10k floor removed it and cost no hits. But a *principal* we
put on the list ourselves can be tiny and still be the whole signal:
@squidrouterETH has 486 followers and announced its own airdrop. A floor
on tier 1 would have discarded that.

## The required keyword

Every rule for a market ANDs one term — **including the `from:` rules on
principals**. A company account posts recruitment, memes and conference
photos, and each of those costs $0.005 to receive plus an LLM call to
reject.

The keyword must be a term that appears in **the announcement**, not the
market's subject. This is the trap: for "Will Arcium launch a token",
`Arcium` is the obvious word, but @Arcium announcing its own token writes
"TGE is live", not "Arcium's TGE is live".

Worked through on the eight blind-test markets:

| market | wrong (subject) | right (event) |
|---|---|---|
| Arcium launches a token | `Arcium` | `(token OR TGE OR "$ARX" OR airdrop)` |
| Andy Burnham visits Ukraine | `Burnham` | `(Kyiv OR Ukraine OR visit)` |
| Squid launches a token | `Squid` | `(token OR TGE OR "$QUID" OR airdrop)` |
| SpaceX added to Nasdaq-100 | `SpaceX` | `(Nasdaq OR "Nasdaq-100" OR index)` |
| OBJ signs with a team | `OBJ` | `(sign OR signs OR signed OR agrees)` |

The subject term still appears — in `topic_terms`, which is the tier-2
rule's other half. It is the *keyword* that has to be the event, because
that is the half a principal's `from:` rule gets ANDed with.

### The accepted cost

A principal who announces with a bare "It's live." and a link matches
nothing and is missed. That is not engineered away. It is the trade the
user asked for, and the reason the keyword is an OR-group rather than a
single word: `(token OR TGE OR "$ARX" OR airdrop OR live OR claim)` is
still a filter, and still cheap.

`build_rules` refuses to build a market with an empty keyword, and
`add_market` refuses to arm one — so the failure is caught by the person
adding the market, while they have the context to fix it, rather than
appearing as a surprise bill.
