"""How much of the universe did we actually look at, and where does it go?

The claim under test is "two tradeable signals in six months". That number
came from a run whose universe was the **top 1,000 markets by volume** --
`top_markets(pages=10, per_page=100)`. Polymarket lists far more than
that, so before touching any filter it is worth knowing whether the
funnel was tight or the sample was small.

Gamma paging is free, so this stage costs nothing.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.netio import Fetcher
from polybuyer.newsdesk.discover import (KNOWN_INSTANT_PAT, OFF_PLATFORM_PAT,
                                         SCHEDULED_PAT, SPORTS_PAT)
from polybuyer.sources import top_markets


def _f(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def main() -> None:
    pages = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    f = Fetcher(cache_dir=".polycache")
    rows = top_markets(f, pages=pages, per_page=100, closed=True, since_days=270)
    print(f"  gamma returned {len(rows)} resolved markets "
          f"(asked for {pages*100})")

    seen, uni = set(), []
    for m in rows:
        cid = str(m.get("conditionId") or "")
        if cid and cid not in seen:
            seen.add(cid)
            uni.append(m)
    print(f"  {len(uni)} distinct\n")

    band = 500
    print(f"  {'rank band':<14} {'min vol':>12} {'in-play':>8} {'sports':>7}"
          f" {'instant':>8} {'off-plat':>9} {'sched':>6} {'SURVIVE':>8}"
          f" {'>=25k':>7}")
    tot = {"n": 0, "surv": 0, "surv25": 0}
    for i in range(0, len(uni), band):
        chunk = uni[i:i + band]
        c = {"in-play": 0, "sports": 0, "instant": 0, "off": 0, "sched": 0}
        surv, surv25 = [], []
        for m in chunk:
            q = str(m.get("question") or "")
            blob = f"{q} {m.get('description') or ''}"
            if m.get("gameStartTime"):
                c["in-play"] += 1; continue
            if SPORTS_PAT.search(q):
                c["sports"] += 1; continue
            if SCHEDULED_PAT.search(blob):
                c["sched"] += 1; continue
            if OFF_PLATFORM_PAT.search(q):
                c["off"] += 1; continue
            if KNOWN_INSTANT_PAT.search(blob):
                c["instant"] += 1; continue
            surv.append(m)
            if (_f(m.get("volumeNum")) or _f(m.get("volume"))) >= 25_000:
                surv25.append(m)
        vols = [_f(m.get("volumeNum")) or _f(m.get("volume")) for m in chunk]
        tot["n"] += len(chunk); tot["surv"] += len(surv); tot["surv25"] += len(surv25)
        print(f"  {i}-{i+len(chunk):<9} ${min(vols):>11,.0f} {c['in-play']:>8}"
              f" {c['sports']:>7} {c['instant']:>8} {c['off']:>9} {c['sched']:>6}"
              f" {len(surv):>8} {len(surv25):>7}")

    print(f"\n  TOTAL {tot['n']} markets -> {tot['surv']} survive the text "
          f"screens -> {tot['surv25']} also clear $25k volume")
    print(f"  the first run looked at the top 1,000 only, i.e. "
          f"{1000/max(len(uni),1):.0%} of this sample")

    json.dump([{"cid": str(m.get("conditionId")), "q": str(m.get("question")),
                "vol": _f(m.get("volumeNum")) or _f(m.get("volume")),
                "slug": str(m.get("slug") or ""),
                "end": str(m.get("endDate") or "")}
               for m in uni], open("experiments/universe.json", "w"), indent=1)
    print("  -> experiments/universe.json")


if __name__ == "__main__":
    main()
