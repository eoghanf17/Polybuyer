"""Rendering results for a human.

Deliberately verbose about uncertainty.  A ranked list of wallets with big
percentages next to them invites exactly the mistake this pipeline exists to
prevent -- treating the luckiest member of a large cohort as a discovery --
so intervals, sample sizes and the FDR q-value travel with every number.
"""

from __future__ import annotations

import json
from typing import Sequence

from .features import WalletFeatures
from .scores import FOLLOW, Verdict

BAR = "-" * 78


def _fmt_window(s: float) -> str:
    if s == float("inf"):
        return "never"
    if s < 90:
        return f"{s:.0f}s"
    if s < 5400:
        return f"{s / 60:.0f}m"
    return f"{s / 3600:.1f}h"


def table(ranked: Sequence[tuple[Verdict, WalletFeatures]], limit: int = 25) -> str:
    """Compact ranking table."""
    out = [
        f"{'wallet':<44}{'archetype':<11}{'score':>6}{'q':>7}"
        f"{'mkts':>6}{'window':>8}{'fill':>6}  decision",
        BAR,
    ]
    for v, f in ranked[:limit]:
        out.append(
            f"{v.wallet:<44}{v.archetype:<11}{v.score:6.1f}{v.q_value:7.3f}"
            f"{f.n_markets:6d}{_fmt_window(f.median_follow_window_s):>8}"
            f"{f.mean_fill_frac:6.0%}  {v.decision}"
        )
    if not ranked:
        out.append("(nothing survived screening)")
    return "\n".join(out)


def detail(v: Verdict, f: WalletFeatures) -> str:
    """Full evidence for one wallet."""
    L = [BAR, f"{v.wallet}   [{v.archetype}]   -> {v.decision.upper()}", BAR]

    L.append(f"  insider score {v.insider_score:.1f} | news score {v.news_score:.1f} "
             f"| p={v.p_value:.4f} q={v.q_value:.4f}")
    L.append("")
    L.append("  Scale")
    L.append(f"    {f.n_markets} resolved markets, {f.n_trades} trades, "
             f"${f.capital:,.0f} deployed")
    L.append(f"    {f.n_events} events, {f.eff_n:.1f} effectively independent")

    L.append("  Result")
    if f.roi:
        L.append(f"    ROI              {f.roi}")
    if f.first_trade_roi:
        L.append(f"    first-trade ROI  {f.first_trade_roi}")
    L.append(f"    ROI ex-best-{5:d}     {f.roi_ex_best:+.1%}   "
             f"(edge must survive dropping its best markets)")
    L.append(f"    win rate         {f.win_rate:.1%}")
    L.append(f"    calibration      {f.calibration_edge:+.1%} vs entry price"
             + (f"; long shots (<25c) {f.long_odds_edge:+.1%} over {f.long_odds_n}"
                if f.long_odds_n >= 10 else ""))

    L.append("  Timing vs repricings")
    L.append(f"    present at {f.n_jumps} repricings: "
             f"{f.n_pre} anticipated, {f.n_fast} first-mover, {f.n_late} late")
    if f.anticipation_excess:
        L.append(f"    anticipation     {f.anticipation_excess}")
    if f.fast_excess:
        L.append(f"    first-mover edge {f.fast_excess}")
    if f.median_lead_s:
        L.append(f"    typical lead     {_fmt_window(f.median_lead_s)} before the move")
    if f.median_latency_s is not None:
        L.append(f"    typical reaction {f.median_latency_s:+.0f}s from onset")

    L.append("  Copyability")
    L.append(f"    follow window    {_fmt_window(f.median_follow_window_s)} "
             f"before the price clears the cap")
    L.append(f"    mean fill        {f.mean_fill_frac:.0%} of target size "
             f"(lower bound: executed prints only)")
    if f.follow_roi:
        L.append(f"    simulated ROI    {f.follow_roi}")
    L.append(f"    adverse select.  {f.adverse_selection:+.2f} "
             f"(negative = you fill on their losers)")

    L.append("  Structure")
    L.append(f"    position ratio   {f.position_ratio:.2f} "
             f"(low = market maker)")
    L.append(f"    negative-risk    {f.negrisk_share:.0%} of volume")

    rows = f.top_anticipated if f.archetype_is_insider else f.top_reacted
    if rows:
        label = ("Biggest anticipated repricings" if f.archetype_is_insider
                 else "Biggest first-mover reactions")
        L.append(f"  {label}")
        for title, slug, pnl, t, mag in rows[:6]:
            when = (f"{_fmt_window(abs(t))} before" if f.archetype_is_insider
                    else f"{t:+.0f}s after")
            L.append(f"    {pnl:>+10,.0f}  {mag:.0%} move, {when:>12}  "
                     f"{(title or slug)[:44]}")

    L.append("  Why")
    for r in v.reasons:
        L.append(f"    - {r}")
    return "\n".join(L)


