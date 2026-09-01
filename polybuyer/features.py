"""Per-wallet feature extraction across a universe of markets.

Three families of features, answering three separate questions:

**Behaviour** -- where does this trader stand relative to repricings?  Money
made before the market moves is a different animal from money made in the
first seconds of the move, which is different again from money made chasing
it.  Raw PnL cannot tell them apart; lead time can.

**Skill** -- is the edge real?  ROI, calibration against entry price, and
whether it survives dropping the best few markets.

**Followability** -- could you actually have copied it?  The prior phase's
central finding was that these come apart: a trader whose winners gap
instantly hands a follower nothing but the losers.  Fill availability is
therefore measured, not assumed, and it is measured against the executed
tape, which makes every number here a lower bound.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Sequence

from .config import Config
from .jumps import Jump, Stance, baseline_alignment, stances
from .model import Resolution, Trade
from .pnl import MarketPnL, cost_of, drop_best, market_pnl, roi as roi_of
from .stats import Interval, bootstrap_ratio, effective_n
from .tape import Tape


def _pct(xs: Sequence[float], q: float) -> float:
    if not xs:
        return 0.0
    ys = sorted(xs)
    pos = (q / 100.0) * (len(ys) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ys) - 1)
    return ys[lo] + (ys[hi] - ys[lo]) * (pos - lo)


def _corr(xs: Sequence[float], ys: Sequence[float]) -> float:
    """Pearson correlation, 0.0 when undefined."""
    n = len(xs)
    if n < 3:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    sxy = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    sxx = sum((a - mx) ** 2 for a in xs)
    syy = sum((b - my) ** 2 for b in ys)
    if sxx <= 0 or syy <= 0:
        return 0.0
    return sxy / (sxx * syy) ** 0.5


@dataclass
class FollowSignal:
    """One simulated copy of one of the trader's opening trades."""

    condition_id: str
    ts: int
    their_price: float
    direction: int
    want_shares: float
    got_shares: float
    vwap: float
    #: Seconds before the price ran past our slippage cap.
    follow_window_s: float
    pnl: float
    capital: float
    #: The trader's own ROI on this signal -- for adverse-selection analysis.
    their_roi: float

    @property
    def fill_frac(self) -> float:
        return self.got_shares / self.want_shares if self.want_shares > 0 else 0.0


@dataclass
class WalletFeatures:
    wallet: str

    # --- scale -----------------------------------------------------------
    n_markets: int = 0
    n_trades: int = 0
    capital: float = 0.0
    pnl: float = 0.0
    n_events: int = 0
    eff_n: float = 0.0

    # --- skill -----------------------------------------------------------
    roi: Interval | None = None
    first_trade_roi: Interval | None = None
    roi_ex_best: float = 0.0
    calibration_edge: float = 0.0
    long_odds_edge: float = 0.0
    long_odds_n: int = 0
    win_rate: float = 0.0

    # --- behaviour relative to repricings --------------------------------
    n_jumps: int = 0
    n_pre: int = 0
    n_fast: int = 0
    n_late: int = 0
    pre_pnl: float = 0.0
    fast_pnl: float = 0.0
    late_pnl: float = 0.0
    pre_notional: float = 0.0
    anticipation_rate: float = 0.5
    anticipation_baseline: float = 0.5
    anticipation_excess: Interval | None = None
    fast_hit_rate: float = 0.5
    fast_excess: Interval | None = None
    median_lead_s: float | None = None
    median_latency_s: float | None = None

    # --- followability ---------------------------------------------------
    n_signals: int = 0
    median_follow_window_s: float = 0.0
    mean_fill_frac: float = 0.0
    follow_roi: Interval | None = None
    adverse_selection: float = 0.0

    # --- structure (screening) -------------------------------------------
    #: Peak |position| / gross volume, gross-weighted across markets.
    #: Near 0 = never holds a directional position (market maker).
    position_ratio: float = 1.0
    negrisk_share: float = 0.0
    gross_to_net: float = 1.0

    markets: list[MarketPnL] = field(default_factory=list)
    signals: list[FollowSignal] = field(default_factory=list)

    @property
    def pre_pnl_share(self) -> float:
        """Share of jump-window PnL earned *before* the market moved."""
        tot = abs(self.pre_pnl) + abs(self.fast_pnl) + abs(self.late_pnl)
        return self.pre_pnl / tot if tot > 0 else 0.0

    @property
    def fast_pnl_share(self) -> float:
        tot = abs(self.pre_pnl) + abs(self.fast_pnl) + abs(self.late_pnl)
        return self.fast_pnl / tot if tot > 0 else 0.0


