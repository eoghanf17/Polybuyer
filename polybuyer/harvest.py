"""Candidate generation.

There is no leaderboard listing endpoint -- ``lb-api/leaderboard`` 404s, and
``rank`` only answers for an address you already have.  So the candidate pool
has to be built from the tape.

Sweeping large recent trades is the right bias rather than a compromise: it
selects for traders who are active now and sizing meaningfully, which is
exactly the population worth screening.  A dormant wallet with a great
2024 is not a follow candidate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import Config
from .netio import Fetcher
from .sources import big_trades, market_tape, recent_trades


@dataclass
class Candidate:
    wallet: str
    trades_seen: int = 0
    notional_seen: float = 0.0
    markets: set[str] = field(default_factory=set)
    name: str = ""
    last_ts: int = 0

    @property
    def avg_notional(self) -> float:
        return self.notional_seen / self.trades_seen if self.trades_seen else 0.0


def _absorb(cands: dict[str, Candidate], rows: list[dict]) -> None:
    for r in rows:
        w = str(r.get("proxyWallet") or "").strip().lower()
        if not w:
            continue
        try:
            notional = float(r.get("size", 0)) * float(r.get("price", 0))
            ts = int(float(r.get("timestamp", 0)))
        except (TypeError, ValueError):
            continue
        c = cands.setdefault(w, Candidate(wallet=w))
        c.trades_seen += 1
        c.notional_seen += notional
        c.last_ts = max(c.last_ts, ts)
        cid = str(r.get("conditionId") or "")
        if cid:
            c.markets.add(cid)
        if not c.name:
            c.name = str(r.get("name") or r.get("pseudonym") or "")


def sweep(fetch: Fetcher, cfg: Config, include_unfiltered: bool = True) -> dict[str, Candidate]:
    """Build a candidate pool from the recent global tape."""
    cands: dict[str, Candidate] = {}
    _absorb(cands, big_trades(fetch, cfg.harvest.cash_filter_usd,
                              cfg.harvest.page_limit, cfg.harvest.pages))
    if include_unfiltered:
        _absorb(cands, recent_trades(fetch, cfg.harvest.page_limit,
                                     max(4, cfg.harvest.pages // 4)))
    return cands


def shortlist(cands: dict[str, Candidate], cfg: Config) -> list[Candidate]:
    """Rank candidates for the expensive deep analysis.

    Ordered by distinct markets first, notional second: breadth is what makes
    a trader *measurable*, and a wallet with one enormous trade cannot be
    assessed no matter how large it is.
    """
    rows = sorted(
        cands.values(),
        key=lambda c: (len(c.markets), c.notional_seen),
        reverse=True,
    )
    return rows[: cfg.harvest.max_candidates]


def collect_markets(
    fetch: Fetcher,
    condition_ids: list[str],
) -> tuple[list[dict], dict[str, bool]]:
    """Fetch full tapes for a set of markets.

    Returns the raw prints plus a per-market truncation flag.  A truncated
    tape cannot support fill simulation for trades older than its window;
    callers must respect the flag rather than silently analysing the wrong
    period.
    """
    rows: list[dict] = []
    truncated: dict[str, bool] = {}
    for cid in condition_ids:
        tape = market_tape(fetch, cid)
        rows.extend(tape.trades)
        truncated[cid] = tape.truncated
    return rows, truncated
