"""Repricing events, and where each trader stood relative to them.

The premise of this whole module: a prediction market's price is flat-ish
until information arrives, then it moves and stays moved.  Those moves are
the only externally visible timestamps of "when the news landed".  Timing a
trader against them separates three populations that raw PnL cannot:

    positioned BEFORE the move    -> knew something (or guessed, repeatedly)
    in the FIRST SECONDS after    -> professional news flow / fast wire
    after the move is public      -> follower, or noise

The distinction matters commercially, not just taxonomically.  The prior
research phase found that copying a trader whose winners gap instantly is a
losing proposition -- you get filled on their mistakes and miss their wins.
So the archetype a trader belongs to, and the *shape* of the move after
them, decide whether they are worth following at all.

A note on the obvious question: this reads only public on-chain trade data,
and infers behaviour from price timing.  It identifies wallets whose timing
looks informed.  It cannot and does not establish why.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Sequence

from .config import JumpConfig, WindowConfig
from .tape import Tape

#: How a trader's entry is classified relative to a jump onset.
PRE = "pre"
FAST = "fast"
LATE = "late"


def _quantile(xs: Sequence[float], q: float) -> float:
    """Linear-interpolated quantile (stdlib only, small inputs)."""
    if not xs:
        return 0.0
    ys = sorted(xs)
    if len(ys) == 1:
        return ys[0]
    pos = q * (len(ys) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ys) - 1)
    return ys[lo] + (ys[hi] - ys[lo]) * (pos - lo)


def _spread(xs: Sequence[float]) -> float:
    """Robust dispersion: the central 80% range."""
    return _quantile(xs, 0.9) - _quantile(xs, 0.1)


@dataclass(frozen=True, slots=True)
class Jump:
    """A large, persistent repricing in one market."""

    condition_id: str
    #: Timestamp of the first print that committed to the move.
    onset_ts: int
    #: +1 if the reference outcome repriced up, -1 if down.
    direction: int
    #: Size of the move in probability points (always positive).
    magnitude: float
    before: float
    after: float
    #: Prints in the market before onset -- a proxy for how watched it was.
    prior_trades: int

    @property
    def signed_move(self) -> float:
        return self.after - self.before


@dataclass(frozen=True, slots=True)
class Stance:
    """One wallet's position relative to one jump."""

    wallet: str
    jump: Jump
    #: Exposure acquired in the pre-onset window (the anticipation signal).
    pre_net: float
    #: Exposure acquired in the first moments after onset (reaction signal).
    fast_net: float
    #: Exposure acquired later in the move.
    late_net: float
    #: Total position carried into the onset, from market open.
    position_at_onset: float
    #: Seconds before onset of their first pre-window entry (None if absent).
    lead_s: float | None
    #: Seconds after onset of their first fast-window entry (None if absent).
    latency_s: float | None
    #: Notional deployed in the pre window, USD.
    pre_notional: float

    @property
    def bucket(self) -> str | None:
        if abs(self.pre_net) > 1e-9:
            return PRE
        if abs(self.fast_net) > 1e-9:
            return FAST
        if abs(self.late_net) > 1e-9:
            return LATE
        return None

    @property
    def aligned(self) -> bool:
        """Correctly positioned for the move, using freshly acquired risk."""
        net = self.pre_net if abs(self.pre_net) > 1e-9 else self.fast_net
        return net * self.jump.direction > 0

    @property
    def anticipatory_pnl(self) -> float:
        """Mark-to-market gain on risk taken in the pre-onset window.

        This is the number that matters for an insider screen: money made by
        being positioned *before* the market moved, as opposed to money made
        by holding through it or chasing it.
        """
        return self.pre_net * self.jump.signed_move

    @property
    def reaction_pnl(self) -> float:
        """Gain on risk taken in the first moments of the move."""
        return self.fast_net * self.jump.signed_move


