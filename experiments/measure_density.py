"""Measure what the armed watchlist would actually cost, exactly.

`costs.py` estimated from two blind tests: 5-10 posts per market-hour, both
figures floors because both runs capped max_results, and both windows sat
immediately before a repricing so they were the busiest hours those markets
had. The discount from that peak to an average hour -- `quiet_factor` -- was
a guess, and the largest source of error in the whole projection.

It does not have to be a guess. `/2/tweets/counts/recent` returns the number
of posts matching a query in hourly buckets over seven days, and it does
**not consume post quota**: eight calls left `project_usage` unchanged at
1,982. So every rule in the watchlist can be measured against real traffic
for free, rather than sampling a handful for $5.

What this measures is the exact thing that gets billed: posts the filtered
stream would have delivered, per rule, per hour.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.newsdesk.config import load
from polybuyer.newsdesk.rules import build_rules
from polybuyer.newsdesk.store import Store

OUT = "experiments/density.json"


def counts(bearer: str, query: str, retries: int = 4):
    """Hourly post counts for the last 7 days. Returns (total, buckets)."""
    p = urllib.parse.urlencode({"query": query, "granularity": "hour"})
    req = urllib.request.Request(
        f"https://api.x.com/2/tweets/counts/recent?{p}",
        headers={"Authorization": f"Bearer {bearer}"})
    for k in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as h:
                d = json.loads(h.read().decode())
                return (int(d.get("meta", {}).get("total_tweet_count", 0)),
                        d.get("data", []))
        except Exception as e:
            msg = str(e)
            if "429" in msg:
                time.sleep(15 * (k + 1))
                continue
            if "400" in msg:
                return None, []          # malformed rule; report separately
            time.sleep(3 * (k + 1))
    return None, []


def main() -> None:
    s = load()
    store = Store(s.db_path)
    markets = store.armed_markets()
    print(f"  {len(markets)} armed markets")

    jobs = []
    for m in markets:
        for r in build_rules(m):
            jobs.append((m["condition_id"], m["question"], r.tag, r.value))
    print(f"  {len(jobs)} stream rules to measure "
          f"(counts calls are free -- usage was flat across a control run)\n")

    rows, bad, t0 = [], 0, time.time()
    hourly = {}
    for i, (cid, q, tag, rule) in enumerate(jobs, 1):
        total, buckets = counts(s.x_bearer, rule)
        if total is None:
            bad += 1
        else:
            rows.append({"cid": cid, "q": q, "tag": tag, "rule": rule,
                         "total_7d": total, "per_hour": total / 168.0,
                         "buckets": len(buckets)})
            for b in buckets:
                hourly[b["start"]] = hourly.get(b["start"], 0) + b["tweet_count"]
        if i % 50 == 0:
            done = sum(r["total_7d"] for r in rows)
            print(f"    {i}/{len(jobs)}  {done:,} posts/7d so far  "
                  f"{time.time()-t0:.0f}s", flush=True)
        time.sleep(0.35)

    json.dump({"rules": rows, "hourly": hourly, "malformed": bad},
              open(OUT, "w"), indent=1)

    tot7 = sum(r["total_7d"] for r in rows)
    per_h = tot7 / 168.0
    print(f"\n  {len(rows)} rules measured, {bad} rejected by X as malformed")
    print(f"  {tot7:,} posts in 7 days = {per_h:,.0f}/hour = "
          f"{per_h*24:,.0f}/day")
    print(f"  cost: ${per_h*24*0.005:,.2f}/day  ${per_h*24*30*0.005:,.0f}/month")
    print(f"  per market: {per_h/max(len(markets),1):.2f} posts/hour")

    top = sorted(rows, key=lambda r: -r["total_7d"])[:12]
    print(f"\n  loudest rules:")
    for r in top:
        print(f"    {r['per_hour']:>8,.1f}/h  ${r['per_hour']*24*30*0.005:>8,.0f}/mo  "
              f"{r['q'][:44]:<46} {r['rule'][:44]}")
    quiet = sum(1 for r in rows if r["total_7d"] == 0)
    print(f"\n  {quiet} rules matched nothing at all in 7 days")
    print(f"  -> {OUT}")
    store.close()


if __name__ == "__main__":
    main()
