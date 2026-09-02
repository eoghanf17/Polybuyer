"""Every mistake this pipeline has made, and where it is now prevented.

A findings document rots. Somebody writes "remember to exclude in-play
markets", the next run is written by someone who did not read it, and the
same 131 match markets come back looking like a strategy. So the rule here
is that **a learning is not recorded until it points at its enforcement** —
a test that fails if the mistake returns, or a named constant the pipeline
actually consumes.

:func:`unenforced` returns learnings that have no such anchor, and the test
suite fails when that list is non-empty. That is the whole mechanism: you
cannot add a learning to this file and leave it as prose.

Adding one after a run:

1. Fix the code, and add a test that fails without the fix.
2. Append a :class:`Learning` here naming that test in ``enforced_by``.
3. ``python -m polybuyer.newsdesk.learnings`` prints the register and
   exits non-zero if anything is unenforced.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Learning:
    id: str
    #: What went wrong, in the concrete. Numbers, not adjectives.
    incident: str
    #: What the pipeline does differently now.
    change: str
    #: Test names or module constants that would fail/flag if it regressed.
    #: A learning with an empty list is a to-do, not a learning.
    enforced_by: tuple[str, ...] = field(default_factory=tuple)
    #: Cost of having got it wrong, where it was measured.
    cost: str = ""


REGISTER: tuple[Learning, ...] = (
    Learning(
        "in-play-inflates-everything",
        "A tradeable-market sweep returned 256 candidates. 131 of them had "
        "gameStartTime set: live match markets, which carry the biggest "
        "jumps and deepest books in the whole set (one showed $753k). The "
        "cached universe had dropped the field, and a regex over question "
        "text missed them because 'Will England win on 2026-07-11?' "
        "contains no sports vocabulary.",
        "in-play is excluded on the gameStartTime field, never on wording, "
        "and any cached universe must carry that field.",
        ("TestLatencyRaceScreens", "discover.screen"),
        cost="would have overstated tradeable markets by 2x",
    ),
    Learning(
        "ceremonies-are-latency-races",
        "Triage accepted 18 Ballon d'Or markets, TIME Person of the Year "
        "and the Nobel committee, because a principal genuinely does "
        "announce those. They are announced on stage, live, at a time "
        "everybody knows, so the post follows the broadcast.",
        "CEREMONY_PAT and SPORT_RESULT_PAT run after triage; a plausible "
        "announcer is not sufficient, the announcement must not be a "
        "broadcast everyone is already watching.",
        ("TestLatencyRaceScreens", "discover.CEREMONY_PAT",
         "discover.SPORT_RESULT_PAT"),
    ),
    Learning(
        "narrow-sport-regex-eats-elections",
        "A first attempt at the sports screen used `win the \\d{4}` and "
        "`final`. It disarmed 83 markets, of which 35 were false positives: "
        "the French and Brazilian presidential elections, a US-Iran nuclear "
        "deal market.",
        "SPORT_RESULT_PAT lists named competitions only. Tests pin both "
        "directions -- competitions caught, elections kept.",
        ("TestLatencyRaceScreens.test_elections_and_deals_are_not",),
        cost="35 good markets disarmed before it was caught",
    ),
    Learning(
        "gamma-caps-every-query-at-2100",
        "top_markets() is one gamma query and gamma stops at 2,100 rows. "
        "Ordered by volume descending that ceiling landed at $2.97M, so "
        "every market the project ever screened was in the top tenth by "
        "volume, and the $25k volume floor never bound because nothing "
        "below it was visible. Slicing the same window by date reaches "
        "18,832 resolved and 21,860 open markets.",
        "Universe sweeps slice by date until each slice is under the cap. A "
        "slice that returns exactly 2,100 rows is truncated, not complete.",
        ("experiments/funnel_audit.py", "experiments/open_universe.py"),
        cost="5.8x fewer tradeable markets than exist",
    ),
    Learning(
        "one-wallet-is-not-a-cluster",
        "The FootballFan98 ladder was re-run against one wallet and "
        "returned -11.9%, against +16.7% on record. FootballFan98 is the "
        "loss-making leg of a four-wallet cluster: -$1.07M against the "
        "cluster's +$4.76M.",
        "Cluster membership is pinned in targets.py, not rediscovered. Copy "
        "strategies use the cluster's combined position per market and "
        "exclude all members from follower liquidity.",
        ("targets.FOOTBALLFAN_WALLETS", "targets.cluster_pnl"),
        cost="inverted the sign of the headline result",
    ),
    Learning(
        "cluster-rediscovery-does-not-work",
        "Rebuilding the cluster from one seed failed four ways: "
        "fetch_and_build only merges wallets already in the seed set; "
        "find_siblings is blind because Blockscout serves only the most "
        "recent 10,000 transfers (two months for an active wallet) and the "
        "founding USDC transfers are older; the funding counterparties in "
        "that window are shared deposit hubs touching 5,564 addresses; and "
        "co-occurrence across 96 tapes was diffuse. Candidate sets formed a "
        "star, never the closed network the real cluster shows (6/6 pairs, "
        "every member degree 3).",
        "Known clusters are pinned in targets.py with provenance. Any "
        "candidate set claiming to be a cluster must show a closed network.",
        ("targets.FOOTBALLFAN_CLUSTER",),
    ),
    Learning(
        "signals-come-from-history-not-the-tape",
        "A follow simulation built signals from market_tape, which is capped "
        "and returns newest-first. On a busy market that holds only recent "
        "prints, so the target's fifth trade was being read as their first.",
        "Signals are built from the wallet's own trade history. Signals "
        "whose tape does not reach back are dropped as unmeasurable.",
        ("experiments/ff_timeline.py", "follow.evaluate"),
        cost="about 10 points of ROI",
    ),
    Learning(
        "guards-must-measure-headroom-not-movement",
        "The don't-chase guards blocked the largest trade in the dataset. "
        "'Iran closes its airspace by June 8' had drifted +47% over two "
        "hours and +56% over one day on a developing story when "
        "@financialjuice posted the confirmation; entry was 0.583 and the "
        "trade was worth $140,858 at a 5c cap, 87% ROI.",
        "A guard breaches only when a window is over threshold AND "
        "remaining headroom is below min_headroom. How far a price moved "
        "says nothing about how much is left.",
        ("TestHeadroomGuard", "guards.DEFAULT_MIN_HEADROOM"),
        cost="$140,858 on one market",
    ),
    Learning(
        "the-gate-is-more-literal-than-the-market",
        "'US strikes Iran by Feb 28' repriced 0.50->0.91 with $66,094 of "
        "demonstrable PnL. Ten of the 22 posts in the window reported "
        "ISRAEL striking Iran and none mentioned the US. The gate dropped "
        "them and was right by the market's rules; the market repriced "
        "anyway because traders inferred what followed.",
        "Open, not fixed. Loosening `resolves` to fire on correlated news "
        "reopens the false-alarm class that cost 36 points of ROI. Recorded "
        "so the trade-off is chosen rather than rediscovered.",
        ("gate.QUESTIONS",),
        cost="$66,094 on one market; unresolved",
    ),
    Learning(
        "keyword-must-be-the-event-not-the-subject",
        "The obvious keyword for 'Will Arcium launch a token' is 'Arcium', "
        "but @Arcium announcing its own token writes 'TGE is live', not "
        "\"Arcium's TGE is live\".",
        "required_keyword holds event terms and topic_terms holds the "
        "subject. lint() warns when a narrow keyword group is ANDed over "
        "principal feeds.",
        ("TestKeywordToggle", "rules.lint"),
    ),
    Learning(
        "posts-cost-money-so-keep-them",
        "blind2.py read 288 posts at $0.005 each and kept four snippets "
        "truncated to 100 characters, leaving its own conclusions "
        "unauditable. No harness stored tweet ids although X returns them "
        "by default, and none stored gate answers, so re-evaluating a gate "
        "change meant re-paying both APIs.",
        "Every harness writes corpus.Post rows: post id, follower count, "
        "retweet status, full text, repricing moment and complete gate "
        "answers. Rows merge on post id.",
        ("TestCorpus", "corpus.add"),
        cost="$1.44 re-fetched; one run's conclusions unverifiable",
    ),
    Learning(
        "follower-floor-belongs-to-the-open-tier-only",
        "At no follower floor the keyword tier's one false positive was a "
        "106-follower account replying 'They picked the best approach tbh'. "
        "A 10k floor removed it and cost no hits. But @squidrouterETH has "
        "486 followers and announced its own airdrop.",
        "min_followers applies to the keyword tier only. A principal we "
        "chose is trusted by that choice, however small.",
        ("TestRules.test_the_follower_floor_applies_to_keyword_only",),
    ),
    Learning(
        "x-stream-cost-scales-with-markets-watched",
        "Observed post density in the blind tests was 5-10 posts per market "
        "per hour during news windows, and both runs hit their max_results "
        "cap so those are floors. 252 armed markets projects to $700-$7,000 "
        "a month of delivered posts.",
        "The armed-market count is a budget decision before it is a "
        "research one. cost_model() sizes the watchlist from a monthly "
        "budget rather than from how many markets look interesting.",
        ("cost_model", "TestCostModel"),
        cost="would have been discovered by invoice",
    ),
)


def unenforced() -> list[Learning]:
    """Learnings with nothing stopping them recurring."""
    return [l for l in REGISTER if not l.enforced_by]


def as_markdown() -> str:
    out = ["# Learning register", "",
           f"{len(REGISTER)} recorded. A learning is only valid when it names "
           "the test or constant that prevents it recurring.", ""]
    for l in REGISTER:
        out += [f"## `{l.id}`", "", f"**What happened.** {l.incident}", "",
                f"**What changed.** {l.change}", ""]
        if l.cost:
            out.append(f"**Cost.** {l.cost}\n")
        out.append("**Enforced by** " +
                   (", ".join(f"`{e}`" for e in l.enforced_by) or "**NOTHING**"))
        out.append("")
    return "\n".join(out)


if __name__ == "__main__":
    import sys
    print(as_markdown())
    bad = unenforced()
    if bad:
        print(f"\n!! {len(bad)} unenforced: {[l.id for l in bad]}", file=sys.stderr)
        sys.exit(1)
