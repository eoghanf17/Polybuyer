"""Don't-chase guards, checked immediately before any order goes out.

If the price has already moved our way, the news is in it and we are late.
The out-of-sample experiment is unambiguous that late entries are where the
money goes: ROI held flat from 0s to 45s and then fell off a cliff, so a
market that has already repriced is not a slightly worse trade, it is a
different and worse one.

A breach does more than block the order. It disarms the market. If the move
happened without us the opportunity is gone, and leaving the market armed
would only invite a later, worse fill on the same story.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

WINDOWS = (("5m", 300), ("1h", 3600), ("2h", 7200), ("1d", 86400))


@dataclass
class GuardResult:
    passed: bool
    #: Signed move over each window, positive meaning "our way".
    moves: dict[str, float]
    breached: list[str]
    mid: float
    reason: str = ""


#: A move only counts as "the news is already in the price" if there is
#: little left to win. Below this much remaining upside, a large move
#: means we are late; above it, the market is still paying.
DEFAULT_MIN_HEADROOM = 0.15


def evaluate(
    mid_now: float,
    history: dict[str, float | None],
    direction: int,
    thresholds: dict[str, float],
    min_headroom: float = DEFAULT_MIN_HEADROOM,
) -> GuardResult:
    """Compare the move over each window against its threshold.

    ``history`` maps window label to the reference-outcome price at that
    lookback, ``None`` where it is unavailable. Missing history is treated as
    passing that window rather than failing: a market too new to have an
    hour of data has not run away from us, and blocking on absent data would
    silently disarm every fresh market.

    A breach requires **both** a large move and little headroom left, and
    the second condition was added after it cost the largest trade in the
    dataset. "Iran closes its airspace by June 8" had drifted up all day on
    a developing story -- +47% over two hours, +56% over one day -- when
    @financialjuice posted "Western Iran airspace closed until further
    notice: official news agency" and the market went 0.54 to 0.93. On
    movement alone the guards blocked it. But entry was 0.583, so 42 cents
    of upside remained, and the trade was worth $140,858 at a 5c cap for
    87% ROI.

    That is the flaw the headroom term fixes: how far a price has *moved*
    says nothing about how much is *left*. A market that has run from 0.10
    to 0.55 on developing news is not a market we are late to. A market
    sitting at 0.97 is, whatever it did to get there -- and that case still
    breaches, because the headroom test catches it directly.
    """
    moves: dict[str, float] = {}
    breached: list[str] = []

    for label, _ in WINDOWS:
        then = history.get(label)
        if then is None:
            continue
        # Positive = moved in the direction we want to trade.
        move = (mid_now - then) * (1 if direction > 0 else -1)
        moves[label] = move
        limit = thresholds.get(label)
        if limit is not None and move > limit:
            breached.append(label)

    # What is still on the table. We buy at ``mid_now`` on the side we
    # want and each share pays at most 1.0, so this is known without
    # knowing the outcome.
    headroom = (1.0 - mid_now) if direction > 0 else mid_now

    if breached and headroom < min_headroom:
        detail = ", ".join(f"{w} moved {moves[w]:+.0%} (limit {thresholds[w]:.0%})"
                           for w in breached)
        return GuardResult(False, moves, breached, mid_now,
                           f"already repriced with {headroom:.0%} left: {detail}")
    if breached:
        detail = ", ".join(f"{w} {moves[w]:+.0%}" for w in breached)
        return GuardResult(True, moves, breached, mid_now,
                           f"moved ({detail}) but {headroom:.0%} headroom remains")
    return GuardResult(True, moves, [], mid_now, "within limits")


def thresholds_from(market: dict) -> dict[str, float]:
    return {
        "5m": float(market.get("guard_5m", 0.20)),
        "1h": float(market.get("guard_1h", 0.20)),
        "2h": float(market.get("guard_2h", 0.20)),
        "1d": float(market.get("guard_1d", 0.30)),
    }


def limit_price(mid: float, direction: int, aggression: float) -> float:
    """Where to put the limit, given the pre-move mid.

    ``aggression`` is how far through the mid we will pay. Expressed on the
    side actually being bought, so the caller never has to reason about which
    outcome token the order is in.
    """
    px = mid if direction > 0 else 1.0 - mid
    return max(0.001, min(0.999, px + aggression))


def size_shares(size_usd: float, limit_px: float) -> float:
    return size_usd / limit_px if limit_px > 0 else 0.0


def history_from_series(series: list[dict], now: float | None = None
                        ) -> dict[str, float | None]:
    """Pick out the price at each lookback from a CLOB price series.

    ``series`` is ``[{"t": unix_seconds, "p": price}, ...]`` as
    ``clob/prices-history`` returns it. Takes the last point at or before
    each target time; returns None where the series does not reach back.
    """
    now = now or time.time()
    pts = sorted(((int(p.get("t", 0)), float(p.get("p", 0))) for p in series
                  if p.get("t") is not None), key=lambda x: x[0])
    out: dict[str, float | None] = {}
    for label, secs in WINDOWS:
        target = now - secs
        prior = [p for t, p in pts if t <= target]
        out[label] = prior[-1] if prior else None
    return out
