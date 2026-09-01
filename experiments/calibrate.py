"""Calibrate the gate against real posts around real repricings.

Full-archive search works with an app bearer token, so the test set does not
have to be invented. For each resolved market we pull everything the
principal posted in a window spanning the moment the market repriced, then
run every post through the gate.

The announcement is in there somewhere; so is everything else that account
said that week. That mix is exactly the live problem -- one post should fire
and the rest should not -- so it measures both error rates at once, on the
real distribution rather than on cases chosen to be tricky.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.newsdesk.config import load
from polybuyer.newsdesk.gate import decide
from polybuyer.newsdesk.llm import ask

# (market, rules, handles, repricing UTC, direction)
CASES = [
    ("Will EdgeX launch a token by March 31, 2026?",
     "Resolves YES if edgeX publicly launches a tradeable token before 31 March 2026.",
     ["edgeX_exchange"], "2026-03-07 11:14", 1),
    ("Will Flying Tulip launch a token by March 31, 2026?",
     "Resolves YES if Flying Tulip publicly launches a tradeable token before 31 March 2026.",
     ["flyingtulip_"], "2026-01-10 08:03", 1),
    ("Will MicroStrategy announce holding 800k+ BTC by December 31, 2026?",
     "Resolves YES if Strategy (MicroStrategy) announces total bitcoin holdings of "
     "800,000 BTC or more before 31 December 2026.",
     ["saylor"], "2026-03-10 20:15", 1),
    ("Tesla launches unsupervised full self driving (FSD) by June 30?",
     "Resolves YES if Tesla publicly launches unsupervised FSD to customers before 30 June.",
     ["elonmusk", "Tesla"], "2025-12-14 19:47", 1),
    ("Will Oleksandr Syrskyi be out as Ukraine's Commander-in-Chief by December 31?",
     "Resolves YES if Oleksandr Syrskyi ceases to be Commander-in-Chief of Ukraine's "
     "armed forces before 31 December.",
     ["ZelenskyyUa"], "2026-07-20 13:29", 1),
]

BEFORE_H, AFTER_H, MAX_RESULTS = 36, 6, 100


def fetch(handle: str, start: dt.datetime, end: dt.datetime, bearer: str) -> list[dict]:
    q = urllib.parse.urlencode({
        "query": f"from:{handle} -is:retweet",
        "max_results": MAX_RESULTS,
        "start_time": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end_time": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tweet.fields": "created_at",
    })
    req = urllib.request.Request(
        f"https://api.x.com/2/tweets/search/all?{q}",
        headers={"Authorization": f"Bearer {bearer}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode()).get("data", []) or []
    except Exception as e:
        print(f"    fetch failed for @{handle}: {e}", file=sys.stderr)
        return []


def main() -> None:
    s = load()
    total_posts = spend_x = spend_llm = 0
    rows = []

    for q, rules, handles, when, direction in CASES:
        t = dt.datetime.strptime(when, "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc)
        lo, hi = t - dt.timedelta(hours=BEFORE_H), t + dt.timedelta(hours=AFTER_H)
        print(f"\n{'='*78}\n{q}\n  repriced {when} UTC | @{', @'.join(handles)}", flush=True)

        posts = []
        for h in handles:
            got = fetch(h, lo, hi, s.x_bearer)
            posts += [(h, p) for p in got]
        total_posts += len(posts)
        spend_x += len(posts) * 0.005
        posts.sort(key=lambda p: p[1]["created_at"])
        print(f"  {len(posts)} posts in window (-{BEFORE_H}h/+{AFTER_H}h)", flush=True)

        mkt = {"question": q, "rules": rules}
        fired = []
        for h, p in posts:
            c = ask(mkt, p["text"], h, s.openai_key, s.gate_model)
            spend_llm += c.cost_usd
            act, why = decide(c.result, direction)
            ts = dt.datetime.strptime(p["created_at"], "%Y-%m-%dT%H:%M:%S.%fZ").replace(
                tzinfo=dt.timezone.utc)
            mins = (ts - t).total_seconds() / 60
            if act == "fire":
                fired.append((mins, h, p["text"]))
            rows.append({"market": q, "handle": h, "ts": p["created_at"],
                         "mins_vs_repricing": round(mins, 1), "action": act,
                         "text": p["text"][:200]})

        print(f"  FIRED on {len(fired)}/{len(posts)}:")
        for mins, h, text in fired:
            rel = f"{mins:+.0f}m vs repricing"
            print(f"    [{rel:>18}] @{h}: {' '.join(text.split())[:88]}")
        if not fired:
            print("    (none)")

    print(f"\n{'='*78}")
    print(f"{total_posts} posts | X ${spend_x:.2f} | LLM ${spend_llm:.4f} "
          f"| total ${spend_x + spend_llm:.2f}")
    json.dump(rows, open("experiments/calibration.json", "w"), indent=1)


if __name__ == "__main__":
    main()