def _size_ladder(notionals: Sequence[float], cfg: Config) -> tuple[float, float, float, float]:
    """Follower sizing keyed to the trader's *own* notional percentiles.

    Self-normalising by design: a $500 trader and a $500k trader both get
    sized sensibly without a per-trader hand-tuned constant.
    """
    f = cfg.follow
    lo = _pct(notionals, f.size_lo_pct)
    hi = _pct(notionals, f.size_hi_pct)
    return lo, hi, f.size_lo_usd, f.size_hi_usd


def _follow_usd(notional: float, lo: float, hi: float, lo_usd: float, hi_usd: float) -> float:
    if hi <= lo:
        return lo_usd
    frac = (notional - lo) / (hi - lo)
    return max(lo_usd, min(hi_usd, lo_usd + frac * (hi_usd - lo_usd)))


def extract_all(
    tapes: dict[str, Tape],
    jumps: dict[str, list[Jump]],
    resolutions: dict[str, Resolution],
    cfg: Config,
    clusters: dict[str, str] | None = None,
) -> dict[str, WalletFeatures]:
    """Compute features for every wallet appearing in ``tapes``.

    ``clusters`` maps wallet -> cluster id; sibling wallets are excluded from
    each other's simulated fills, since you cannot fill against the very
    order you are copying.
    """
    clusters = clusters or {}
    feats: dict[str, WalletFeatures] = {}

    # Accumulators keyed by wallet, then by market (the bootstrap cluster).
    ant_num: dict[str, dict[str, float]] = {}
    ant_den: dict[str, dict[str, float]] = {}
    fast_num: dict[str, dict[str, float]] = {}
    fast_den: dict[str, dict[str, float]] = {}
    leads: dict[str, list[float]] = {}
    lats: dict[str, list[float]] = {}
    events: dict[str, list[str]] = {}
    gross: dict[str, float] = {}
    net: dict[str, float] = {}
    posratio: dict[str, list[tuple[float, float]]] = {}
    negrisk: dict[str, list[tuple[float, int]]] = {}

    def F(w: str) -> WalletFeatures:
        if w not in feats:
            feats[w] = WalletFeatures(wallet=w)
        return feats[w]

    # ---------------------------------------------------------- pass 1
    for cid, tape in tapes.items():
        res = resolutions.get(cid)

        by_wallet: dict[str, list[Trade]] = {}
        for t in tape.trades:
            by_wallet.setdefault(t.wallet, []).append(t)

        # Per-wallet market result.
        for w, rows in by_wallet.items():
            f = F(w)
            f.n_trades += len(rows)

            g = sum(abs(t.ref_signed) for t in rows)
            nt = abs(sum(t.ref_signed for t in rows))
            gross[w] = gross.get(w, 0.0) + g
            net[w] = net.get(w, 0.0) + nt
            if g > 0:
                pos = peak = 0.0
                for t in rows:
                    pos += t.ref_signed
                    peak = max(peak, abs(pos))
                posratio.setdefault(w, []).append((peak / g, g))
            negrisk.setdefault(w, []).append((g, 1 if (res and res.neg_risk) else 0))
            ev = rows[0].event_slug or cid
            events.setdefault(w, []).append(ev)

            if res is not None:
                mp = market_pnl(w, cid, rows, res)
                if mp is not None:
                    f.markets.append(mp)
                    f.n_markets += 1
                    f.capital += mp.capital
                    f.pnl += mp.pnl

        # Stances against every jump in this market.
        for j in jumps.get(cid, []):
            st = stances(tape, j, cfg.window)
            base = baseline_alignment(list(st.values()))
            fast_base = _fast_baseline(list(st.values()))

            for w, s in st.items():
                f = F(w)
                f.n_jumps += 1
                f.pre_pnl += s.anticipatory_pnl
                f.fast_pnl += s.reaction_pnl
                f.late_pnl += s.late_net * j.signed_move
                f.pre_notional += s.pre_notional

                if abs(s.pre_net) > 1e-9:
                    f.n_pre += 1
                    wgt = abs(s.pre_net)
                    hit = 1.0 if s.pre_net * j.direction > 0 else 0.0
                    ant_num.setdefault(w, {}).setdefault(cid, 0.0)
                    ant_den.setdefault(w, {}).setdefault(cid, 0.0)
                    ant_num[w][cid] += wgt * (hit - base)
                    ant_den[w][cid] += wgt
                    if s.lead_s is not None:
                        leads.setdefault(w, []).append(s.lead_s)
                if abs(s.fast_net) > 1e-9:
                    f.n_fast += 1
                    wgt = abs(s.fast_net)
                    hit = 1.0 if s.fast_net * j.direction > 0 else 0.0
                    fast_num.setdefault(w, {}).setdefault(cid, 0.0)
                    fast_den.setdefault(w, {}).setdefault(cid, 0.0)
                    fast_num[w][cid] += wgt * (hit - fast_base)
                    fast_den[w][cid] += wgt
                    if s.latency_s is not None:
                        lats.setdefault(w, []).append(s.latency_s)
                if abs(s.late_net) > 1e-9:
                    f.n_late += 1

    # ---------------------------------------------------------- pass 2
    for w, f in feats.items():
        f.n_events = len(set(events.get(w, [])))
        f.eff_n = effective_n(events.get(w, []))

        if f.markets:
            f.roi = bootstrap_ratio(
                [m.pnl for m in f.markets], [m.capital for m in f.markets], cfg.stats
            )
            f.roi_ex_best = roi_of(drop_best(f.markets, cfg.screen.concentration_drop_n))
            f.win_rate = sum(1 for m in f.markets if m.won) / len(f.markets)
            f.calibration_edge, f.long_odds_edge, f.long_odds_n = _calibration(f.markets)

        g = gross.get(w, 0.0)
        n = net.get(w, 0.0)
        f.gross_to_net = g / n if n > 0 else float("inf")
        pr = posratio.get(w, [])
        pw = sum(x[1] for x in pr)
        f.position_ratio = sum(x[0] * x[1] for x in pr) / pw if pw > 0 else 1.0
        nr = negrisk.get(w, [])
        nw = sum(x[0] for x in nr)
        f.negrisk_share = sum(x[0] * x[1] for x in nr) / nw if nw > 0 else 0.0

        if w in ant_den:
            cids = list(ant_den[w])
            f.anticipation_excess = bootstrap_ratio(
                [ant_num[w][c] for c in cids], [ant_den[w][c] for c in cids], cfg.stats
            )
            f.anticipation_baseline = 0.5
            f.anticipation_rate = 0.5 + f.anticipation_excess.point
        if w in fast_den:
            cids = list(fast_den[w])
            f.fast_excess = bootstrap_ratio(
                [fast_num[w][c] for c in cids], [fast_den[w][c] for c in cids], cfg.stats
            )
            f.fast_hit_rate = 0.5 + f.fast_excess.point

        if leads.get(w):
            f.median_lead_s = median(leads[w])
        if lats.get(w):
            f.median_latency_s = median(lats[w])

    # ---------------------------------------------------------- pass 3
    _simulate_follows(feats, tapes, resolutions, cfg, clusters)
    return feats