def summary(
    ranked: Sequence[tuple[Verdict, WalletFeatures]],
    n_screened: int,
    n_markets: int | None = None,
    min_markets: int | None = None,
    n_truncated: int = 0,
) -> str:
    rec = [(v, f) for v, f in ranked if v.decision == FOLLOW]
    L = [
        BAR,
        f"Screened {n_screened} wallets; {len(ranked)} passed structural filters; "
        f"{len(rec)} recommended.",
        BAR,
    ]
    if n_truncated and n_markets:
        L.append(f"{n_truncated}/{n_markets} tapes hit the server's 12k-print cap, so for")
        L.append("those markets every figure covers only the visible window, not the")
        L.append("trader's full record there.")
        L.append("")
    if (not ranked and n_markets is not None and min_markets is not None
            and n_markets < min_markets):
        L.append(f"NOTE: the corpus holds {n_markets} markets but the breadth")
        L.append(f"screen needs {min_markets}. No wallet can pass. Widen the")
        L.append("sweep or lower ScreenConfig.min_markets.")
        return "\n".join(L)
    if not rec:
        L.append("No wallet cleared both the false-discovery gate and the")
        L.append("copyability simulation. That is the expected outcome on most")
        L.append("cohorts and is a result, not a failure -- see docs/METHOD.md.")
    return "\n".join(L)


def to_json(ranked: Sequence[tuple[Verdict, WalletFeatures]]) -> str:
    rows = []
    for v, f in ranked:
        rows.append({
            "wallet": v.wallet,
            "archetype": v.archetype,
            "decision": v.decision,
            "insider_score": round(v.insider_score, 2),
            "news_score": round(v.news_score, 2),
            "p_value": round(v.p_value, 5),
            "q_value": round(v.q_value, 5),
            "n_markets": f.n_markets,
            "n_trades": f.n_trades,
            "capital": round(f.capital, 2),
            "pnl": round(f.pnl, 2),
            "roi": None if not f.roi else {
                "point": round(f.roi.point, 4), "lo": round(f.roi.lo, 4),
                "hi": round(f.roi.hi, 4), "p_le_zero": round(f.roi.p_le_zero, 4),
                "n": f.roi.n, "underpowered": f.roi.underpowered,
            },
            "anticipation_excess": None if not f.anticipation_excess else {
                "point": round(f.anticipation_excess.point, 4),
                "lo": round(f.anticipation_excess.lo, 4),
                "hi": round(f.anticipation_excess.hi, 4),
                "p_le_zero": round(f.anticipation_excess.p_le_zero, 4),
                "n": f.anticipation_excess.n,
                "underpowered": f.anticipation_excess.underpowered,
            },
            "fast_excess": None if not f.fast_excess else {
                "point": round(f.fast_excess.point, 4),
                "lo": round(f.fast_excess.lo, 4),
                "hi": round(f.fast_excess.hi, 4),
                "p_le_zero": round(f.fast_excess.p_le_zero, 4),
                "n": f.fast_excess.n,
                "underpowered": f.fast_excess.underpowered,
            },
            "n_pre": f.n_pre, "n_fast": f.n_fast, "n_late": f.n_late,
            "median_lead_s": f.median_lead_s,
            "median_latency_s": f.median_latency_s,
            "median_follow_window_s": (
                None if f.median_follow_window_s == float("inf")
                else round(f.median_follow_window_s, 1)
            ),
            "mean_fill_frac": round(f.mean_fill_frac, 4),
            "adverse_selection": round(f.adverse_selection, 4),
            "position_ratio": round(f.position_ratio, 4),
            "negrisk_share": round(f.negrisk_share, 4),
            "reasons": v.reasons,
        })
    return json.dumps(rows, indent=2)
