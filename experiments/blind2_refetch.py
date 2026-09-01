"""Recover blind test 2's 288 posts into the corpus.

`blind2.py` kept four truncated snippets out of 288 posts it paid to read,
which leaves the run's own conclusions unauditable. In particular: Cap,
Citrea and Nasdaq-100 repriced with every post dropped, and whether that is
"nothing was posted" or "the gate missed it" decides whether the ceiling on
this strategy is the rule set or the gate. Only the posts can say.

Same eight queries, same 24h windows, same 60-post cap, so the returned set
is the one the test scored -- this recovers the evidence rather than
running a new and slightly different test. ~288 posts, ~$1.44.

The field set is wider than blind2 asked for, because the extra fields are
free once the post is being returned anyway: post ids (so a re-fetch merges
instead of duplicating), referenced_tweets (retweet status, which blind
test 1 showed matters), and full public_metrics.
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
from polybuyer.newsdesk.config import load as load_settings
from polybuyer.sources import market_tape
from polybuyer.tape import Tape

# Identical to KEYWORD_RULES.md, unchanged.
RULES = [
    ("Andy Burnham visit", "(Burnham) (Kyiv OR Ukraine OR visit)"),
    ("Cap launch a token", "(Cap OR $CAP) (token OR TGE OR airdrop OR launch)"),
    ("Squid launch a token", "(Squid OR $SQUID) (token OR TGE OR airdrop OR launch)"),
    ("Citrea launch a token", "(Citrea OR $CBTC) (token OR TGE OR airdrop OR mainnet)"),
    ("Nasdaq-100", "(SpaceX) (Nasdaq OR index OR listing)"),
    ("Arcium launch a token", "(Arcium OR $ARX) (token OR TGE OR airdrop)"),
    ("Maia Sandu visit", "(Sandu) (Kyiv OR Ukraine OR visit)"),
    ("OBJ sign", '(OBJ OR "Odell Beckham") (sign OR signs OR signed OR agrees)'),
]

MKTS = ("/tmp/claude-0/-home-user-Polybuyer/"
        "92cecb2d-4fa2-57e6-b25a-7bfae31c1f90/scratchpad/blind2.json")


def repricing(f, cid):
    """Same detection blind2 used, off the cached tape -- no new fetches."""
    t = market_tape(f, cid)
    trs = normalise_many(t.trades)
    if len(trs) < 20:
        return None
    tp = Tape(cid, trs)
    for tr in tp.trades:
        if tr.ref_price >= 0.90:
            n = tp.median_price(tr.ts, tr.ts + 6 * 3600)
            if n is not None and n >= 0.85:
                return tr.ts
    return None


def search(bearer, q, a, b, n=60):
    p = urllib.parse.urlencode({
        "query": f"{q} lang:en", "max_results": min(n, 100),
        "start_time": a, "end_time": b,
        "tweet.fields": "created_at,public_metrics,referenced_tweets,lang",
        "expansions": "author_id",
        "user.fields": "username,public_metrics,verified",
    })
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
                        "id": t.get("id", ""),
                        "author_id": t.get("author_id", ""),
                        "handle": u.get("username", ""),
                        "followers": (u.get("public_metrics") or {}).get("followers_count"),
                        "at": t.get("created_at", ""),
                        "text": t.get("text", ""),
                        "lang": t.get("lang", ""),
                        "is_rt": any(x.get("type") == "retweeted" for x in refs),
                    })
                return out
        except Exception as e:
            if "429" in str(e):
                time.sleep(5 * (k + 1))
                continue
            print(f"    ! {e}")
            return []
    return []


def main() -> None:
    s = load_settings()
    if not s.x_bearer:
        sys.exit("X_BEARER_TOKEN not set")
    f = Fetcher(cache_dir=".polycache")
    mkts = json.load(open(MKTS))

    rows, total = [], 0
    for frag, rule in RULES:
        m = next((x for x in mkts if frag.split()[0].lower() in x["q"].lower()), None)
        if not m:
            continue
        ts = repricing(f, m["cid"])
        if ts is None:
            print(f"  {frag}: no clean repricing, skipped")
            continue
        t = dt.datetime.fromtimestamp(ts, dt.timezone.utc)
        posts = search(s.x_bearer, rule,
                       (t - dt.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                       t.strftime("%Y-%m-%dT%H:%M:%SZ"))
        total += len(posts)
        print(f"  {frag:<26} {len(posts):>3} posts recovered", flush=True)
        for p in posts:
            rows.append(C.Post(
                post_id=p["id"], handle=p["handle"], author_id=p["author_id"],
                followers=p["followers"], created_at=p["at"], text=p["text"],
                is_retweet=p["is_rt"], lang=p["lang"],
                market=m["q"], condition_id=m["cid"],
                market_repriced_at=t.isoformat(),
                source="blind2/keyword_rules", query=rule,
            ))
        time.sleep(2)

    n = C.add(rows, C.DEFAULT_PATH)
    print(f"\n  {total} posts recovered (~${total * 0.005:.2f})")
    print(f"  corpus now {n} rows")


if __name__ == "__main__":
    main()
