"""What the strategy would have made, on markets that actually resolved.

For each filter-passing market that resolved YES: recover the moment the
market repriced from its tape, pull what the principal posted around it, run
every post through the live gate, and price the trade the strategy would
have put on.

The trade is priced the way the strategy would place it -- at the pre-move
price plus the aggression setting, held to resolution -- and only counted
when the gate fires on a post that PRECEDES the repricing. A post that lands
after the market has moved is not a signal, it is confirmation of a trade
already gone.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.config import DEFAULT
from polybuyer.model import normalise_many
from polybuyer.netio import Fetcher
from polybuyer.newsdesk.config import load
from polybuyer.newsdesk.gate import decide
from polybuyer.newsdesk.llm import ask
from polybuyer.sources import market_tape
from polybuyer.tape import Tape

SIZE_USD = 10.0
AGGRESSION = 0.05
GUARD_5M = GUARD_1H = GUARD_2H = 0.20

# market question fragment -> (handle, keyword query)
PRINCIPALS = {
    "MegaETH": ("megaeth", "token OR TGE OR launch OR live OR mainnet"),
    "EdgeX": ("edgeX_exchange", "token OR TGE OR launch OR live"),
    "Flying Tulip": ("flyingtulip_", "token OR TGE OR launch OR live"),
    "Trove": ("trove", "token OR TGE OR launch OR live"),
    "ETHGAS": ("ETHGASofficial", "token OR TGE OR launch OR live"),
    "Fogo": ("FogoChain", "token OR TGE OR launch OR live"),
    "Kodiak": ("KodiakFi", "token OR TGE OR launch OR live"),
    "Syrskyi": ("ZelenskyyUa", "Syrskyi OR Drapatyi OR Commander"),
    "MicroStrategy": ("saylor", "bitcoin OR BTC"),
}


def repricing(fetch: Fetcher, cid: str) -> tuple[int | None, float | None]:
    """When the market committed to certainty, and where it sat before."""
    t = market_tape(fetch, cid)
    trs = normalise_many(t.trades)
    if not trs:
        return None, None
    tape = Tape(cid, trs)
    for tr in tape.trades:
        if tr.ref_price >= 0.90:
            after = tape.slice(tr.ts, tr.ts + 6 * 3600)
            if after and all(x.ref_price >= 0.85 for x in after):
                before = tape.median_price(tr.ts - 6 * 3600, tr.ts - 300)
                return tr.ts, before
    return None, None


def posts(handle: str, terms: str, lo: dt.datetime, hi: dt.datetime,
          bearer: str, n: int = 25) -> list[dict]:
    q = urllib.parse.urlencode({
        "query": f"from:{handle} ({terms}) -is:retweet",
        "max_results": max(10, n),
        "start_time": lo.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_time": hi.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tweet.fields": "created_at"})
    r = urllib.request.Request(f"https://api.x.com/2/tweets/search/all?{q}",
                               headers={"Authorization": f"Bearer {bearer}"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(r, timeout=30) as h:
                return json.loads(h.read().decode()).get("data", []) or []
        except Exception as e:
            if "429" in str(e):
                time.sleep(4 * (attempt + 1))
                continue
            return []
    return []


def main() -> None:
    s = load()
    f = Fetcher(cache_dir=".polycache")
    mkts = json.load(open("/tmp/claude-0/-home-user-Polybuyer/"
                          "92cecb2d-4fa2-57e6-b25a-7bfae31c1f90/scratchpad/last45.json"))
    todo = [(m, k, *PRINCIPALS[k]) for m in mkts
            for k in PRINCIPALS if k.lower() in m["q"].lower()]
    print(f"{len(todo)} markets with an identified principal\n", flush=True)

    trades, misses, x_posts = [], [], 0
    for m, key, handle, terms in todo:
        ts, before = repricing(f, m["cid"])
        if ts is None or before is None:
            misses.append((m["q"], "no clean repricing in tape"))
            continue
        t = dt.datetime.fromtimestamp(ts, dt.timezone.utc)
        got = posts(handle, terms, t - dt.timedelta(hours=48),
                    t + dt.timedelta(hours=2), s.x_bearer)
        x_posts += len(got)

        mkt = {"question": m["q"], "rules": f"Resolves YES per the market title."}
        best = None
        for p in got:
            pt = dt.datetime.strptime(p["created_at"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(
                tzinfo=dt.timezone.utc)
            r = ask(mkt, p["text"], handle, s.openai_key, s.gate_model)
            act, _ = decide(r.result, 1)
            if act in ("fire", "corroborate") and pt < t:
                if best is None or pt < best[0]:
                    best = (pt, p["text"], act)
        if best is None:
            misses.append((m["q"], f"no qualifying post ({len(got)} searched)"))
            continue

        lead = (t - best[0]).total_seconds() / 60
        entry = min(0.99, before + AGGRESSION)
        shares = SIZE_USD / entry
        pnl = shares * (1.0 - entry)
        trades.append({"q": m["q"], "vol": m["vol"], "handle": handle,
                       "lead_min": lead, "before": before, "entry": entry,
                       "pnl": pnl, "action": best[2], "post": best[1][:110]})
        print(f"  HIT  {lead:>7.0f}m lead | pre {before:.2f} -> entry {entry:.2f} "
              f"| +${pnl:>6.2f} | {m['q'][:44]}", flush=True)

    print(f"\n{'='*76}")
    print(f"{len(trades)} trades from {len(todo)} candidate markets "
          f"({x_posts} posts searched, X ${x_posts*0.005:.2f})")
    if trades:
        cap = SIZE_USD * len(trades)
        tot = sum(t["pnl"] for t in trades)
        print(f"deployed ${cap:.0f} | PnL +${tot:.2f} | ROI {tot/cap:.0%}")
        leads = sorted(t["lead_min"] for t in trades)
        print(f"lead time: median {leads[len(leads)//2]:.0f} min, "
              f"min {leads[0]:.0f}, max {leads[-1]:.0f}")
    print(f"\nno trade on {len(misses)}:")
    for q, why in misses[:12]:
        print(f"  - {q[:52]}: {why}")
    json.dump({"trades": trades, "misses": misses}, open("experiments/pnl_month.json", "w"), indent=1)


if __name__ == "__main__":
    main()
