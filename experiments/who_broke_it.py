"""Who actually broke each market? Scored against the blind predictions.

Searches by topic rather than by account, so the answer is not constrained
to the handles predicted -- which is the whole point. Whoever posted first
about the resolving event, inside the window where the market moved, is the
account that would have had to be watched.
"""
from __future__ import annotations
import datetime as dt, json, os, sys, time, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from polybuyer.model import normalise_many
from polybuyer.netio import Fetcher
from polybuyer.sources import market_tape
from polybuyer.tape import Tape

B = os.environ["X_BEARER_TOKEN"]

# (question fragment, topic query) -- topic only, no account restriction
TOPICS = [
    ("Khamenei", "Khamenei (supreme leader OR dead OR died OR replaced OR out)"),
    ("Graham Platner", "Platner (drop OR dropping OR withdraw OR suspend OR ends)"),
    ("SHEIN IPO", "SHEIN (IPO OR listing OR float OR listed)"),
    ("SpaceX or OpenAI IPO", "(SpaceX OR OpenAI) IPO"),
    ("Binance launch stock tokens", "Binance (stock tokens OR tokenized stocks OR equities)"),
    ("Infrared launch a token", "Infrared (token OR TGE OR airdrop OR IRED)"),
    ("Pep Guardiola", "Guardiola (leave OR leaving OR out OR exit OR steps down OR departure)"),
    ("Tria launch a token", "Tria (token OR TGE OR airdrop)"),
    ("GRVT launch a token", "GRVT (token OR TGE OR airdrop)"),
    ("António Costa visit", "(Costa) Kyiv OR Ukraine visit"),
    ("o1 launch a token", "\"o1\" (token OR TGE OR airdrop)"),
    ("Keith Kellogg visit", "Kellogg (Kyiv OR Ukraine)"),
    ("Bitmine", "Bitmine (ETH OR ethereum OR holdings)"),
]


def repricing(f, cid):
    t = market_tape(f, cid)
    trs = normalise_many(t.trades)
    if len(trs) < 20:
        return None
    tp = Tape(cid, trs)
    for tr in tp.trades:
        if tr.ref_price >= 0.90:
            nxt = tp.median_price(tr.ts, tr.ts + 6 * 3600)
            if nxt is not None and nxt >= 0.85:
                return tr.ts
    return None


def search(q, a, b, n=30):
    p = urllib.parse.urlencode({
        "query": f"{q} -is:retweet -is:reply lang:en", "max_results": n,
        "start_time": a, "end_time": b, "tweet.fields": "created_at",
        "expansions": "author_id", "user.fields": "username,public_metrics"})
    r = urllib.request.Request(f"https://api.x.com/2/tweets/search/all?{p}",
                               headers={"Authorization": f"Bearer {B}"})
    for k in range(3):
        try:
            with urllib.request.urlopen(r, timeout=30) as h:
                d = json.loads(h.read().decode())
                users = {u["id"]: u for u in d.get("includes", {}).get("users", [])}
                return [(users.get(t["author_id"], {}).get("username", "?"),
                         users.get(t["author_id"], {}).get(
                             "public_metrics", {}).get("followers_count", 0),
                         t["created_at"], t["text"]) for t in d.get("data", [])]
        except Exception as e:
            if "429" in str(e):
                time.sleep(5 * (k + 1)); continue
            return []
    return []


def main():
    f = Fetcher(cache_dir=".polycache")
    mkts = json.load(open("/tmp/claude-0/-home-user-Polybuyer/"
                          "92cecb2d-4fa2-57e6-b25a-7bfae31c1f90/scratchpad/blind.json"))
    out = []
    for frag, topic in TOPICS:
        m = next((x for x in mkts if frag.lower() in x["q"].lower()), None)
        if not m:
            continue
        ts = repricing(f, m["cid"])
        if ts is None:
            print(f"\n### {frag}: no clean repricing in tape"); continue
        t = dt.datetime.fromtimestamp(ts, dt.timezone.utc)
        posts = search(topic, (t - dt.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                       (t + dt.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"))
        posts.sort(key=lambda p: p[2])
        print(f"\n### {frag}  (repriced {t:%Y-%m-%d %H:%M} UTC) -- {len(posts)} posts")
        for u, fol, ct, tx in posts[:6]:
            mins = (dt.datetime.strptime(ct, "%Y-%m-%dT%H:%M:%S.%fZ").replace(
                tzinfo=dt.timezone.utc) - t).total_seconds() / 60
            print(f"  {mins:>+7.0f}m @{u:<20} {fol:>9,}f  {' '.join(tx.split())[:62]}")
        out.append({"market": m["q"], "repriced": t.isoformat(),
                    "posts": [{"handle": u, "followers": fol, "at": ct, "text": tx[:200]}
                              for u, fol, ct, tx in posts[:10]]})
        time.sleep(2)
    json.dump(out, open("experiments/who_broke_it.json", "w"), indent=1)


if __name__ == "__main__":
    main()
