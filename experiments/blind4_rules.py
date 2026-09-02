"""Generate the blind-test-4 shortlist and its keyword rules.

Two changes from blind test 3, both deliberate.

**Cluster capping.** 125 tradeable markets are ten events, and Iran/US is
41 of them. Searching by PnL rank would spend most of the budget
re-confirming one story. Each cluster is capped so the spend buys breadth.

**The rules are generated, not hand-written.** In blind test 3 I wrote 21
rules by hand after looking at the questions, which is a step the live
system does not have -- there, Claude reads a new market and writes the
rule. Generating them here tests the pipeline that would actually run,
including its rule-writing, rather than testing my own knowledge of what
broke each story.

Rules are written to disk and committed before any search runs.
"""

from __future__ import annotations

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.newsdesk.config import load as load_settings
from polybuyer.newsdesk.llm import complete, text_of

PER_CLUSTER = {"Iran/US conflict": 6, "other": 14}
DEFAULT_CAP = 4
OUT = "experiments/blind4_rules.json"

PROMPT = """You are writing a Twitter/X search rule to catch the post that \
breaks the news for a prediction market.

MARKET: {q}

Write ONE X search rule in this exact shape:

    (SUBJECT TERMS) (EVENT TERMS)

- SUBJECT TERMS: 2-5 alternatives naming who or what the market is about,
  separated by " OR ". Include tickers with $ where relevant.
- EVENT TERMS: 3-6 alternatives naming the thing that must happen for this
  market to resolve YES, separated by " OR ". These must be words that
  would appear in the announcement itself, not words describing the market.

Do not include operators other than OR. No quotes, no from:, no lang:.
Both bracketed groups are required.

Reply with JSON only: {{"rule": "(...) (...)"}}"""

VALID = re.compile(r"^\([^()]+\)\s*\([^()]+\)$")


def cluster(q: str) -> str:
    ql = q.lower()
    for pat, name in [
        (r"\biran\b", "Iran/US conflict"), (r"eurovision", "Eurovision"),
        (r"bitcoin|btc|ethereum|\beth\b", "Crypto price"),
        (r"romanian|simion|nicu", "Romania election"),
        (r"megaeth|lighter|airdrop|token|tge", "Token launch"),
        (r"venezuela", "Venezuela"),
        (r"hezbollah|lebanon|israel", "Israel/Lebanon"),
        (r"ukraine|russia|putin|zelensk", "Ukraine/Russia"),
        (r"shutdown|congress|senate", "US government"),
        (r"trump", "Trump"), (r"fed|rate cut|inflation|cpi", "Macro/Fed"),
        (r"oil|crude", "Oil"),
    ]:
        if re.search(pat, ql):
            return name
    return "other"


def main() -> None:
    s = load_settings()
    mkts = json.load(open("experiments/tradeable_news.json"))
    mkts.sort(key=lambda m: -m["pnl_usd"])

    picked, counts = [], {}
    for m in mkts:
        c = cluster(m["q"])
        cap = PER_CLUSTER.get(c, DEFAULT_CAP)
        if counts.get(c, 0) >= cap:
            continue
        counts[c] = counts.get(c, 0) + 1
        picked.append({**m, "cluster": c})

    print(f"  {len(picked)} markets across {len(counts)} clusters")
    for c, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"      {c:<22} {n}")

    out = []
    for m in picked:
        rule = None
        payload, err = complete(PROMPT.format(q=m["q"]), s.openai_key,
                                s.gate_model)
        if err:
            print(f"    ! {m['q'][:40]}: {err}")
        else:
            try:
                j = json.loads(re.search(r"\{.*\}", text_of(payload), re.S).group(0))
                cand = " ".join(str(j.get("rule", "")).split())
                if VALID.match(cand):
                    rule = cand
            except (AttributeError, ValueError, TypeError):
                pass
        if rule is None:
            print(f"    ! no valid rule for {m['q'][:50]}")
            continue
        out.append({**m, "rule": rule})
        print(f"  {m['q'][:52]:<54} {rule[:60]}")

    json.dump(out, open(OUT, "w"), indent=1)
    print(f"\n  {len(out)} rules -> {OUT}")


if __name__ == "__main__":
    main()
