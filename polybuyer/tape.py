"""The executed tape of a single market, and what can honestly be read off it.

Polymarket publishes no historical order books.  There is no way to know what
was resting at any past instant.  The only evidence of liquidity is what
actually traded, so every fill number this module produces is a **lower
bound**: liquidity that was resting but never lifted is invisible to us and
would only ever make a follower's fill better, never worse.

That constraint is deliberately baked in here rather than left to callers to
remember.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass
from statistics import median
from typing import Iterable, Sequence

from .model import Trade


@dataclass(frozen=True, slots=True)
class Fill:
    """Result of simulating a follow order against the forward tape."""

    #: Shares actually obtainable from prints inside the cap and window.
    shares: float
    #: Shares we wanted.
    wanted: float
    #: Volume-weighted cost per share, in the currency of the side taken.
    vwap: float
    #: Seconds from signal to the last print consumed.
    elapsed_s: float

    @property
    def fill_frac(self) -> float:
        return self.shares / self.wanted if self.wanted > 0 else 0.0

    @property
    def notional(self) -> float:
        return self.shares * self.vwap


class Tape:
    """All prints for one market, sorted, with the reference price path."""

    __slots__ = ("condition_id", "trades", "_ts", "_px")

    def __init__(self, condition_id: str, trades: Iterable[Trade]):
        self.condition_id = condition_id
        self.trades: list[Trade] = sorted(trades, key=lambda t: (t.ts, t.tx))
        self._ts: list[int] = [t.ts for t in self.trades]
        self._px: list[float] = [t.ref_price for t in self.trades]

    def __len__(self) -> int:
        return len(self.trades)

    @property
    def start(self) -> int:
        return self._ts[0] if self._ts else 0

    @property
    def end(self) -> int:
        return self._ts[-1] if self._ts else 0

    @property
    def wallets(self) -> set[str]:
        return {t.wallet for t in self.trades}

    # ---------------------------------------------------------------- price

    def price_at(self, ts: int) -> float | None:
        """Last printed reference price at or before ``ts``."""
        i = bisect.bisect_right(self._ts, ts)
        return self._px[i - 1] if i > 0 else None

    def slice(self, lo: int, hi: int) -> list[Trade]:
        """Prints in ``[lo, hi)``."""
        a = bisect.bisect_left(self._ts, lo)
        b = bisect.bisect_left(self._ts, hi)
        return self.trades[a:b]

    def median_price(self, lo: int, hi: int) -> float | None:
        """Median reference price over ``[lo, hi)``.

        Median rather than mean: a single fat-fingered print or a sweep
        through a thin book should not move the baseline that jump detection
        is measured against.
        """
        seg = self.slice(lo, hi)
        return median(t.ref_price for t in seg) if seg else None

    def buckets(self, bucket_s: int, min_trades: int = 1) -> tuple[list[int], list[float]]:
        """Resample the price path onto a fixed grid.

        Returns ``(times, prices)`` where each price is the size-weighted
        average of the prints in that bucket, forward-filled across empty
        buckets.  Size weighting stops a one-share print carrying the same
        weight as a $50k block.
        """
        if not self.trades:
            return [], []

        t0 = (self.start // bucket_s) * bucket_s
        t1 = self.end
        times: list[int] = []
        prices: list[float] = []

        num = 0.0
        den = 0.0
        n = 0
        edge = t0 + bucket_s
        last = self._px[0]

        for tr in self.trades:
            while tr.ts >= edge:
                if n >= min_trades and den > 0:
                    last = num / den
                times.append(edge - bucket_s)
                prices.append(last)
                num = den = 0.0
                n = 0
                edge += bucket_s
            num += tr.ref_price * tr.size
            den += tr.size
            n += 1

        if n >= min_trades and den > 0:
            last = num / den
        times.append(edge - bucket_s)
        prices.append(last)

        # Guard against pathological grids on very long-lived markets.
        while edge <= t1:
            edge += bucket_s
            times.append(edge - bucket_s)
            prices.append(last)

        return times, prices

    # ------------------------------------------------------------ exposure

    def net_exposure(self, lo: int, hi: int) -> dict[str, float]:
        """Net change in reference exposure per wallet over ``[lo, hi)``.

        Net, not gross: a market maker who bought and sold the same size has
        no opinion, and should not be credited with one.
        """
        out: dict[str, float] = {}
        for t in self.slice(lo, hi):
            out[t.wallet] = out.get(t.wallet, 0.0) + t.ref_signed
        return out

    def first_entry(self, wallet: str) -> Trade | None:
        for t in self.trades:
            if t.wallet == wallet:
                return t
        return None

    # ---------------------------------------------------------- simulation

    def follow_window(
        self,
        ts: int,
        entry_ref: float,
        direction: int,
        cap: float,
        limit_s: int = 86_400,
    ) -> float:
        """Seconds until the price runs past a follower's slippage cap.

        This is the quantity that decides whether an informed trader is
        *followable at all*.  Two traders with identical edge are completely
        different propositions if one's price gaps in 400ms and the other's
        diffuses over two hours -- the second can be copied, the first
        cannot.  Returns ``inf`` if the price never escapes the cap within
        ``limit_s``.
        """
        if direction > 0:
            bound = entry_ref + cap
            escaped = lambda p: p > bound  # noqa: E731
        else:
            bound = entry_ref - cap
            escaped = lambda p: p < bound  # noqa: E731

        for t in self.slice(ts, ts + limit_s):
            if t.ts <= ts:
                continue
            if escaped(t.ref_price):
                return float(t.ts - ts)
        return float("inf")

    def simulate_fill(
        self,
        ts: int,
        entry_ref: float,
        direction: int,
        want_shares: float,
        cap: float,
        window_s: int,
        exclude: frozenset[str] = frozenset(),
    ) -> Fill:
        """Fill a follow order out of the forward tape.

        We compete for the same prints everybody else lifted: for each
        subsequent print that took the *same* direction at a price inside our
        cap, we consume shares from it until we are full or the window
        closes.  Prints from ``exclude`` (the target and their sibling
        wallets) are skipped -- you cannot fill against the very order you
        are trying to copy.

        This under-counts real liquidity, by construction.  See module
        docstring.
        """
        if want_shares <= 0 or direction == 0:
            return Fill(0.0, max(want_shares, 0.0), 0.0, 0.0)

        if direction > 0:
            cap_ok = lambda p: p <= entry_ref + cap  # noqa: E731
            cost_of = lambda p: p  # noqa: E731
        else:
            cap_ok = lambda p: p >= entry_ref - cap  # noqa: E731
            cost_of = lambda p: 1.0 - p  # noqa: E731

        got = 0.0
        spend = 0.0
        last_ts = ts

        for t in self.slice(ts, ts + window_s + 1):
            if t.ts <= ts or t.wallet in exclude:
                continue
            # Only prints taking our side represent liquidity we could have
            # taken instead of the wallet that took it.
            if (t.ref_signed > 0) != (direction > 0):
                continue
            if not cap_ok(t.ref_price):
                continue

            take = min(abs(t.ref_signed), want_shares - got)
            if take <= 0:
                break
            got += take
            spend += take * cost_of(t.ref_price)
            last_ts = t.ts
            if got >= want_shares - 1e-9:
                break

        vwap = spend / got if got > 0 else 0.0
        return Fill(got, want_shares, vwap, float(last_ts - ts))


def build_tapes(trades: Sequence[Trade]) -> dict[str, Tape]:
    """Group a flat list of prints into per-market tapes."""
    by_market: dict[str, list[Trade]] = {}
    for t in trades:
        by_market.setdefault(t.condition_id, []).append(t)
    return {cid: Tape(cid, ts) for cid, ts in by_market.items()}