def detect(tape: Tape, cfg: JumpConfig) -> list[Jump]:
    """Find persistent repricings in a market's price path.

    Method: resample to a fixed grid, compare a trailing median level to a
    leading median level at every point, keep the local maxima that clear
    ``min_move``, discard any that revert, then locate the onset print.

    Medians throughout: a prediction-market tape is full of single prints
    that sweep a thin book and immediately bounce back, and a mean-based
    detector fires on every one of them.
    """
    if len(tape) < cfg.min_market_trades:
        return []

    times, prices = tape.buckets(cfg.bucket_s, cfg.min_bucket_trades)
    n = len(times)
    if n < 4:
        return []

    b = max(1, cfg.baseline_s // cfg.bucket_s)
    h = max(1, cfg.horizon_s // cfg.bucket_s)
    p = max(1, cfg.persistence_s // cfg.bucket_s)

    # Candidate change points: |leading median - trailing median|.
    cands: list[tuple[float, int, float, float, float]] = []
    for i in range(n):
        lo = max(0, i - b)
        if i - lo < 1 or i + 1 >= n:
            continue
        base = prices[lo:i]
        before = median(base)
        after = median(prices[i : min(n, i + h)])
        move = after - before
        if abs(move) < cfg.min_move:
            continue
        # The level we are measuring from has to be a level.  A baseline
        # window that is itself swinging gives us nothing to measure
        # against -- and is exactly what the *return leg* of a spike looks
        # like, which would otherwise be reported as fresh news.
        bspread = _spread(base)
        if bspread > cfg.max_baseline_spread_frac * abs(move):
            continue
        cands.append((abs(move), i, before, after, bspread))

    if not cands:
        return []

    # Non-max suppression so one repricing yields one event.
    cands.sort(key=lambda c: -c[0])
    sep = max(1, cfg.min_separation_s // cfg.bucket_s)
    chosen: list[tuple[float, int, float, float, float]] = []
    for c in cands:
        if all(abs(c[1] - k[1]) >= sep for k in chosen):
            chosen.append(c)

    jumps: list[Jump] = []
    for mag, i, before, after, bspread in chosen:
        move = after - before
        direction = 1 if move > 0 else -1

        # Persistence: did it stick?  A spike that round-trips is noise, or
        # someone sweeping the book, not information.
        j = min(n - 1, i + p)
        held = prices[j] if j > i else prices[-1]
        if (held - before) * direction < cfg.persistence_frac * abs(move):
            continue

        onset = _find_onset(tape, times[i], before, move, bspread, cfg)
        if onset is None:
            continue

        jumps.append(
            Jump(
                condition_id=tape.condition_id,
                onset_ts=onset,
                direction=direction,
                magnitude=abs(move),
                before=before,
                after=after,
                prior_trades=len(tape.slice(tape.start, onset)),
            )
        )

    jumps.sort(key=lambda x: x.onset_ts)
    return jumps


def _find_onset(
    tape: Tape,
    bucket_ts: int,
    before: float,
    move: float,
    bspread: float,
    cfg: JumpConfig,
) -> int | None:
    """Timestamp at which the price *started* moving.

    Two steps, because the two things we need are different:

    1. Find where the market **committed** -- crossed a good fraction of the
       way to the new level and stayed there.  Confirmation matters; without
       it the onset latches onto the first stray print.
    2. Walk **backwards** from there to the last moment the price was still
       inside the baseline band, and call that the onset.

    Step 2 is the important one.  If onset is placed a quarter of the way up
    the ramp, everyone who traded on the first tick of the news -- which is
    precisely what a professional news desk does -- is timestamped *before*
    the move and misread as having anticipated it.  Anchoring to the
    departure point puts the news reaction where it belongs, on the far side
    of the onset.
    """
    direction = 1 if move > 0 else -1
    commit_level = before + cfg.onset_cover_frac * move
    committed = lambda x: (x - commit_level) * direction >= 0  # noqa: E731

    lo = bucket_ts - cfg.baseline_s
    hi = bucket_ts + cfg.horizon_s
    confirm = max(cfg.bucket_s * 3, 300)

    commit_ts: int | None = None
    for t in tape.slice(lo, hi):
        if not committed(t.ref_price):
            continue
        nxt = tape.median_price(t.ts, t.ts + confirm)
        if nxt is None or committed(nxt):
            commit_ts = t.ts
            break

    if commit_ts is None:
        return None

    # Band that counts as "still at the old level".  Wide enough to ignore
    # baseline chop, never wider than the commit threshold itself.
    band = max(2.0 * bspread, cfg.onset_band_min)
    band = min(band, abs(cfg.onset_cover_frac * move))
    departed = lambda x: (x - (before + direction * band)) * direction >= 0  # noqa: E731

    run = tape.slice(lo, commit_ts + 1)
    onset = commit_ts
    for t in reversed(run):
        if not departed(t.ref_price):
            break
        onset = t.ts
    return onset


def stances(tape: Tape, jump: Jump, win: WindowConfig) -> dict[str, Stance]:
    """Every wallet's position relative to one jump."""
    o = jump.onset_ts
    # The guard band sits between "anticipated" and "reacted": trades inside
    # it are credited as reaction, because at this timestamp resolution the
    # two are indistinguishable.
    g = o - win.guard_s
    pre = tape.net_exposure(o - win.pre_s, g)
    fast = tape.net_exposure(g, o + win.fast_s)
    late = tape.net_exposure(o + win.fast_s, o + win.react_tail_s)
    held = tape.net_exposure(tape.start, g)

    first_pre: dict[str, int] = {}
    pre_notional: dict[str, float] = {}
    for t in tape.slice(o - win.pre_s, g):
        first_pre.setdefault(t.wallet, t.ts)
        pre_notional[t.wallet] = pre_notional.get(t.wallet, 0.0) + t.notional

    first_fast: dict[str, int] = {}
    for t in tape.slice(g, o + win.fast_s):
        first_fast.setdefault(t.wallet, t.ts)

    out: dict[str, Stance] = {}
    for w in set(pre) | set(fast) | set(late):
        out[w] = Stance(
            wallet=w,
            jump=jump,
            pre_net=pre.get(w, 0.0),
            fast_net=fast.get(w, 0.0),
            late_net=late.get(w, 0.0),
            position_at_onset=held.get(w, 0.0),
            lead_s=float(o - first_pre[w]) if w in first_pre else None,
            latency_s=float(first_fast[w] - o) if w in first_fast else None,
            pre_notional=pre_notional.get(w, 0.0),
        )
    return out


def baseline_alignment(stances_for_jump: Sequence[Stance]) -> float:
    """Share of pre-window risk that happened to be on the right side.

    This is the null the insider score is measured against.  In a market
    that is about to move, *somebody* is always positioned correctly by
    chance; in an efficient market that share is ~50% of the risk on.  Being
    right before the move is only evidence when it beats this.
    """
    right = wrong = 0.0
    for s in stances_for_jump:
        if abs(s.pre_net) < 1e-9:
            continue
        if s.pre_net * s.jump.direction > 0:
            right += abs(s.pre_net)
        else:
            wrong += abs(s.pre_net)
    total = right + wrong
    return right / total if total > 0 else 0.5