def _fast_baseline(sts: Sequence[Stance]) -> float:
    """Share of first-moments risk that was on the right side."""
    right = wrong = 0.0
    for s in sts:
        if abs(s.fast_net) < 1e-9:
            continue
        if s.fast_net * s.jump.direction > 0:
            right += abs(s.fast_net)
        else:
            wrong += abs(s.fast_net)
    tot = right + wrong
    return right / tot if tot > 0 else 0.5


def _calibration(markets: Sequence[MarketPnL]) -> tuple[float, float, int]:
    """Realised frequency minus implied probability, at entry.

    Robust to the whale-sizing distortion that makes total PnL a poor skill
    estimate: it asks whether the things they bought at 20c happen 20% of
    the time, not how much they made.
    """
    imp: list[float] = []
    real: list[float] = []
    lo_imp: list[float] = []
    lo_real: list[float] = []
    for m in markets:
        p = m.first_price if m.first_direction > 0 else 1.0 - m.first_price
        r = m.terminal if m.first_direction > 0 else 1.0 - m.terminal
        imp.append(p)
        real.append(r)
        if p < 0.25:
            lo_imp.append(p)
            lo_real.append(r)
    edge = (sum(real) / len(real) - sum(imp) / len(imp)) if imp else 0.0
    lo_edge = (sum(lo_real) / len(lo_real) - sum(lo_imp) / len(lo_imp)) if lo_imp else 0.0
    return edge, lo_edge, len(lo_imp)


