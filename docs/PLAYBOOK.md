# Building a watchlist: the rerunnable process

Every stage is a script in `experiments/`. Run them in order; each writes a
file the next one reads, so a stage can be re-run without repeating the one
before it.

**The ordering principle: everything free runs first.** Gamma and the tape
cost nothing, the model costs cents, X costs $0.005 a post and bills
continuously once a market is armed. An earlier version of this pipeline
searched X for markets chosen because they *resolved*, and learned they had
$3.5k of lifetime volume — money spent to discover something the tape
already knew.

---

## 0. Budget first

```python
from polybuyer.newsdesk.costs import markets_for_budget
markets_for_budget(100)   # -> 13
```

X bills per post **delivered**, so an armed market costs money whether or
not it ever fires. Decide the market count here, not after the research
feels finished. Current numbers: ~$8/market/month, so 252 armed markets is
**~$1,900/month**.

## 1. Sweep the universe — `experiments/open_universe.py`

Gamma stops at **2,100 rows per query**, so a single call is never the
universe. Slice by resolution date until each slice is under the cap. A
slice returning exactly 2,100 rows is truncated; narrow it.

*Output:* `open_universe.json` — 21,860 open markets on the last run.

## 2. Mechanical screens — free, and they do most of the work

In order: `gameStartTime` (in-play), `SPORTS_PAT`, `SCHEDULED_PAT`,
`OFF_PLATFORM_PAT` (Truth Social), `KNOWN_INSTANT_PAT`, then a liquidity
floor. 21,860 → 11,845 → 3,343 at $10k liquidity.

**In-play is excluded on the field, never on wording.** "Will England win
on 2026-07-11?" is a World Cup match with no sports vocabulary in it.

## 3. Triage — `experiments/triage_open.py`

Asks the model, twelve markets a call: *would a principal — a party to the
event — plausibly announce this on X?* Rejects price/index/vote-count
resolution, journalist-only stories, off-X announcements, and gradual
events. 3,343 → 952 (28.5%).

## 4. Post-triage screens — `SPORT_RESULT_PAT`, `CEREMONY_PAT`

Triage accepts award ceremonies and league finals because a principal
genuinely does announce them — on stage, live, at a known time. The post
follows the broadcast, so the trade is a latency race against television.

Keep these patterns **narrow**: a first version used `win the \d{4}` and
`final` and disarmed the French and Brazilian presidential elections.

## 5. Arm — `experiments/build_watchlist.py`

Caps markets per principal (18 Ballon d'Or contracts are one event), then
generates per market:

- `required_keyword` — 4–8 **event** terms, ANDed into every rule including
  the principal's own feed. Not the subject: @Arcium announcing its own
  token writes "TGE is live", not "Arcium's TGE is live".
- `topic_terms` — the subject, for the open keyword tier.
- `accounts` — principal / beat / wire.

Writes to `newsdesk.db` armed and paper-only. `rules.lint()` flags narrow
keyword groups over principal feeds.

*Output:* 252 armed, 372 handles, 504 stream rules (X allows 1,000).

## 5b. Price every rule — free, and non-negotiable

```python
from polybuyer.newsdesk.costs import rule_posts_per_hour, affordable
affordable(rule_posts_per_hour(bearer, rule))
```

`/2/tweets/counts/recent` returns volume without consuming post quota
(`project_usage` held flat at 1,982 across a control run), so this costs
nothing and must run before anything is armed.

Measured on the first real watchlist, the projection was wrong by **117×**:
$1,925/month estimated, **$223,936/month actual**. The error was entirely
in the open tier —

| tier | rules | posts/hour | $/month |
|---|---|---|---|
| principal | 241 | 43 | **$156** |
| keyword | 250 | 62,161 | **$223,780** |

— because generated topic groups contained bare country names. One market's
`(Cuba OR Israel OR …)` billed 14,159 posts/hour, $50,973/month by itself.

A keyword rule over `MAX_RULE_POSTS_PER_HOUR` (5/h) loses its open tier and
keeps its principal rules. An **unmeasurable** rule is refused, never
assumed quiet. Applied: $223,936 → **$410/month**, all 252 markets still
armed, 78 keeping the keyword tier.

## 6. Verify handles — **not yet done, needs X credit**

Every handle is model-generated. Some will not exist. Check each against
`/2/users/by/username/{handle}` before arming live; a rule naming a
non-existent account silently matches nothing.

## 7. Backtest before live — `candidates50.py` → `refine_candidates.py` → `blind*.py`

For resolved markets only. Locate repricings with `jumps.detect` (never
"first print above 0.90"), take the jump whose **direction** agrees with
the payoff, and track head fakes as a separate population — a live desk
fires without knowing which repricing holds.

Search a **tight window** anchored on the onset. Blind test 4 used 2 hours
and cost $2.36 across 45 markets; a 24-hour window costs twelve times that.

---

## Closing the loop

After every run, do this before the context is lost:

1. **Fix the code**, and add a test that fails without the fix.
2. **Append a `Learning`** to `polybuyer/newsdesk/learnings.py` naming that
   test in `enforced_by`.
3. `python -m polybuyer.newsdesk.learnings` — prints the register, exits
   non-zero if any learning has no enforcement.

`TestLearningRegister` fails the suite when a learning is prose only. That
is the mechanism: findings cannot decay into a document nobody reads,
because a finding without a test is a build failure.

Current register: 13 learnings, 0 unenforced.
