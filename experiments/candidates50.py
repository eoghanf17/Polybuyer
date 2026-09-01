"""Stage 1: find tradeable resolved markets, spending nothing on X.

The lesson from the last round is that signal quality was never the
binding constraint -- depth was. Three markets where the rule caught the
breaking post and the direction was right returned about ten dollars,
because nothing could be filled. Searching X for those was money spent to
learn something the tape already knew.

So the order is inverted here. Everything free runs first, and a market
only earns an X search by passing all of it:

1. **Resolved, and not a clock.** Sports, in-play and scheduled-settlement
   markets are excluded -- an announcement cannot precede a scoreboard.
2. **Depth.** Gamma volume over the floor.
3. **A real repricing.** `jumps.detect` with persistence, not "first print
   above 0.90". This also hands us the onset timestamp, which is what makes
   the X window tight instead of 24 hours.
4. **Liquidity at the onset.** Could a ticket actually have been filled in
   the minutes after the move started? This is the filter that would have
   removed all three of last round's hits before a single post was read.
5. **The don't-chase guards.** Evaluated at the onset. A market that had
   already run before the news landed is one we would not have traded, so
   there is no reason to pay to find the post.

Only survivors of 1-5 go to stage 2 and cost anything.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.config import JumpConfig
from polybuyer.jumps import detect
from polybuyer.model import normalise_many
from polybuyer.netio import Fetcher
from polybuyer.newsdesk import ledger as L
from polybuyer.newsdesk.discover import (KNOWN_INSTANT_PAT, SCHEDULED_PAT,
                                         SPORTS_PAT, OFF_PLATFORM_PAT)
from polybuyer.newsdesk.guards import WINDOWS, evaluate
from polybuyer.sources import market_tape, top_markets
from polybuyer.tape import Tape

MIN_VOLUME = 25_000.0
#: A ticket has to be fillable at a cap we would actually pay.
TEST_CAP = 0.05
TEST_WINDOW_S = 1800
MIN_FILLABLE_USD = 200.0
CFG = JumpConfig(min_market_trades=60)
OUT = "experiments/candidates50.json"


def _iso(ts: int) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(timespec="seconds")


def _f(x) -> float:
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def guards_at(tape: Tape, ts: int, entry: float, direction: int):
    hist = {lab: tape.median_price(ts - s - 900, ts - s) for lab, s in WINDOWS}
    return evaluate(entry, hist, direction,
                    {"5m": 0.20, "1h": 0.20, "2h": 0.20, "1d": 0.30})


def main() -> None:
    want = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    f = Fetcher(cache_dir=".polycache")

    rows = top_markets(f, pages=10, per_page=100, closed=True, since_days=270)
    print(f"  {len(rows)} resolved markets from gamma")

    drops: dict[str, int] = {}
    def drop(w): drops[w] = drops.get(w, 0) + 1

    pool = []
    seen = set()
    for m in rows:
        cid = str(m.get("conditionId") or "")
        q = str(m.get("question") or "")
        if not cid or cid in seen:
            drop("dupe"); continue
        seen.add(cid)
        blob = f"{q} {m.get('description') or ''}"
        if m.get("gameStartTime"):
            drop("in-play"); continue
        if SPORTS_PAT.search(q):
            drop("sports"); continue
        if SCHEDULED_PAT.search(blob):
            drop("settles on a schedule"); continue
        if OFF_PLATFORM_PAT.search(q):
            drop("announces off-platform"); continue
        if KNOWN_INSTANT_PAT.search(blob):
            drop("settles at a known instant"); continue
        vol = _f(m.get("volumeNum")) or _f(m.get("volume"))
        if vol < MIN_VOLUME:
            drop(f"volume < ${MIN_VOLUME:,.0f}"); continue
        pool.append({"cid": cid, "q": q, "vol": vol,
                     "slug": str(m.get("slug") or ""),
                     "end": str(m.get("endDate") or "")})

    print(f"  {len(pool)} pass the free text/depth screens")
    for k, v in sorted(drops.items(), key=lambda x: -x[1]):
        print(f"      {v:>5}  {k}")

    out, recs = [], []
    checked = 0
    for m in pool:
        if len(out) >= want:
            break
        checked += 1
        try:
            trs = normalise_many(market_tape(f, m["cid"]).trades)
        except Exception:
            drop("tape error"); continue
        if len(trs) < 60:
            drop("tape too thin"); continue
        tape = Tape(m["cid"], trs)
        last = tape.median_price(tape.end - 3600, tape.end + 1)
        if last is None:
            drop("no terminal"); continue
        terminal = 1.0 if last >= 0.5 else 0.0

        jumps = detect(tape, CFG, terminal=terminal)
        if not jumps:
            drop("no persistent repricing"); continue
        # The resolving move: the last jump that ends on the winning side.
        resolving = [j for j in jumps
                     if (j.after >= 0.5) == (terminal >= 0.5)]
        if not resolving:
            drop("no jump toward the outcome"); continue
        j = resolving[-1]

        direction = j.direction
        payoff = terminal if direction > 0 else 1.0 - terminal
        fill = tape.simulate_fill(j.onset_ts, j.before, direction,
                                  want_shares=1e9, cap=TEST_CAP,
                                  window_s=TEST_WINDOW_S)
        fillable = fill.shares * fill.vwap
        if fillable < MIN_FILLABLE_USD:
            drop(f"< ${MIN_FILLABLE_USD:,.0f} fillable at the onset"); continue

        g = guards_at(tape, j.onset_ts, j.before, direction)
        if not g.passed:
            drop("guards: already repriced before onset"); continue

        pnl = fill.shares * (payoff - fill.vwap)
        rec = {
            "cid": m["cid"], "q": m["q"], "vol": m["vol"], "slug": m["slug"],
            "terminal": terminal, "onset": _iso(j.onset_ts),
            "onset_ts": j.onset_ts,
            "before": round(j.before, 4), "after": round(j.after, 4),
            "direction": direction, "payoff": payoff,
            "fillable_usd": round(fillable, 2), "vwap": round(fill.vwap, 4),
            "pnl_usd": round(pnl, 2),
            "roi": round(pnl / fillable, 4) if fillable else 0.0,
            "n_jumps": len(jumps), "prints": len(trs),
            "guard_moves": {k: round(v, 4) for k, v in g.moves.items()},
        }
        out.append(rec)
        recs.append(L.MarketRecord(
            condition_id=m["cid"], question=m["q"], slug=m["slug"],
            end_date=m["end"], volume_usd=m["vol"], resolved=True,
            terminal=terminal, tape_prints=len(trs),
            tape_notional_usd=round(sum(t.notional for t in trs), 2),
            tape_start=_iso(tape.start), tape_end=_iso(tape.end),
            jumps=[{"at": _iso(x.onset_ts), "before": round(x.before, 4),
                    "after": round(x.after, 4)} for x in jumps],
            entry_price=j.before, direction=direction,
            verdict=L.FILLABLE, sources=["candidates50"],
            notes=(f"onset {_iso(j.onset_ts)}; ${fillable:,.0f} fillable at "
                   f"{TEST_CAP:.0%} in {TEST_WINDOW_S//60}min; guards passed"),
        ))
        print(f"  [{len(out):>2}] {m['q'][:52]:<54} ${m['vol']:>9,.0f} "
              f"{j.before:.2f}->{j.after:.2f} fill ${fillable:>7,.0f} "
              f"pnl ${pnl:>7,.0f}", flush=True)

    json.dump(out, open(OUT, "w"), indent=1)
    L.add(recs)
    print(f"\n  {len(out)} tradeable candidates from {checked} tapes examined")
    print(f"  drops: {json.dumps(dict(sorted(drops.items(), key=lambda x: -x[1])), indent=2)}")
    print(f"  -> {OUT}, and merged into the ledger")


if __name__ == "__main__":
    main()
