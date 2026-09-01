"""Archetype classification, screening, and the follow verdict.

Two questions have to be kept apart, because the prior research phase showed
they can point in opposite directions:

    Is this trader good?        -> skill features
    Can I profit by copying?    -> followability features

A trader whose winners reprice instantly is genuinely informed *and*
worthless to copy: you get a sliver of their winners and the full size of
their losers.  Ranking on ROI alone promotes exactly those traders.  So the
final verdict is gated on simulated fills, never on headline performance.

Every composite score here is a weighted blend of components that are also
reported individually.  The blend is a convenience for sorting; the
components and their confidence intervals are the evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import Config
from .features import WalletFeatures
from .stats import fdr_qvalues

INSIDER = "insider"
NEWSDESK = "newsdesk"
FOLLOWER = "follower"
MAKER = "maker"
STRUCTURAL = "structural"
UNCLASSIFIED = "unclassified"

FOLLOW = "follow"
WATCH = "watch"
AVOID = "avoid"


def _clip01(x: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.0
    return max(0.0, min(1.0, (x - lo) / (hi - lo)))


@dataclass
class Verdict:
    wallet: str
    archetype: str = UNCLASSIFIED
    insider_score: float = 0.0
    news_score: float = 0.0
    decision: str = WATCH
    #: Human-readable evidence, in the order it was considered.
    reasons: list[str] = field(default_factory=list)
    #: Why the wallet was screened out, if it was.
    excluded: str | None = None
    #: Raw one-sided p-value on this wallet's defining statistic.
    p_value: float = 1.0
    #: Benjamini-Hochberg q-value across the whole candidate sweep.  Only
    #: meaningful relative to the cohort it was computed over.
    q_value: float = 1.0

    @property
    def score(self) -> float:
        return max(self.insider_score, self.news_score)


def screen(f: WalletFeatures, cfg: Config) -> str | None:
    """Reason to exclude this wallet, or ``None`` to keep it.

    These populations dominate any volume- or PnL-ranked list while carrying
    no directional signal at all, so they are removed before scoring rather
    than being allowed to crowd the top of it.
    """
    s = cfg.screen
    if f.n_markets < s.min_markets:
        return f"only {f.n_markets} resolved markets (need {s.min_markets})"
    if f.n_jumps < s.min_jumps:
        return f"present for only {f.n_jumps} repricings (need {s.min_jumps})"
    if f.capital < s.min_notional:
        return f"only ${f.capital:,.0f} deployed (need ${s.min_notional:,.0f})"
    if f.position_ratio < s.min_position_ratio:
        return (f"never holds a directional position (peak position is only "
                f"{f.position_ratio:.0%} of volume traded) -- market maker")
    if f.negrisk_share > s.max_negrisk_share:
        return (f"{f.negrisk_share:.0%} negative-risk markets -- positions are "
                f"structural mints, not opinions")
    return None


def insider_score(f: WalletFeatures, cfg: Config) -> tuple[float, list[str]]:
    """How much does this look like someone trading ahead of the news?

    The load-bearing component is anticipation excess: the size-weighted rate
    at which their *freshly acquired* risk, taken in the hours before a
    repricing, turns out to be on the correct side -- measured against the
    rate for everyone else positioned in the same window.  That baseline
    matters: in any market about to move, somebody is always right by
    accident.
    """
    why: list[str] = []
    ex = f.anticipation_excess
    if ex is None or f.n_pre == 0:
        return 0.0, ["never positioned ahead of a repricing"]
    if f.n_pre < cfg.screen.min_archetype_events:
        return 0.0, [f"positioned ahead of only {f.n_pre} repricings "
                     f"(need {cfg.screen.min_archetype_events})"]
    if ex.underpowered:
        return 0.0, [f"anticipation measurable in only {ex.n} markets -- underpowered"]

    # Multiplicative, not additive.  An additive blend hands out points for
    # *style* -- trading early, concentrating PnL in the pre-move window --
    # which merely describes when someone trades and is satisfied perfectly
    # by a random punter who happens to trade early.  Measured accuracy
    # against the baseline is the necessary condition; everything else only
    # modulates a score that is already earned.
    conf = 1.0 - ex.p_le_zero
    evidence = _clip01(ex.point, 0.0, 0.35) * conf
    style = 0.7 * _clip01(f.pre_pnl_share, 0.0, 0.70) + 0.3 * _clip01(
        f.long_odds_edge, 0.0, 0.25
    )
    s = 100.0 * evidence * (0.65 + 0.35 * style)

    why.append(f"correctly positioned before {f.n_pre} repricings, "
               f"{ex.point:+.1%} vs everyone else also positioned "
               f"(95% CI [{ex.lo:+.1%}, {ex.hi:+.1%}], p={ex.p_le_zero:.3f})")
    if f.pre_pnl_share > 0.3:
        why.append(f"{f.pre_pnl_share:.0%} of repricing PnL earned before the move")
    if f.long_odds_n >= 10 and f.long_odds_edge > 0.05:
        why.append(f"long shots (<25c) land {f.long_odds_edge:+.1%} more often "
                   f"than priced, over {f.long_odds_n} entries")
    if f.median_lead_s:
        why.append(f"typically in {f.median_lead_s / 3600:.1f}h before the move")
    return s, why


def news_score(f: WalletFeatures, cfg: Config) -> tuple[float, list[str]]:
    """How much does this look like a professional reacting to a live feed?

    Not anticipation -- reaction, but faster and more accurately than the
    rest of the market that is reacting to the same headline.  Speed alone
    is not enough (a fast wrong trader is just fast), so accuracy against
    the other first-movers carries the most weight.
    """
    why: list[str] = []
    ex = f.fast_excess
    if ex is None or f.n_fast == 0:
        return 0.0, ["never among the first movers on a repricing"]
    if f.n_fast < cfg.screen.min_archetype_events:
        return 0.0, [f"first-mover on only {f.n_fast} repricings "
                     f"(need {cfg.screen.min_archetype_events})"]
    if ex.underpowered:
        return 0.0, [f"reaction edge measurable in only {ex.n} markets -- underpowered"]

    conf = 1.0 - ex.p_le_zero
    lat = f.median_latency_s if f.median_latency_s is not None else 600.0
    # Faster is better; the guard band is the floor of what we can resolve.
    speed = 1.0 - _clip01(lat, -float(cfg.window.guard_s), 600.0)

    # Same structure as the insider score, for the same reason: speed is not
    # evidence.  A fast trader who is right half the time is just fast.
    evidence = _clip01(ex.point, 0.0, 0.30) * conf
    style = 0.5 * speed + 0.5 * _clip01(f.fast_pnl_share, 0.0, 0.70)
    s = 100.0 * evidence * (0.65 + 0.35 * style)

    why.append(f"first-mover on {f.n_fast} repricings, {ex.point:+.1%} more often "
               f"right than the other first movers "
               f"(95% CI [{ex.lo:+.1%}, {ex.hi:+.1%}], p={ex.p_le_zero:.3f})")
    why.append(f"median reaction {lat:+.0f}s from onset")
    if f.eff_n >= 20:
        why.append(f"spread over {f.eff_n:.0f} effectively independent events")
    return s, why


def followability(f: WalletFeatures, cfg: Config) -> tuple[str, list[str]]:
    """Could you actually have copied this, and would it have paid?

    This is where good traders get rejected.  Three ways to fail:

    * the price runs past your cap before you can act at all;
    * you fill, but only on the ideas that were wrong (adverse selection);
    * you fill fine and the simulated ROI still is not positive.
    """
    why: list[str] = []
    if f.n_signals == 0 or f.follow_roi is None:
        return WATCH, ["no copyable opening trades in sample"]

    fr = f.follow_roi
    win = f.median_follow_window_s
    why.append(f"simulated follow ROI {fr}")
    why.append(f"median {win:.0f}s before the price clears a "
               f"{cfg.follow.cap * 100:.0f}c cap; mean fill {f.mean_fill_frac:.0%}")

    hard_gap = win < 5.0
    adverse = f.adverse_selection < -0.25

    # Which constraint actually binds?  These pull in opposite directions
    # and imply completely different infrastructure, so naming the binding
    # one is more useful than a single "followability" number.
    #
    # Anticipatory traders act in the quiet tape before news, where there is
    # time to copy but very little to copy into -- their limit is size.
    # Reaction traders act inside the news burst, where liquidity is deep
    # but the price clears a limit in seconds -- their limit is latency.
    if win > 300.0 and f.mean_fill_frac < 0.35:
        why.append(
            f"binding constraint is LIQUIDITY, not speed: ~{win / 60:.0f} min to "
            f"act, but only {f.mean_fill_frac:.0%} of target size is available "
            f"in the quiet tape before the move"
        )
    elif win < 60.0 and f.mean_fill_frac > 0.70:
        why.append(
            f"binding constraint is SPEED: {f.mean_fill_frac:.0%} of size is "
            f"available, but only ~{win:.0f}s before the price clears the cap"
        )

    if adverse:
        why.append(f"adverse selection: fill availability correlates "
                   f"{f.adverse_selection:+.2f} with their own result -- you fill "
                   f"on the losers and miss the winners")
    if hard_gap:
        why.append("price gaps through the cap almost immediately; "
                   "needs sub-second execution to capture any of it")

    if fr.p_le_zero > 0.5 or adverse:
        return AVOID, why
    if fr.significant and not hard_gap:
        return FOLLOW, why
    return WATCH, why


def classify(f: WalletFeatures, cfg: Config) -> Verdict:
    """Full verdict for one wallet."""
    v = Verdict(wallet=f.wallet)

    reason = screen(f, cfg)
    if reason is not None:
        v.excluded = reason
        v.archetype = MAKER if "market maker" in reason else (
            STRUCTURAL if "structural" in reason else UNCLASSIFIED
        )
        v.decision = AVOID
        v.reasons = [reason]
        return v

    v.insider_score, ins_why = insider_score(f, cfg)
    v.news_score, news_why = news_score(f, cfg)

    if v.insider_score >= v.news_score and v.insider_score > 0:
        v.archetype = INSIDER
        v.reasons = list(ins_why)
        v.p_value = f.anticipation_excess.p_le_zero if f.anticipation_excess else 1.0
    elif v.news_score > 0:
        v.archetype = NEWSDESK
        v.reasons = list(news_why)
        v.p_value = f.fast_excess.p_le_zero if f.fast_excess else 1.0
    else:
        v.archetype = UNCLASSIFIED

    # Money made only after the move is public is not an edge worth paying
    # for -- it is the crowd, arriving.
    if f.n_late > max(f.n_pre, f.n_fast) * 2 and v.score < 25:
        v.archetype = FOLLOWER
        v.reasons.append("mostly arrives after repricings are public")

    v.decision, follow_why = followability(f, cfg)
    v.reasons.extend(follow_why)
    return v


def rank(feats: dict[str, WalletFeatures], cfg: Config) -> list[tuple[Verdict, WalletFeatures]]:
    """Score everyone, keep what survives screening, best first.

    Two gates stand between a high score and a recommendation:

    * **Multiplicity.** Several hundred wallets are tested at once, so raw
      p-values are worthless -- 5% of a pure-noise cohort clears p<0.05 by
      construction.  Candidates are held to a Benjamini-Hochberg q-value
      computed across the whole sweep.
    * **Followability.** An unfollowable genius must not outrank a
      followable journeyman, so the sort is by decision first, score second.
    """
    out: list[tuple[Verdict, WalletFeatures]] = []
    for w, f in feats.items():
        v = classify(f, cfg)
        if v.excluded is None:
            out.append((v, f))

    qs = fdr_qvalues([v.p_value for v, _ in out])
    for (v, f), q in zip(out, qs):
        v.q_value = q
        if v.decision == FOLLOW and q > cfg.stats.fdr_q:
            v.decision = WATCH
            v.reasons.append(
                f"q={q:.3f} across {len(out)} candidates screened: not "
                f"distinguishable from the luckiest of the cohort"
            )

    order = {FOLLOW: 0, WATCH: 1, AVOID: 2}
    out.sort(key=lambda p: (order.get(p[0].decision, 3), -p[0].score))
    return out
