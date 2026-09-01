"""Copy-strategy evaluation against recorded liquidity.

The prior research phase measured its headline copy strategies with
*mechanical* slippage: assume you fill your whole intended size at the
target's price plus k ticks. That is an upper bound on what a follower
gets, and on the one strategy where the same phase did check real fills the
gap was large -- paying a cent cost ~2.3 points, while actually competing
for the offers cost 14.

This module closes that gap for every strategy. Each of the target's trades
becomes a signal; the follower's order is then filled only out of prints
that actually executed afterwards, inside the slippage cap and window, and
excluding the target's own cluster. Both numbers are reported side by side,
because the difference between them *is* the finding.

Everything here is still a lower bound on fillability: resting liquidity
that was never lifted is invisible in a tape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median
from typing import Callable, Sequence

from .config import Config
from .model import Resolution, Trade
from .stats import Interval, bootstrap_ratio
from .tape import Tape

DEFAULT_TICK = 0.01


@dataclass(frozen=True, slots=True)
class Signal:
    """One of the target's trades, as something a follower could copy."""

    condition_id: str
    ts: int
    entry_ref: float
    direction: int
    shares: float
    notional: float


def _signals_from(trades: Sequence[Trade], risk_only: bool, first_only: bool,
                  min_notional: float = 0.0) -> list[Signal]:
    """Turn one wallet-market trade sequence into follow signals."""
    out: list[Signal] = []
    pos = 0.0
    for t in sorted(trades, key=lambda x: x.ts):
        new = pos + t.ref_signed
        increasing = abs(new) > abs(pos)
        pos = new
        if risk_only and not increasing:
            continue
        if t.notional < min_notional:
            continue
        out.append(Signal(t.condition_id, t.ts, t.ref_price,
                          1 if t.ref_signed > 0 else -1,
                          abs(t.ref_signed), t.notional))
        if first_only:
            break
    return out


def mirror_all(trades: Sequence[Trade]) -> list[Signal]:
    """Copy every print the target makes."""
    return _signals_from(trades, risk_only=False, first_only=False)


def risk_increasing(trades: Sequence[Trade]) -> list[Signal]:
    """Copy only prints that grow the position, and hold to expiry."""
    return _signals_from(trades, risk_only=True, first_only=False)


def first_per_market(trades: Sequence[Trade]) -> list[Signal]:
    """Copy only the opening trade in each market."""
    return _signals_from(trades, risk_only=True, first_only=True)


def first_big(min_notional: float = 10_000.0) -> Callable[[Sequence[Trade]], list[Signal]]:
    """Copy only opening trades above a notional floor."""
    def f(trades: Sequence[Trade]) -> list[Signal]:
        return _signals_from(trades, risk_only=True, first_only=True,
                             min_notional=min_notional)
    return f


STRATEGIES: dict[str, Callable[[Sequence[Trade]], list[Signal]]] = {
    "mirror": mirror_all,
    "risk-increasing": risk_increasing,
    "first": first_per_market,
    "first-10k": first_big(10_000.0),
}


@dataclass
class Outcome:
    """What one strategy would have returned."""

    strategy: str
    n_signals: int = 0
    #: Signals dropped because the tape does not reach back to them.
    n_uncovered: int = 0
    n_filled: int = 0

    real_pnl: float = 0.0
    real_capital: float = 0.0
    mech_pnl: float = 0.0
    mech_capital: float = 0.0

    fill_fracs: list[float] = field(default_factory=list)
    windows: list[float] = field(default_factory=list)
    #: per-market totals, for the cluster bootstrap
    by_market_real: dict[str, tuple[float, float]] = field(default_factory=dict)
    by_market_mech: dict[str, tuple[float, float]] = field(default_factory=dict)
    real_ci: Interval | None = None
    mech_ci: Interval | None = None

    @property
    def real_roi(self) -> float:
        return self.real_pnl / self.real_capital if self.real_capital > 0 else 0.0

    @property
    def mech_roi(self) -> float:
        return self.mech_pnl / self.mech_capital if self.mech_capital > 0 else 0.0

    @property
    def mean_fill(self) -> float:
        return sum(self.fill_fracs) / len(self.fill_fracs) if self.fill_fracs else 0.0

    @property
    def median_window(self) -> float:
        finite = [w for w in self.windows if w != float("inf")]
        return median(finite) if finite else float("inf")

    @property
    def capital_ratio(self) -> float:
        """Fraction of the mechanical capital that could really be deployed."""
        return self.real_capital / self.mech_capital if self.mech_capital > 0 else 0.0


def _add(d: dict[str, tuple[float, float]], cid: str, pnl: float, cap: float) -> None:
    a, b = d.get(cid, (0.0, 0.0))
    d[cid] = (a + pnl, b + cap)


