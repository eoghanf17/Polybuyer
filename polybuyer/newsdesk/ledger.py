"""One row per market the desk has studied, and what it paid.

The post corpus answers "did we see the news". This answers "was there a
trade in it", which turned out to be the harder question and the one the
strategy actually lives or dies on: blind test 2 caught the breaking post
in three markets, had the direction right in all three, and the aggregate
demonstrable PnL was about ten dollars, because the markets carrying those
stories had $3.5k-$11.3k of lifetime volume between them.

A number like that is only visible if depth, signal and outcome are
recorded in the same place. Kept as JSONL alongside the corpus, and for
the same reason: this is evidence, not operational state.

## What a row is honest about

Most rows are incomplete, and the schema says which parts. A market can be
recorded because a rule was written for it long before it resolves, so
``resolved``, ``terminal`` and the PnL ladder are all optional and stay
``None`` rather than defaulting to something convenient. ``sources`` names
every experiment that touched the row, so a number can be traced back to
the run that produced it.

``pnl_usd`` is never a claim about money made. Nothing here has been
traded. It is what :meth:`Tape.simulate_fill` could demonstrate was
available from prints that actually executed, which is a lower bound on
liquidity and an upper bound on nothing.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

DEFAULT_PATH = "experiments/corpus/markets.jsonl"

#: Verdicts, in increasing order of usefulness to the strategy.
NO_MARKET = "no market yet"        # post landed before the tape existed
NO_LIQUIDITY = "no liquidity"      # nothing fillable at any cap or window
FILLABLE = "fillable"              # a trade existed, however small
MISSED = "missed"                  # market repriced, our rules caught nothing
UNTESTED = "untested"              # recorded, not yet analysed


@dataclass
class MarketRecord:
    condition_id: str = ""
    question: str = ""
    slug: str = ""

    # -- resolution -------------------------------------------------------
    end_date: str = ""
    resolved: bool | None = None
    #: Terminal value on the reference axis (outcome 0). None if unresolved.
    terminal: float | None = None
    resolved_at: str = ""

    # -- depth ------------------------------------------------------------
    #: Gamma's reported lifetime volume. Double-counts sides.
    volume_usd: float | None = None
    tape_prints: int | None = None
    tape_notional_usd: float | None = None
    tape_start: str = ""
    tape_end: str = ""

    # -- what moved it ----------------------------------------------------
    #: Detected repricings: [{"at": iso, "before": f, "after": f}, ...]
    jumps: list[dict] = field(default_factory=list)

    # -- what we saw ------------------------------------------------------
    #: The post that fired, if any.
    signal_handle: str = ""
    signal_followers: int | None = None
    signal_at: str = ""
    signal_tier: str = ""
    #: Seconds between the post and the repricing it was scored against.
    signal_lead_s: float | None = None

    # -- what it would have paid -----------------------------------------
    entry_price: float | None = None
    direction: int | None = None
    #: [{"window","aggression","fillable_usd","vwap","pnl_usd","roi"}, ...]
    ladder: list[dict] = field(default_factory=list)

    verdict: str = UNTESTED
    sources: list[str] = field(default_factory=list)
    notes: str = ""

    # ---------------------------------------------------------------- api

    def best(self) -> dict | None:
        """The ladder row with the largest demonstrable PnL."""
        rows = [r for r in self.ladder if r.get("pnl_usd") is not None]
        return max(rows, key=lambda r: r["pnl_usd"]) if rows else None

    def pnl_at(self, aggression: float, size_usd: float) -> float | None:
        """PnL for a real ticket: this aggression, this much money.

        Uses the longest window available at that aggression, and caps the
        ticket at what the tape can demonstrate was fillable -- asking for
        $10 in a market that could only absorb $3 returns the $3 answer,
        not a pro-rated fiction.
        """
        rows = [r for r in self.ladder
                if abs(float(r.get("aggression", -1)) - aggression) < 1e-9
                and r.get("vwap")]
        if not rows:
            return None
        r = max(rows, key=lambda x: float(x.get("fillable_usd") or 0))
        spend = min(float(size_usd), float(r.get("fillable_usd") or 0))
        vwap = float(r["vwap"])
        if vwap <= 0:
            return None
        return (spend / vwap) * (1.0 - vwap)

    def to_json(self) -> str:
        d = asdict(self)
        b = self.best()
        d["best_pnl_usd"] = b["pnl_usd"] if b else None
        d["best_aggression"] = b["aggression"] if b else None
        return json.dumps(d, ensure_ascii=False)


def from_dict(d: dict) -> MarketRecord:
    known = set(MarketRecord.__dataclass_fields__)
    return MarketRecord(**{k: v for k, v in d.items() if k in known})


def load(path: str = DEFAULT_PATH) -> list[MarketRecord]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                out.append(from_dict(json.loads(line)))
    return out


def _merge(prev: MarketRecord, new: MarketRecord) -> MarketRecord:
    """Field-wise merge. A later run fills gaps; it does not erase.

    Every field that is empty on the incoming row keeps whatever the
    existing row had, so a cheap run that only knows a market's volume
    cannot wipe a PnL ladder an expensive one computed.
    """
    out = MarketRecord(**asdict(prev))
    for k, v in asdict(new).items():
        if v in (None, "", [], {}) or (k == "verdict" and v == UNTESTED):
            continue
        setattr(out, k, v)
    out.sources = sorted(set(prev.sources) | set(new.sources))
    return out


def save(records: Iterable[MarketRecord], path: str = DEFAULT_PATH) -> int:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    merged: dict[str, MarketRecord] = {}
    for r in records:
        key = r.condition_id or f"q:{r.question}"
        merged[key] = _merge(merged[key], r) if key in merged else r
    rows = sorted(merged.values(), key=lambda x: (x.question, x.condition_id))
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(r.to_json() + "\n")
    return len(rows)


def add(new: Iterable[MarketRecord], path: str = DEFAULT_PATH) -> int:
    """Merge rows into the ledger on disk. The 'add as you go' entry point."""
    return save([*load(path), *new], path)


def summary(records: Iterable[MarketRecord]) -> dict[str, Any]:
    """Portfolio-level arithmetic over whatever has been analysed."""
    rs = list(records)
    verdicts: dict[str, int] = {}
    for r in rs:
        verdicts[r.verdict] = verdicts.get(r.verdict, 0) + 1
    priced = [r for r in rs if r.ladder]
    best = [r.best()["pnl_usd"] for r in priced if r.best()]
    vols = [r.volume_usd for r in rs if r.volume_usd is not None]
    return {
        "markets": len(rs),
        "verdicts": verdicts,
        "priced": len(priced),
        "best_pnl_total_usd": round(sum(best), 2) if best else None,
        "median_volume_usd": sorted(vols)[len(vols) // 2] if vols else None,
        "resolved": sum(1 for r in rs if r.resolved),
    }
