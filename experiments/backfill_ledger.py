"""Seed the market ledger from every experiment run so far.

Polymarket tapes are free and mostly already cached, so depth is measured
here rather than left blank -- depth is the finding the ledger exists to
make visible, and a row without it is close to useless.

The market lists themselves lived in the session scratchpad, which is
reclaimed when the container goes. They are copied into the repo as part of
this, so the ledger can be rebuilt without them.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.config import JumpConfig
from polybuyer.jumps import detect
from polybuyer.model import normalise_many
from polybuyer.netio import Fetcher
from polybuyer.newsdesk import ledger as L
from polybuyer.sources import market_tape
from polybuyer.tape import Tape

SP = ("/tmp/claude-0/-home-user-Polybuyer/"
      "92cecb2d-4fa2-57e6-b25a-7bfae31c1f90/scratchpad/")
LISTS = "experiments/corpus/market_lists.json"
CFG = JumpConfig(min_market_trades=40)


def _iso(ts: int) -> str:
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat(timespec="seconds")


def market_lists() -> dict[str, list[dict]]:
    """Read the scratchpad lists, or the repo copy if they are gone."""
    if os.path.exists(LISTS):
        return json.load(open(LISTS))
    out = {}
    for name, fn in (("blind1", "blind.json"), ("blind2", "blind2.json")):
        p = os.path.join(SP, fn)
        if os.path.exists(p):
            out[name] = json.load(open(p))
    os.makedirs(os.path.dirname(LISTS), exist_ok=True)
    json.dump(out, open(LISTS, "w"), indent=1)
    return out


def enrich(f: Fetcher, r: L.MarketRecord) -> None:
    """Measure depth, resolution and repricings off the tape."""
    try:
        mt = market_tape(f, r.condition_id)
    except Exception as e:
        r.notes = f"tape unavailable: {e}"
        return
    trs = normalise_many(mt.trades)
    if not trs:
        r.tape_prints = 0
        return
    tape = Tape(r.condition_id, trs)
    r.tape_prints = len(trs)
    r.tape_notional_usd = round(sum(t.notional for t in trs), 2)
    r.tape_start, r.tape_end = _iso(tape.start), _iso(tape.end)

    last = tape.median_price(tape.end - 3600, tape.end + 1)
    if last is not None:
        r.terminal = 1.0 if last >= 0.5 else 0.0
        # Settled to a corner and stopped trading -> treat as resolved.
        r.resolved = bool(last >= 0.95 or last <= 0.05)
        if r.resolved:
            r.resolved_at = r.tape_end
    r.jumps = [{"at": _iso(j.onset_ts), "before": round(j.before, 4),
                "after": round(j.after, 4)}
               for j in detect(tape, CFG, terminal=r.terminal)]


def main() -> None:
    f = Fetcher(cache_dir=".polycache")
    lists = market_lists()
    recs: dict[str, L.MarketRecord] = {}

    for source, rows in lists.items():
        for m in rows:
            cid = m.get("cid") or ""
            if not cid:
                continue
            recs[cid] = L.MarketRecord(
                condition_id=cid, question=m.get("q", ""),
                end_date=str(m.get("end", "")),
                volume_usd=float(m.get("vol") or 0) or None,
                sources=[source],
            )
    print(f"  {len(recs)} markets from the blind-test lists")

    by_q = {r.question: r for r in recs.values()}

    # blind test 2 scoring: which threshold, if any, caught it.
    p = "experiments/blind2_result.json"
    if os.path.exists(p):
        for row in json.load(open(p)):
            r = by_q.get(row["market"])
            if r is None:
                continue
            hits = {t: v for t, v in row["by_threshold"].items() if v["hit"]}
            r.sources = sorted(set(r.sources) | {"blind2/keyword_rules"})
            if hits:
                lowest = min(hits, key=lambda t: int(t))
                r.signal_handle = hits[lowest]["handle"] or ""
                r.signal_followers = hits[lowest]["followers"]
                r.signal_tier = "keyword"
                r.notes = (f"blind2: caught at follower floors "
                           f"{sorted(int(t) for t in hits)}; "
                           f"{row['matched']} posts matched the rule")
            else:
                r.verdict = L.MISSED
                r.notes = (f"blind2: {row['matched']} posts matched the rule, "
                           f"none passed the gate at any floor")

    # The three priced markets.
    p = "experiments/hit_pnl.json"
    if os.path.exists(p):
        for row in json.load(open(p)):
            r = by_q.get(row["market"])
            if r is None:
                continue
            r.entry_price = row.get("entry")
            r.ladder = row.get("ladder", []) or []
            r.verdict = row.get("verdict", L.UNTESTED)
            r.signal_handle = row.get("handle") or r.signal_handle
            r.signal_followers = row.get("followers") or r.signal_followers
            r.direction = 1
            r.sources = sorted(set(r.sources) | {"hit_pnl"})

    print(f"  measuring depth off tapes for {len(recs)} markets...")
    for i, r in enumerate(recs.values(), 1):
        enrich(f, r)
        if i % 10 == 0:
            print(f"    {i}/{len(recs)}", flush=True)

    n = L.add(list(recs.values()))
    rows = L.load()
    s = L.summary(rows)
    print(f"\n  ledger: {n} markets -> {L.DEFAULT_PATH}")
    print(f"  {json.dumps(s, indent=2)}")

    priced = [r for r in rows if r.ladder]
    if priced:
        print("\n  what the desk's configured sizes would have made:")
        print(f"  {'market':<46} {'tier2 $3@2c':>12} {'tier1 $10@5c':>13}")
        t2 = t1 = 0.0
        for r in priced:
            a, b = r.pnl_at(0.02, 3.0), r.pnl_at(0.05, 10.0)
            t2 += a or 0.0
            t1 += b or 0.0
            print(f"  {r.question[:45]:<46} "
                  f"{('$%.2f' % a) if a is not None else '-':>12} "
                  f"{('$%.2f' % b) if b is not None else '-':>13}")
        print(f"  {'TOTAL':<46} {'$%.2f' % t2:>12} {'$%.2f' % t1:>13}")


if __name__ == "__main__":
    main()