def evaluate(
    strategy: str,
    wallets: Sequence[str],
    tapes: dict[str, Tape],
    resolutions: dict[str, Resolution],
    cfg: Config,
    truncated: set[str] | None = None,
    ticks: dict[str, float] | None = None,
    slippage_ticks: int = 1,
) -> Outcome:
    """Run one strategy over a cluster's trades, real fills and mechanical.

    ``wallets`` is the whole operator cluster: its members are excluded from
    the liquidity a follower consumes, since you cannot fill against the
    order you are copying, nor against the same operator's other wallet
    firing the same idea.
    """
    build = STRATEGIES[strategy]
    cluster = frozenset(w.lower() for w in wallets)
    truncated = truncated or set()
    ticks = ticks or {}
    out = Outcome(strategy=strategy)

    for cid, tape in tapes.items():
        res = resolutions.get(cid)
        if res is None or not res.is_terminal or res.ref_terminal is None:
            continue
        terminal = res.ref_terminal
        tick = ticks.get(cid, DEFAULT_TICK)

        mine = [t for t in tape.trades if t.wallet in cluster]
        if not mine:
            continue

        for sig in build(mine):
            out.n_signals += 1

            # A truncated tape that starts after the signal cannot tell us
            # what liquidity followed it; scoring it would be guesswork.
            if cid in truncated and sig.ts < tape.start:
                out.n_uncovered += 1
                continue

            d = sig.direction
            unit = sig.entry_ref if d > 0 else 1.0 - sig.entry_ref
            if unit <= 0:
                continue
            payoff = terminal if d > 0 else 1.0 - terminal

            # Mechanical: full size, k ticks worse. The optimistic bound.
            mech_cost = min(max(unit + slippage_ticks * tick, 1e-6), 1.0)
            m_pnl = sig.shares * (payoff - mech_cost)
            m_cap = sig.shares * mech_cost
            out.mech_pnl += m_pnl
            out.mech_capital += m_cap
            _add(out.by_market_mech, cid, m_pnl, m_cap)

            # Real: fill out of prints that actually executed afterwards.
            fill = tape.simulate_fill(sig.ts, sig.entry_ref, d, sig.shares,
                                      cfg.follow.cap, cfg.follow.window_s, cluster)
            out.fill_fracs.append(fill.fill_frac)
            out.windows.append(
                tape.follow_window(sig.ts, sig.entry_ref, d, cfg.follow.cap)
            )
            if fill.shares > 0:
                out.n_filled += 1
                r_pnl = fill.shares * (payoff - fill.vwap)
                r_cap = fill.notional
                out.real_pnl += r_pnl
                out.real_capital += r_cap
                _add(out.by_market_real, cid, r_pnl, r_cap)
            else:
                _add(out.by_market_real, cid, 0.0, 0.0)

    if out.by_market_real:
        cids = list(out.by_market_real)
        out.real_ci = bootstrap_ratio(
            [out.by_market_real[c][0] for c in cids],
            [out.by_market_real[c][1] for c in cids], cfg.stats)
    if out.by_market_mech:
        cids = list(out.by_market_mech)
        out.mech_ci = bootstrap_ratio(
            [out.by_market_mech[c][0] for c in cids],
            [out.by_market_mech[c][1] for c in cids], cfg.stats)
    return out


def render(outcomes: Sequence[Outcome], cap: float, slippage_ticks: int) -> str:
    """Side-by-side table: mechanical slippage vs recorded liquidity."""
    L = [
        "-" * 92,
        f"Copy strategies: mechanical slippage ({slippage_ticks} tick) vs "
        f"recorded liquidity (+{cap * 100:.0f}c cap)",
        "-" * 92,
        f"{'strategy':<17}{'signals':>8}{'filled':>8}{'fill%':>7}"
        f"{'mech PnL':>12}{'mech ROI':>10}{'real PnL':>12}{'real ROI':>10}{'cap%':>7}",
    ]
    for o in outcomes:
        L.append(
            f"{o.strategy:<17}{o.n_signals:>8}{o.n_filled:>8}{o.mean_fill:>7.0%}"
            f"{o.mech_pnl:>12,.0f}{o.mech_roi:>10.1%}"
            f"{o.real_pnl:>12,.0f}{o.real_roi:>10.1%}{o.capital_ratio:>7.0%}"
        )
    L.append("")
    L.append("cap%  = share of the mechanical capital that could actually be deployed")
    L.append("real  = filled only from prints that executed after the signal, inside")
    L.append("        the cap and window, excluding the target's own cluster")
    L.append("")
    for o in outcomes:
        L.append(f"{o.strategy}:")
        if o.mech_ci:
            L.append(f"    mechanical ROI  {o.mech_ci}")
        if o.real_ci:
            L.append(f"    recorded ROI    {o.real_ci}")
        w = o.median_window
        ws = "never" if w == float("inf") else (f"{w:.0f}s" if w < 90 else f"{w/60:.0f}m")
        L.append(f"    median {ws} before the price clears the cap")
        if o.n_uncovered:
            L.append(f"    {o.n_uncovered}/{o.n_signals} signals unusable: tape "
                     f"does not reach back that far")
    return "\n".join(L)
