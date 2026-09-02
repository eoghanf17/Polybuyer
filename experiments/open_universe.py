"""Every currently-open market gamma will serve, sliced past its row cap.

Same trick as the resolved sweep: one gamma query stops at 2,100 rows, so
the window is cut into slices that each fit under it. For open markets the
natural axis is the resolution date rather than the past.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.netio import Fetcher
from polybuyer.sources import GAMMA


def _f(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def slice_window(f, a, b, pages=25):
    out = []
    for p in range(pages):
        url = (f"{GAMMA}/markets?closed=false&limit=100&offset={p*100}"
               f"&order=volumeNum&ascending=false"
               f"&end_date_min={a}T00:00:00Z&end_date_max={b}T00:00:00Z")
        r = f.get(url)
        if not r or not isinstance(r, list):
            break
        out.extend(r)
        if len(r) < 100:
            break
    return out


def main() -> None:
    f = Fetcher(cache_dir=".polycache")
    today = dt.date.today()
    seen, rows = set(), []
    # Weekly slices for the next two months (where most news markets sit),
    # then monthly out to a year.
    edges = [today + dt.timedelta(days=7 * i) for i in range(9)]
    edges += [today + dt.timedelta(days=60 + 30 * i) for i in range(1, 11)]
    for a, b in zip(edges, edges[1:]):
        batch = slice_window(f, a.isoformat(), b.isoformat())
        new = [m for m in batch if str(m.get("conditionId")) not in seen]
        for m in new:
            seen.add(str(m.get("conditionId")))
        rows.extend(new)
        print(f"  {a} .. {b}: {len(batch):>5} rows, {len(new):>5} new", flush=True)

    out = [{"cid": str(m.get("conditionId")), "q": str(m.get("question") or ""),
            "desc": str(m.get("description") or "")[:1200],
            "vol": _f(m.get("volumeNum")) or _f(m.get("volume")),
            "liq": _f(m.get("liquidityNum")) or _f(m.get("liquidity")),
            "gst": bool(m.get("gameStartTime")),
            "slug": str(m.get("slug") or ""),
            "end": str(m.get("endDate") or ""),
            "tokens": m.get("clobTokenIds"), "outcomes": m.get("outcomes")}
           for m in rows if m.get("conditionId")]
    json.dump(out, open("experiments/open_universe.json", "w"))
    vols = sorted(x["vol"] for x in out)
    print(f"\n  {len(out)} distinct open markets")
    if vols:
        for q in (25, 50, 75, 90):
            print(f"    p{q} volume ${vols[int(q/100*(len(vols)-1))]:,.0f}")
    print(f"    in-play (gameStartTime): {sum(1 for x in out if x['gst'])}")
    print("  -> experiments/open_universe.json")


if __name__ == "__main__":
    main()
