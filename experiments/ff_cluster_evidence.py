"""Evidence for the cluster: membership, entry timing, fill realism.

Three checks that were run ad hoc during the session and left only in
conversation. They are the basis for claims in FOOTBALLFAN_LADDER.md, so
they belong in the repo where they can be re-run and disputed.

1. **Membership.** The four wallets should form a closed network -- every
   pair connected by direct on-chain transfers. A star (everyone connected
   to one hub and not to each other) is what single-seed heuristics kept
   producing, and is not evidence of common control.

2. **Entry timing.** `game_start_time` says a market is *about* a scheduled
   match, not that a trade happened during one. Conflating those labelled
   the strategy a broadcast latency race when 95% of entries precede
   kickoff.

3. **Fill realism.** `simulate_fill` consumes prints that actually
   executed, but if the order is most of the flow in its window the fill is
   not credible. This measures the order as a share of same-side executed
   volume.
"""

from __future__ import annotations

import collections
import datetime as dt
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.clusters import USDC, _norm
from polybuyer.config import DEFAULT
from polybuyer.model import normalise_many, resolution_from_clob
from polybuyer.netio import Fetcher
from polybuyer.sources import market_resolution, market_tape, token_transfers
from polybuyer.tape import Tape
from polybuyer.targets import FOOTBALLFAN_CLUSTER, FOOTBALLFAN_WALLETS

OUT = "experiments/ff_cluster_evidence.json"
SAMPLE = 250


def membership(f) -> dict:
    name = {m.address.lower(): m.handle for m in FOOTBALLFAN_CLUSTER}
    ns = set(name)
    edges, usdc = collections.Counter(), collections.Counter()
    tx = {}
    for a in ns:
        tx[a] = token_transfers(f, a)
    for rows in tx.values():
        for r in rows:
            s, d = _norm(r.get("from")), _norm(r.get("to"))
            if s in ns and d in ns and s != d:
                k = tuple(sorted((s, d)))
                edges[k] += 1
                if _norm(r.get("contractAddress")) in USDC:
                    usdc[k] += 1
    deg = collections.Counter()
    for a, b in edges:
        deg[a] += 1; deg[b] += 1
    n = len(ns)
    return {
        "wallets": {name[a]: a for a in sorted(ns)},
        "transfers_seen": {name[a]: len(tx[a]) for a in sorted(ns)},
        "pairs_connected": len(edges),
        "pairs_possible": n * (n - 1) // 2,
        "edges": [{"a": name[a], "b": name[b], "transfers": c,
                   "usdc_transfers": usdc[(a, b)]}
                  for (a, b), c in edges.most_common()],
        "degree": {name[a]: deg[a] for a in sorted(ns)},
        "closed_network": len(edges) == n * (n - 1) // 2
                          and all(deg[a] == n - 1 for a in ns),
    }


def timing(f, positions) -> dict:
    cids = sorted({p["cid"] for p in positions})
    gst = {}
    for cid in cids:
        pay = market_resolution(f, cid)
        if not pay:
            continue
        r = resolution_from_clob(cid, pay)
        if r.game_start_ts:
            gst[cid] = r.game_start_ts
    buckets = collections.Counter()
    leads = []
    for p in positions:
        g = gst.get(p["cid"])
        if g is None:
            buckets["no kickoff time"] += 1; continue
        lead = (g - p["entry_ts"]) / 3600.0
        leads.append(lead)
        if lead > 24: buckets[">24h before kickoff"] += 1
        elif lead > 2: buckets["2-24h before"] += 1
        elif lead > 0: buckets["0-2h before"] += 1
        else: buckets["after kickoff (in-play)"] += 1
    leads.sort()
    return {
        "markets_with_kickoff": len(gst),
        "buckets": dict(buckets),
        "median_lead_h": statistics.median(leads) if leads else None,
        "p10_lead_h": leads[int(.1 * len(leads))] if leads else None,
        "p90_lead_h": leads[int(.9 * len(leads))] if leads else None,
        "pre_kickoff_share": (sum(1 for x in leads if x > 0) / len(leads)
                              if leads else None),
    }


def fills(f, positions) -> dict:
    cfg = DEFAULT
    cl = frozenset(FOOTBALLFAN_WALLETS)
    shares, prints = [], []
    for p in positions[:SAMPLE]:
        trs = normalise_many(market_tape(f, p["cid"]).trades)
        if not trs:
            continue
        tp = Tape(p["cid"], trs)
        pool, n = 0.0, 0
        for t in tp.slice(p["entry_ts"], p["entry_ts"] + cfg.follow.window_s + 1):
            if t.wallet in cl or t.ts <= p["entry_ts"]:
                continue
            pool += abs(t.ref_signed) * t.price
            n += 1
        if pool <= 0:
            continue
        shares.append(min(p["capital"] / pool, 1.0))
        prints.append(n)
    shares.sort()
    return {
        "sampled": len(shares),
        "median_share_of_flow": statistics.median(shares) if shares else None,
        "p90_share_of_flow": shares[int(.9 * len(shares))] if shares else None,
        "took_everything_share": (sum(1 for x in shares if x >= 0.999)
                                  / len(shares)) if shares else None,
        "median_counterparty_prints": statistics.median(prints) if prints else None,
    }


def main() -> None:
    f = Fetcher(cache_dir=".polycache")
    d = json.load(open("experiments/ff_timeline.json"))
    ps = d["positions"]["$50 → $1,000"]

    print("  1. membership")
    mem = membership(f)
    print(f"     {mem['pairs_connected']}/{mem['pairs_possible']} pairs connected, "
          f"closed_network={mem['closed_network']}")
    for e in mem["edges"]:
        print(f"       {e['a']:<14} <-> {e['b']:<14} {e['transfers']:>4} transfers "
              f"({e['usdc_transfers']} USDC)")

    print("\n  2. entry timing")
    tim = timing(f, ps)
    for k, v in sorted(tim["buckets"].items(), key=lambda x: -x[1]):
        print(f"     {v:>4}  {k}")
    print(f"     median lead {tim['median_lead_h']:+.1f}h, "
          f"{tim['pre_kickoff_share']:.0%} before kickoff")

    print(f"\n  3. fill realism (largest {SAMPLE} positions)")
    fl = fills(f, ps)
    print(f"     median share of same-side flow {fl['median_share_of_flow']:.1%}, "
          f"p90 {fl['p90_share_of_flow']:.1%}")
    print(f"     took everything available in "
          f"{fl['took_everything_share']:.1%} of positions")
    print(f"     median {fl['median_counterparty_prints']:.0f} counterparty prints "
          f"per window")

    json.dump({"membership": mem, "timing": tim, "fills": fl},
              open(OUT, "w"), indent=1)
    print(f"\n  -> {OUT}")


if __name__ == "__main__":
    main()
