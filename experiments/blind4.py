"""Blind test 4: the expanded set, with generated rules.

Rules, windows and thresholds fixed in BLIND3.md before this ran.

Two things separate this from blind test 2. The markets were selected on
depth before any post was read, so a hit here is worth something. And PnL
is computed by entering at **the post's own timestamp**, which is the first
time the don't-chase guards have a late entry to act on.
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

from polybuyer.model import normalise_many
from polybuyer.netio import Fetcher
from polybuyer.newsdesk import corpus as C
from polybuyer.newsdesk import ledger as L
from polybuyer.newsdesk.config import load as load_settings
from polybuyer.newsdesk.gate import decide
from polybuyer.newsdesk.guards import WINDOWS, evaluate
from polybuyer.newsdesk.llm import ask
from polybuyer.sources import market_tape
from polybuyer.tape import Tape

IRAN_STRIKE = "(Iran) (strike OR strikes OR struck OR attack OR bomb)"
ROMANIA = "(Romania OR Romanian) (election OR exit poll OR wins OR won OR president)"
LIGHTER = "(lighter OR $LIGHTER) (airdrop OR claim OR live OR TGE OR token)"
MEGA_SALE = "(MegaETH OR $MEGA) (sale OR raise OR committed OR allocation)"
MEGA_FDV = "(MegaETH OR $MEGA) (FDV OR market cap OR launch OR listed OR live)"
IRAN_DEAL = "(Iran) (deal OR agreement OR nuclear OR talks OR signed)"
IRAN_MEET = "(Iran) (meeting OR meet OR talks OR negotiations OR summit)"
HEZB = "(Hezbollah OR Lebanon) (ceasefire OR truce OR agreement OR deal)"

#: question fragment -> rule. Fixed in BLIND3.md.
RULES = {
    "US strikes Iran by February 28": IRAN_STRIKE,
    "US strikes Iran by February 23": IRAN_STRIKE,
    "US strikes Iran by January 16": IRAN_STRIKE,
    "US or Israel strike Iran by January 31": IRAN_STRIKE,
    "Nicușor Dan": ROMANIA,
    "George Simion": ROMANIA,
    "Starmer out": "(Starmer) (resign OR resigns OR resignation OR quit OR ousted)",
    "lighter perform an airdrop": LIGHTER,
    "Lighter Airdrop on December 29": LIGHTER,
    "Government shutdown on Saturday":
        "(shutdown) (government OR Senate OR House OR funding OR bill OR vote)",
    "$1.2B committed to the MegaETH": MEGA_SALE,
    "MegaETH market cap (FDV)": MEGA_FDV,
    "Epstein suicide note": "(Epstein) (note OR document OR release OR released OR files)",
    "US-Iran nuclear deal by June 30": IRAN_DEAL,
    "permanent peace deal": IRAN_DEAL,
    "US x Iran meeting by April 10": IRAN_MEET,
    "Finland win Eurovision": "(Eurovision) (Finland OR wins OR won OR winner OR points)",
    "Party for Freedom":
        "(Netherlands OR Dutch OR PVV OR Wilders) (election OR exit poll OR seats OR wins)",
    "Israel x Hezbollah ceasefire by April 18": HEZB,
    "Israel x Hezbollah ceasefire by April 15": HEZB,
    "Iran x Israel/US conflict ends": "(Iran) (ceasefire OR truce OR ends OR ended OR peace)",
}

WINDOW_H = 2
MAX_RESULTS = 20
FLOORS = [0, 10_000]
CAP = 0.05
HOLD_WINDOW_S = 1800


def search(bearer, q, a, b):
    p = urllib.parse.urlencode({
        "query": f"{q} lang:en", "max_results": MAX_RESULTS,
        "start_time": a, "end_time": b,
        "tweet.fields": "created_at,public_metrics,referenced_tweets,lang",
        "expansions": "author_id",
        "user.fields": "username,public_metrics,verified"})
    r = urllib.request.Request(f"https://api.x.com/2/tweets/search/all?{p}",
                               headers={"Authorization": f"Bearer {bearer}"})
    for k in range(3):
        try:
            with urllib.request.urlopen(r, timeout=30) as h:
                d = json.loads(h.read().decode())
                users = {u["id"]: u for u in d.get("includes", {}).get("users", [])}
                out = []
                for t in d.get("data", []):
                    u = users.get(t.get("author_id", ""), {})
                    refs = t.get("referenced_tweets") or []
                    out.append({
                        "id": t.get("id", ""), "author_id": t.get("author_id", ""),
                        "handle": u.get("username", ""),
                        "followers": (u.get("public_metrics") or {}).get("followers_count"),
                        "at": t.get("created_at", ""), "text": t.get("text", ""),
                        "lang": t.get("lang", ""),
                        "is_rt": any(x.get("type") == "retweeted" for x in refs)})
                return out
        except Exception as e:
            if "429" in str(e):
                time.sleep(5 * (k + 1)); continue
            print(f"    ! {e}")
            return []
    return []


def main() -> None:
    s = load_settings()
    if not s.x_bearer or not s.openai_key:
        sys.exit("credentials missing")
    f = Fetcher(cache_dir=".polycache")

    shortlist = json.load(open("experiments/blind4_rules.json"))
    print(f"  {len(shortlist)} markets to search\n")

    # Dedupe searches: same rule, overlapping window -> one call.
    cache: dict[tuple, list] = {}
    spent = 0
    results, corpus_rows, ledger_rows = [], [], []

    for m in shortlist:
        onset = m["onset_ts"]
        a = dt.datetime.fromtimestamp(onset - WINDOW_H * 3600, dt.timezone.utc)
        b = dt.datetime.fromtimestamp(onset, dt.timezone.utc)
        key = None
        for (rule, ka, kb), posts in cache.items():
            if rule == m["rule"] and abs(ka - (onset - WINDOW_H * 3600)) < 3600 \
               and abs(kb - onset) < 3600:
                key = (rule, ka, kb); break
        if key is not None:
            posts = cache[key]
            note = f"(reused {len(posts)} posts)"
        else:
            posts = search(s.x_bearer, m["rule"],
                           a.strftime("%Y-%m-%dT%H:%M:%SZ"),
                           b.strftime("%Y-%m-%dT%H:%M:%SZ"))
            cache[(m["rule"], onset - WINDOW_H * 3600, onset)] = posts
            spent += len(posts)
            note = f"({len(posts)} posts, ${len(posts)*0.005:.2f})"

        print(f"  {m['q'][:52]:<54} {note}")
        by_floor = {}
        for floor in FLOORS:
            elig = [p for p in posts if (p["followers"] or 0) >= floor]
            fired = None
            for p in sorted(elig, key=lambda x: x["at"]):   # chronological
                r = ask({"question": m["q"], "rules": "Resolves YES per the market title."},
                        p["text"], p["handle"] or "unknown", s.openai_key, s.gate_model)
                act, _ = decide(r.result, 1 if m["direction"] > 0 else -1)
                if act in ("fire", "corroborate"):
                    fired = {**p, "gate": {"answers": r.result.answers,
                                           "direction": r.result.implied_direction,
                                           "action": act}}
                    break
            by_floor[floor] = {"eligible": len(elig), "hit": bool(fired),
                               "handle": fired["handle"] if fired else None,
                               "followers": fired["followers"] if fired else None,
                               "at": fired["at"] if fired else None,
                               "text": fired["text"] if fired else None}
            tag = (f"HIT @{fired['handle']} ({fired['followers']:,}f)"
                   if fired else "miss")
            print(f"      floor {floor:>6,}: {len(elig):>2} eligible -> {tag}")

        for p in posts:
            corpus_rows.append(C.Post(
                post_id=p["id"], handle=p["handle"], author_id=p["author_id"],
                followers=p["followers"], created_at=p["at"], text=p["text"],
                is_retweet=p["is_rt"], lang=p["lang"], market=m["q"],
                condition_id=m["cid"], market_repriced_at=b.isoformat(),
                source="blind4/expanded", query=m["rule"]))
        results.append({**{k: v for k, v in m.items() if k != "moves"},
                        "by_floor": by_floor})
        time.sleep(1)

    C.add(corpus_rows)
    json.dump(results, open("experiments/blind4_result.json", "w"), indent=1)
    print(f"\n{'='*70}")
    for floor in FLOORS:
        h = sum(1 for r in results if r["by_floor"][floor]["hit"])
        print(f"  floor {floor:>6,}: {h}/{len(results)} markets hit")
    print(f"  {spent} posts read (~${spent*0.005:.2f}); "
          f"{len(cache)} searches for {len(shortlist)} markets")


if __name__ == "__main__":
    main()
