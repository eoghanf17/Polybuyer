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

**Maker versus taker cannot be inferred from trade count.** ``/trades``
returns only the taker side unless ``taker_only=False`` is passed, so a
wallet dominating the default feed is dominating the *aggressive* flow --
the opposite of quoting. The scanner reads both feeds and reports each
wallet's notional as taker and as maker separately. A lifetime-market count
says a wallet is automated; it says nothing about which side of the book it
sits on.

**Staleness.** ``Fetcher``'s cache has no TTL: once a URL is read it is
served from disk forever. That is right for resolved markets and wrong for
a live one, where it silently answers a question about the past. This
scanner therefore runs with ``use_cache=False`` and prints how far behind
the wall clock the newest print is, so a stale answer cannot be mistaken
for a current one.
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
#: A wallet above this many lifetime markets is automated. It does NOT
#: follow that it is quoting -- see the module docstring.
AUTOMATED_MARKETS = 5_000


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
    # Live markets: never cached. See "Staleness" above.
    f = Fetcher(cache_dir=".polycache", use_cache=False)

    print(f"  {ev.get('title')}  (ends {ev.get('endDate','')[:16]})")
    print(f"  {len(ev.get('markets') or [])} markets\n")
    print(f"  {'market':<34}{'prints':>7}{'$ bought':>11}{'$ sold':>11}"
          f"{'wallets':>8}{'last px':>9}")

    hits, movers = [], defaultdict(float)
    took, made = defaultdict(float), defaultdict(float)
    newest = 0
    truncated = []
    for m in ev.get("markets") or []:
        mt = market_tape(f, m["conditionId"])
        trs = normalise_many(mt.trades)
        if not trs:
            continue
        # Taker side first: the keys have to exist before the full feed is
        # differenced against them, or every record reads as maker.
        keys = set()
        for r in mt.trades:
            keys.add((r.get("transactionHash"), r.get("proxyWallet"),
                      r.get("side"), r.get("price"), r.get("size")))
            took[str(r.get("proxyWallet", "")).lower()] += (
                float(r.get("size", 0)) * float(r.get("price", 0)))
        # Whatever the full feed adds is the resting side.
        for r in market_tape(f, m["conditionId"], taker_only=False).trades:
            k = (r.get("transactionHash"), r.get("proxyWallet"), r.get("side"),
                 r.get("price"), r.get("size"))
            if k not in keys:
                made[str(r.get("proxyWallet", "")).lower()] += (
                    float(r.get("size", 0)) * float(r.get("price", 0)))
        trs.sort(key=lambda t: t.ts)
        newest = max(newest, trs[-1].ts)
        if mt.truncated:
            truncated.append(m["question"][:40])
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
    print(f"  {'wallet':<44}{'net $':>11}{'took $':>10}{'made $':>10}"
          f"{'lifetime':>10}  read")
    for w, v in sorted(movers.items(), key=lambda kv: -abs(kv[1]))[:8]:
        n = markets_traded(f, w)
        t, mk = took.get(w, 0.0), made.get(w, 0.0)
        read = ""
        if t + mk > 0:
            read = "aggressor" if t > 3 * mk else ("provider" if mk > 3 * t
                                                  else "both sides")
        if n >= AUTOMATED_MARKETS:
            read += " (bot)"
        if w in cl:
            read = f"** {cl[w]} **"
        print(f"  {w:<44}{v:>+11,.0f}{t:>10,.0f}{mk:>10,.0f}{n:>10,}  {read}")

    print(f"\n  cluster wallets in this event: "
          f"{hits if hits else 'NONE of the four'}")

    now = dt.datetime.now(dt.timezone.utc).timestamp()
    lag = (now - newest) / 60 if newest else None
    if lag is None:
        print("  TAPE: no prints in any market")
    else:
        stale = "  <-- STALE, treat with care" if lag > 30 else ""
        print(f"  TAPE: newest print "
              f"{dt.datetime.fromtimestamp(newest, dt.timezone.utc):%d %b %H:%M:%S} UTC, "
              f"{lag:.0f} min behind now{stale}")
    if truncated:
        print(f"  TAPE TRUNCATED (hit the per-market print cap, oldest trades "
              f"missing): {truncated}")
    else:
        print("  tape complete: no market hit the print cap")


if __name__ == "__main__":
    main()
