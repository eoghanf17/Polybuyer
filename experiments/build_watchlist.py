"""Stage 2: turn accepted markets into an armed watchlist.

Triage answered "could a principal announce this on X". Two classes still
get through it and both are the same mistake in different clothes:

**Award ceremonies.** France Football (18 Ballon d'Or markets), TIME Person
of the Year, the Nobel committee. A principal does announce these — on
stage, live, at a time everybody knows. The tweet follows the broadcast, so
the trade is a latency race against television, which is exactly what the
in-play exclusion exists to avoid.

**Live sport results.** US Open markets survive because "USTA" is a
plausible announcer.

After those, markets are capped per principal. Eighteen Ballon d'Or
contracts are one event, and the research phase's rule that the independent
unit is the event applies to arming as much as to scoring.

Each survivor then gets its stream rules and accounts generated in one
call, and is written into the desk database armed but paper-only.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.newsdesk.config import load as load_settings
from polybuyer.newsdesk.llm import complete, text_of
from polybuyer.newsdesk.rules import build_rules, lint, RuleError
from polybuyer.newsdesk.store import Market, Store

CEREMONY = re.compile(
    r"\b(ballon d'?or|person of the year|nobel|oscar|academy award|grammy|"
    r"emmy|golden globe|time100|award|prize|player of the (year|month)|"
    r"mvp|hall of fame|eurovision|miss universe)\b", re.I)
SPORT_ORG = re.compile(
    r"\b(us open|wimbledon|roland garros|australian open|masters|ryder cup|"
    r"tennis|atp|wta|pga|nascar|formula 1|f1 |grand prix)\b", re.I)
PER_PRINCIPAL = 4
MAX_MARKETS = 300

PROMPT = """You are arming a news-trading desk for one prediction market.

MARKET: {q}
RESOLVES: {end}
LIKELY ANNOUNCER: {who}

Produce:

1. "keyword": 4-8 alternatives, separated by " OR ", of words that would
   appear in the ANNOUNCEMENT ITSELF — not words describing the market.
   This is ANDed into every rule including the principal's own feed, so a
   term the principal would not use means the announcement is missed.
   Example: for "Will Arcium launch a token", the right answer is
   "token OR TGE OR airdrop OR live OR claim OR mint", NOT "Arcium".

2. "topic": 2-5 alternatives naming the subject — who or what the market is
   about. Include tickers with $ only if you are confident they exist.

3. "accounts": 2-6 real X/Twitter handles, no @, most likely first. Include
   the principal's own account where it exists. Each needs a "tier":
     "principal" — a party to the event itself
     "beat"      — a reporter who covers exactly this
     "wire"      — a news agency
   Only handles you are confident exist. Fewer is better than invented.

Reply with JSON only:
{{"keyword": "...", "topic": "...",
  "accounts": [{{"handle": "...", "tier": "...", "why": "..."}}]}}"""


def main() -> None:
    s = load_settings()
    if not s.openai_key:
        sys.exit("OPENAI_API_KEY not set")
    rows = json.load(open("experiments/triage_open.json"))

    drops = {"ceremony": 0, "sport org": 0, "principal cap": 0}
    kept, seen = [], {}
    for m in sorted(rows, key=lambda x: -x["liq"]):
        blob = f"{m['q']} {m['who']}"
        if CEREMONY.search(blob):
            drops["ceremony"] += 1; continue
        if SPORT_ORG.search(blob):
            drops["sport org"] += 1; continue
        w = m["who"].lower()[:40]
        if seen.get(w, 0) >= PER_PRINCIPAL:
            drops["principal cap"] += 1; continue
        seen[w] = seen.get(w, 0) + 1
        kept.append(m)
        if len(kept) >= MAX_MARKETS:
            break

    print(f"  {len(rows)} accepted -> {len(kept)} armed candidates")
    for k, v in drops.items():
        print(f"      dropped {v:>4}  {k}")

    store = Store(s.db_path)
    armed = failed = 0
    t0 = time.time()
    for i, m in enumerate(kept, 1):
        payload, err = complete(
            PROMPT.format(q=m["q"], end=m["end"][:10], who=m["who"]),
            s.openai_key, s.gate_model, timeout=45)
        if err:
            failed += 1; continue
        try:
            j = json.loads(re.search(r"\{.*\}", text_of(payload), re.S).group(0))
        except (AttributeError, ValueError, TypeError):
            failed += 1; continue

        toks = m.get("tokens")
        if isinstance(toks, str):
            try:
                toks = json.loads(toks)
            except ValueError:
                toks = []
        toks = toks or []
        accounts = [{"handle": str(a.get("handle", "")).lstrip("@"),
                     "tier": str(a.get("tier", "beat")),
                     "why": str(a.get("why", ""))[:160]}
                    for a in (j.get("accounts") or [])
                    if str(a.get("handle", "")).strip()]

        mk = Market(
            condition_id=m["cid"], question=m["q"], slug=m["slug"],
            rules=m["desc"][:600], end_date=m["end"], category=m["who"][:80],
            required_keyword=" ".join(str(j.get("keyword", "")).split()),
            topic_terms=" ".join(str(j.get("topic", "")).split()),
            token_id_ref=str(toks[0]) if len(toks) > 0 else "",
            token_id_other=str(toks[1]) if len(toks) > 1 else "",
            notes=m["why"][:160], added_by="triage_open",
            accounts=accounts)
        try:
            store.add_market(mk)
            armed += 1
        except RuleError as e:
            failed += 1
            store.mark_seen(m["cid"], m["q"], "rejected", str(e)[:200])
        if i % 40 == 0:
            print(f"    {i}/{len(kept)}  armed {armed}  {time.time()-t0:.0f}s",
                  flush=True)

    print(f"\n  armed {armed}, failed {failed}")
    print(f"  store: {json.dumps(store.stats())}")
    warn = 0
    for mk in store.armed_markets():
        if lint(mk):
            warn += 1
    print(f"  {warn} armed markets carry a lint warning")
    print(f"  stream rules: {len(store.stream_rules())}")
    store.close()


if __name__ == "__main__":
    main()
