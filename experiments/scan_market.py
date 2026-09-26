"""Scan a live event's tape: who is trading, which side, and is the cluster in it?

    python experiments/scan_market.py unl-isr-ire-2026-09-27-exact-score

Two traps this exists to avoid.

**Sign direction.** ``ref_signed`` is exposure to *outcome 0*, and on these
markets outcome 0 is "Yes". A wallet with a large negative figure is
**selling** the outcome, not backing it. Reading volume without the sign
inverts the answer: an exact-score market can show heavy turnover that is
entirely one desk writing the longshot.

**Volume is not interest.** Gamma reports a single volume number per
market. Split into bought-versus-sold it often turns out one-sided, and a
wallet with tens of thousands of lifetime markets is a maker providing
quotes rather than anyone with a view.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.model import normalise_many
from polybuyer.netio import Fetcher
from polybuyer.sources import market_tape, markets_traded
from polybuyer.targets import FOOTBALLFAN_CLUSTER

GAMMA = "https://gamma-api.polymarket.com"
#: A wallet above this many lifetime markets is quoting, not opining.
MAKER_MARKETS = 5_000


def fetch(url: str):
    """curl, not urllib: the agent proxy refuses urllib on this host."""
    out = subprocess.run(["curl", "-s", "--max-time", "30", url],
                         capture_output=True, text=True).stdout
    return json.loads(out) if out.strip() else None


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    slug = sys.argv[1]
    ev = fetch(f"{GAMMA}/events?slug={slug}")
    if not ev:
        sys.exit(f"no event for slug {slug}")
    ev = ev[0]
    cl = {m.address.lower(): m.handle for m in FOOTBALLFAN_CLUSTER}
    f = Fetcher(cache_dir=".polycache")

    print(f"  {ev.get('title')}  (ends {ev.get('endDate','')[:16]})")
    print(f"  {len(ev.get('markets') or [])} markets\n")
    print(f"  {'market':<34}{'prints':>7}{'$ bought':>11}{'$ sold':>11}"
          f"{'wallets':>8}{'last px':>9}")

    hits, movers = [], defaultdict(float)
    for m in ev.get("markets") or []:
        trs = normalise_many(market_tape(f, m["conditionId"]).trades)
        if not trs:
            continue
        trs.sort(key=lambda t: t.ts)
        buy = sum(t.notional for t in trs if t.ref_signed > 0)
        sell = sum(t.notional for t in trs if t.ref_signed < 0)
        q = m["question"][:33]
        print(f"  {q:<34}{len(trs):>7}{buy:>11,.0f}{sell:>11,.0f}"
              f"{len({t.wallet for t in trs}):>8}{trs[-1].ref_price:>9.3f}")
        for t in trs:
            movers[t.wallet] += t.ref_signed * t.price
            if t.wallet in cl:
                hits.append((m["question"], cl[t.wallet], t.notional))

    print(f"\n  largest net positions across the event "
          f"(+ = long the outcome, - = writing it)")
    print(f"  {'wallet':<44}{'net $':>12}{'lifetime mkts':>15}  read")
    for w, v in sorted(movers.items(), key=lambda kv: -abs(kv[1]))[:8]:
        n = markets_traded(f, w)
        read = "maker" if n >= MAKER_MARKETS else ""
        if w in cl:
            read = f"** {cl[w]} **"
        print(f"  {w:<44}{v:>+12,.0f}{n:>15,}  {read}")

    print(f"\n  cluster wallets in this event: "
          f"{hits if hits else 'NONE of the four'}")


if __name__ == "__main__":
    main()
