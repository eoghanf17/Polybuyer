"""Stage 1: which open markets could a principal break on X?

The selection rule the desk was specified around: not rumour accounts, not
reporters — markets where **someone party to the event** would plausibly
announce it on X themselves. A company announcing its own token, a minister
announcing their own resignation, an organisation publishing its own
decision.

That is a judgement call per market, so it goes to the model. But it goes
in batches of twelve: 3,343 markets at one call each is slow and costs four
times as much for no better answer, since the question is independent per
market and the prompt is mostly fixed overhead.

Everything mechanical runs first and for free — in-play, sports, scheduled
settlement, off-platform and known-instant patterns, then a liquidity
floor — so the model only sees markets that could actually be traded.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.newsdesk.config import load as load_settings
from polybuyer.newsdesk.discover import (KNOWN_INSTANT_PAT, OFF_PLATFORM_PAT,
                                         SCHEDULED_PAT, SPORTS_PAT)
from polybuyer.newsdesk.llm import complete, text_of

MIN_LIQ = 10_000.0
BATCH = 12
OUT = "experiments/triage_open.json"

PROMPT = """You are selecting prediction markets for a news-trading desk.

The desk watches X/Twitter and fires when a post announces the resolving
event. It only works when a PRINCIPAL — a party to the event itself — would
plausibly post the announcement: the company launching its own token, the
person resigning, the government body publishing its own decision, the
organisation declaring its own result.

Reject a market when:
- resolution comes from a price, an index, a data release, or a vote count
  rather than an announcement
- only journalists or rumour accounts would carry it first
- the announcement would land somewhere else (Truth Social, a press release,
  a filing, a TV broadcast) rather than on X
- the resolving event is continuous or gradual rather than a single moment

For each market reply with:
  "id": the number given
  "ok": true only if a principal would plausibly announce this on X
  "who": the principal, named as concretely as you can (an org or person),
         or "" when ok is false
  "why": at most 12 words

MARKETS:
{items}

Reply with JSON only: {{"results": [{{"id": 0, "ok": true, "who": "...", "why": "..."}}]}}"""


def main() -> None:
    s = load_settings()
    if not s.openai_key:
        sys.exit("OPENAI_API_KEY not set")
    uni = json.load(open("experiments/open_universe.json"))

    pool = []
    for m in uni:
        blob = f"{m['q']} {m['desc']}"
        if m["gst"] or SPORTS_PAT.search(m["q"]) or SCHEDULED_PAT.search(blob) \
           or OFF_PLATFORM_PAT.search(m["q"]) or KNOWN_INSTANT_PAT.search(blob):
            continue
        if m["liq"] < MIN_LIQ:
            continue
        pool.append(m)
    pool.sort(key=lambda m: -m["liq"])
    print(f"  {len(pool)} open markets past screens with >= ${MIN_LIQ:,.0f} liquidity")
    print(f"  {(len(pool)+BATCH-1)//BATCH} batched calls\n")

    out, t0 = [], time.time()
    for i in range(0, len(pool), BATCH):
        chunk = pool[i:i + BATCH]
        items = "\n".join(
            f'{j}. {m["q"]}  [resolves {m["end"][:10]}]' for j, m in enumerate(chunk))
        payload, err = complete(PROMPT.format(items=items), s.openai_key,
                                s.gate_model, timeout=45)
        if err:
            print(f"    ! batch {i//BATCH}: {err}")
            continue
        try:
            j = json.loads(re.search(r"\{.*\}", text_of(payload), re.S).group(0))
            res = j.get("results", [])
        except (AttributeError, ValueError, TypeError):
            print(f"    ! batch {i//BATCH}: unparseable")
            continue
        for r in res:
            try:
                m = chunk[int(r["id"])]
            except (KeyError, ValueError, TypeError, IndexError):
                continue
            if r.get("ok") is True:
                out.append({**m, "who": str(r.get("who", ""))[:120],
                            "why": str(r.get("why", ""))[:120]})
        if (i // BATCH) % 20 == 0:
            print(f"    {i+len(chunk)}/{len(pool)}  accepted {len(out)}  "
                  f"{time.time()-t0:.0f}s", flush=True)

    json.dump(out, open(OUT, "w"), indent=1)
    print(f"\n  {len(out)} accepted of {len(pool)} ({len(out)/max(len(pool),1):.1%})")
    print(f"  -> {OUT}")
    for m in out[:15]:
        print(f"    ${m['liq']:>9,.0f}  {m['q'][:58]:<60} {m['who'][:28]}")


if __name__ == "__main__":
    main()
