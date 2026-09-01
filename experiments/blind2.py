"""Blind test 2: do topic rules catch what account rules missed?

Rules and thresholds fixed in KEYWORD_RULES.md before this ran.
"""
from __future__ import annotations
import datetime as dt, json, os, sys, time, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polybuyer.model import normalise_many
from polybuyer.netio import Fetcher
from polybuyer.newsdesk.config import load
from polybuyer.newsdesk.gate import decide
from polybuyer.newsdesk.llm import ask
from polybuyer.sources import market_tape
from polybuyer.tape import Tape

B = os.environ["X_BEARER_TOKEN"]
THRESHOLDS = [0, 10_000, 50_000, 250_000]
RULES = [
 ("Andy Burnham visit", "(Burnham) (Kyiv OR Ukraine OR visit)"),
 ("Cap launch a token", "(Cap OR $CAP) (token OR TGE OR airdrop OR launch)"),
 ("Squid launch a token", "(Squid OR $SQUID) (token OR TGE OR airdrop OR launch)"),
 ("Citrea launch a token", "(Citrea OR $CBTC) (token OR TGE OR airdrop OR mainnet)"),
 ("Nasdaq-100", "(SpaceX) (Nasdaq OR index OR listing)"),
 ("Arcium launch a token", "(Arcium OR $ARX) (token OR TGE OR airdrop)"),
 ("Maia Sandu visit", "(Sandu) (Kyiv OR Ukraine OR visit)"),
 ("OBJ sign", "(OBJ OR \"Odell Beckham\") (sign OR signs OR signed OR agrees)"),
]

def repricing(f, cid):
    t = market_tape(f, cid); trs = normalise_many(t.trades)
    if len(trs) < 20: return None
    tp = Tape(cid, trs)
    for tr in tp.trades:
        if tr.ref_price >= 0.90:
            n = tp.median_price(tr.ts, tr.ts + 6*3600)
            if n is not None and n >= 0.85: return tr.ts
    return None

def search(q, a, b, n=60):
    p = urllib.parse.urlencode({"query": f"{q} lang:en", "max_results": min(n,100),
        "start_time": a, "end_time": b, "tweet.fields": "created_at",
        "expansions": "author_id", "user.fields": "username,public_metrics"})
    r = urllib.request.Request(f"https://api.x.com/2/tweets/search/all?{p}",
                               headers={"Authorization": f"Bearer {B}"})
    for k in range(3):
        try:
            with urllib.request.urlopen(r, timeout=30) as h:
                d = json.loads(h.read().decode())
                u = {x["id"]: x for x in d.get("includes", {}).get("users", [])}
                return [{"handle": u.get(t["author_id"], {}).get("username", "?"),
                         "followers": u.get(t["author_id"], {}).get("public_metrics", {}).get("followers_count", 0),
                         "at": t["created_at"], "text": t["text"]} for t in d.get("data", [])]
        except Exception as e:
            if "429" in str(e): time.sleep(5*(k+1)); continue
            return []
    return []

def main():
    s = load(); f = Fetcher(cache_dir=".polycache")
    mkts = json.load(open("/tmp/claude-0/-home-user-Polybuyer/"
                          "92cecb2d-4fa2-57e6-b25a-7bfae31c1f90/scratchpad/blind2.json"))
    results = []
    for frag, rule in RULES:
        m = next((x for x in mkts if frag.split()[0].lower() in x["q"].lower()), None)
        if not m: continue
        ts = repricing(f, m["cid"])
        if ts is None:
            print(f"\n### {frag}: no clean repricing"); continue
        t = dt.datetime.fromtimestamp(ts, dt.timezone.utc)
        posts = search(rule, (t - dt.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                       t.strftime("%Y-%m-%dT%H:%M:%SZ"))
        print(f"\n### {frag}  repriced {t:%Y-%m-%d %H:%M} -- {len(posts)} posts matched", flush=True)
        by_thr = {}
        for thr in THRESHOLDS:
            elig = [p for p in posts if p["followers"] >= thr]
            fired = None
            for p in elig[:25]:
                r = ask({"question": m["q"], "rules": "Resolves YES per the market title."},
                        p["text"], p["handle"], s.openai_key, s.gate_model)
                act, _ = decide(r.result, 1)
                if act in ("fire", "corroborate"):
                    fired = p; break
            by_thr[thr] = {"eligible": len(elig), "hit": bool(fired),
                           "handle": fired["handle"] if fired else None,
                           "followers": fired["followers"] if fired else None,
                           "text": fired["text"][:100] if fired else None}
            tag = f"HIT @{fired['handle']} ({fired['followers']:,}f)" if fired else "miss"
            print(f"    thr {thr:>7,}: {len(elig):>3} eligible -> {tag}")
        results.append({"market": m["q"], "matched": len(posts), "by_threshold": by_thr})
        time.sleep(2)
    print(f"\n{'='*66}")
    for thr in THRESHOLDS:
        h = sum(1 for r in results if r["by_threshold"][thr]["hit"])
        e = sum(r["by_threshold"][thr]["eligible"] for r in results)
        print(f"  followers >= {thr:>7,}: {h}/{len(results)} markets hit, "
              f"{e} posts would have been gated")
    json.dump(results, open("experiments/blind2_result.json","w"), indent=1)

if __name__ == "__main__": main()
