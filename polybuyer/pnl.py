"""Mark-to-terminal PnL and deployed capital.

Positions on Polymarket can be created and destroyed in ways that never
appear as trades -- SPLIT mints a YES+NO pair for cash, MERGE burns one back
-- so reconstructing PnL from cash flows silently overstates it unless every
one of those is captured.  The prior research phase lost a $1.16M phantom
that way before catching it.

Marking every trade to the market's terminal payoff sidesteps the problem
entirely.  For a closed market:

    pnl = ref_signed * (ref_terminal - ref_price)

summed over all of a wallet's prints in that market, which is *exactly* its
realised PnL regardless of what splits and merges happened in between.  It
needs only the tape and the resolution, both of which are authoritative.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .model import Resolution, Trade


@dataclass(frozen=True, slots=True)
class MarketPnL:
    """One wallet's result in one market."""

    wallet: str
    condition_id: str
    pnl: float
    #: Capital actually put at risk, USD -- the ROI denominator.
    capital: float
    n_trades: int
    first_ts: int
    #: Price paid on the first risk-increasing print, in reference terms.
    first_price: float
    first_direction: int
    #: Terminal value of the reference outcome.
    terminal: float

    @property
    def roi(self) -> float:
        return self.pnl / self.capital if self.capital > 0 else 0.0

    @property
    def won(self) -> bool:
        return self.pnl > 0


def trade_pnl(t: Trade, terminal: float) -> float:
    """Mark one print to the market's terminal payoff."""
    return t.ref_signed * (terminal - t.ref_price)


def cost_of(t: Trade) -> float:
    """Cash paid to acquire the exposure in this print.

    Acquiring short-reference exposure means buying the other outcome, which
    costs ``1 - ref_price`` per share.
    """
    return abs(t.ref_signed) * (t.ref_price if t.ref_signed > 0 else 1.0 - t.ref_price)


def market_pnl(
    wallet: str,
    condition_id: str,
    trades: Sequence[Trade],
    res: Resolution,
) -> MarketPnL | None:
    """Aggregate one wallet's prints in one market.

    Capital counts only *risk-increasing* prints -- those that push the
    position further from flat.  Closing a position is not fresh capital,
    and counting it as such deflates ROI for anyone who trades in and out.
    """
    if not res.is_terminal or res.ref_terminal is None:
        return None
    rows = sorted((t for t in trades if t.wallet == wallet), key=lambda t: t.ts)
    if not rows:
        return None

    terminal = res.ref_terminal
    pnl = 0.0
    capital = 0.0
    pos = 0.0
    first_price = rows[0].ref_price
    first_dir = 1 if rows[0].ref_signed > 0 else -1
    seen_open = False

    for t in rows:
        pnl += trade_pnl(t, terminal)
        new = pos + t.ref_signed
        # Risk-increasing share of this print: the part that grows |pos|.
        if abs(new) > abs(pos):
            grew = abs(new) - abs(pos)
            if pos * new < 0:
                # Crossed through flat; only the far side is new risk.
                grew = abs(new)
            frac = min(1.0, grew / abs(t.ref_signed)) if t.ref_signed else 0.0
            capital += cost_of(t) * frac
            if not seen_open:
                first_price = t.ref_price
                first_dir = 1 if t.ref_signed > 0 else -1
                seen_open = True
        pos = new

    return MarketPnL(
        wallet=wallet,
        condition_id=condition_id,
        pnl=pnl,
        capital=capital,
        n_trades=len(rows),
        first_ts=rows[0].ts,
        first_price=first_price,
        first_direction=first_dir,
        terminal=terminal,
    )


def roi(rows: Iterable[MarketPnL]) -> float:
    """Capital-weighted ROI across markets."""
    rows = list(rows)
    cap = sum(r.capital for r in rows)
    return sum(r.pnl for r in rows) / cap if cap > 0 else 0.0


def drop_best(rows: Sequence[MarketPnL], n: int) -> list[MarketPnL]:
    """Remove the ``n`` most profitable markets.

    An edge that evaporates when its best few markets are removed is a
    couple of lucky bets wearing a track record.
    """
    return sorted(rows, key=lambda r: r.pnl)[: max(0, len(rows) - n)]