def _simulate_follows(
    feats: dict[str, WalletFeatures],
    tapes: dict[str, Tape],
    resolutions: dict[str, Resolution],
    cfg: Config,
    clusters: dict[str, str],
) -> None:
    """Copy each trader's opening trade and see what we would really get.

    The opening trade specifically: the prior phase found it carries the most
    edge and is the most slippage-robust of the available signals.
    """
    f_cfg = cfg.follow
    by_cluster: dict[str, set[str]] = {}
    for w, c in clusters.items():
        by_cluster.setdefault(c, set()).add(w)

    for w, f in feats.items():
        opens = [m for m in f.markets if m.capital > 0]
        if not opens:
            continue
        notionals = [m.capital for m in opens]
        lo, hi, lo_usd, hi_usd = _size_ladder(notionals, cfg)

        sibs = frozenset(by_cluster.get(clusters.get(w, ""), {w})) | {w}
        exclude = sibs if f_cfg.exclude_self_cluster else frozenset({w})

        for m in opens:
            tape = tapes.get(m.condition_id)
            res = resolutions.get(m.condition_id)
            if tape is None or res is None or res.ref_terminal is None:
                continue

            d = m.first_direction
            entry = m.first_price
            usd = _follow_usd(m.capital, lo, hi, lo_usd, hi_usd)
            unit_cost = entry if d > 0 else 1.0 - entry
            if unit_cost <= 0:
                continue
            want = usd / unit_cost

            fill = tape.simulate_fill(
                m.first_ts, entry, d, want, f_cfg.cap, f_cfg.window_s, exclude
            )
            fw = tape.follow_window(m.first_ts, entry, d, f_cfg.cap)

            if fill.shares > 0:
                payoff = res.ref_terminal if d > 0 else 1.0 - res.ref_terminal
                pnl = fill.shares * (payoff - fill.vwap)
                cap = fill.notional
            else:
                pnl = cap = 0.0

            f.signals.append(
                FollowSignal(
                    condition_id=m.condition_id,
                    ts=m.first_ts,
                    their_price=entry,
                    direction=d,
                    want_shares=want,
                    got_shares=fill.shares,
                    vwap=fill.vwap,
                    follow_window_s=fw,
                    pnl=pnl,
                    capital=cap,
                    their_roi=m.roi,
                )
            )

        if not f.signals:
            continue
        f.n_signals = len(f.signals)
        finite = [s.follow_window_s for s in f.signals if s.follow_window_s != float("inf")]
        f.median_follow_window_s = median(finite) if finite else float("inf")
        f.mean_fill_frac = sum(s.fill_frac for s in f.signals) / len(f.signals)
        f.follow_roi = bootstrap_ratio(
            [s.pnl for s in f.signals], [s.capital for s in f.signals], cfg.stats
        )
        # The §6 mechanism: does capital land preferentially in their bad
        # ideas?  Negative correlation means the winners gapped away.
        f.adverse_selection = _corr(
            [s.fill_frac for s in f.signals], [s.their_roi for s in f.signals]
        )
