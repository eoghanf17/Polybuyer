"""Find new markets worth reviewing as news-trade candidates.

This is a funnel, not a decision. It removes what is obviously unsuitable
and hands everything else over with the context needed to judge, because the
judgement -- will this settle on one headline, and is there an account likely
to break it -- is not something a keyword rule can make.

What it does decide, because these are mechanical:

* **sports** -- resolves by play, no headline front-runs it;
* **scheduled settlement** -- a market that resolves off a TWAP at a stated
  minute, or at a fixed close, has no surprise moment to trade;
* **in-play** -- a live match reprices continuously with the game.
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from dataclasses import dataclass, field

from ..netio import Fetcher
from ..sources import GAMMA

#: Descriptions that settle mechanically at a stated time rather than on news.
SCHEDULED_PAT = re.compile(
    r"\b(twap|time-weighted|up or down|close (?:above|below)|"
    r"at (?:1[0-2]|[1-9]):[0-5]\d\s*(?:am|pm)|hourly|"
    r"between .{0,24}\d:\d\d\s*(?:am|pm))\b", re.I)

#: Markets whose resolving moment is on everyone's calendar. Not dropped --
#: the headline still breaks on X -- but flagged hard, because a known
#: instant is a crowded one. The out-of-sample study found macro had the
#: fastest repricing windows of any category (28s median, 64% inside 45s),
#: which is exactly where a bot without a firehose arrives last.
KNOWN_INSTANT_PAT = re.compile(
    r"\b(fomc|fed(eral reserve)? meeting|after the .{0,20}meeting|"
    r"scheduled to be held|election day|cpi report|jobs report|"
    r"earnings (call|report)|nonfarm)\b", re.I)

#: Principals who announce somewhere other than X. A market that turns on
#: one of these is unreachable from an X feed however good the signal is:
#: Trump posts to Truth Social first and the X repost, when it comes, is
#: already late. Dropped rather than flagged, since no account list fixes it.
OFF_PLATFORM_PAT = re.compile(
    r"\b(trump|truth social|white house|potus)\b", re.I)

SPORTS_PAT = re.compile(
    r"\b(super bowl|nba|nfl|mlb|nhl|premier league|la liga|serie a|"
    r"champions league|world cup|ufc|f1|grand prix|tennis|golf|"
    r"vs\.?\s|match|game \d|playoff|championship)\b", re.I)


@dataclass
class Candidate:
    condition_id: str
    question: str
    slug: str
    rules: str
    end_date: str
    volume: float
    liquidity: float
    token_ids: list[str] = field(default_factory=list)
    outcomes: list[str] = field(default_factory=list)
    #: Why the funnel let it through, or what it wants a human to weigh.
    flags: list[str] = field(default_factory=list)

    @property
    def days_left(self) -> float:
        try:
            end = dt.datetime.fromisoformat(self.end_date.replace("Z", "+00:00"))
            return (end - dt.datetime.now(dt.timezone.utc)).total_seconds() / 86400
        except (ValueError, AttributeError):
            return -1.0


def _f(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def fetch_open(fetch: Fetcher, pages: int = 6, per_page: int = 100,
               order: str = "startDate") -> list[dict]:
    """Open markets, ordered by ``order`` descending."""
    out: list[dict] = []
    for page in range(pages):
        url = (f"{GAMMA}/markets?closed=false&limit={per_page}"
               f"&offset={page * per_page}&order={order}&ascending=false")
        batch = fetch.get(url)
        if not batch or not isinstance(batch, list):
            break
        out.extend(batch)
        if len(batch) < per_page:
            break
    return out


def fetch_universe(fetch: Fetcher, pages: int = 6) -> list[dict]:
    """Both sweeps, deduplicated.

    Newest-first alone returns mostly auto-generated series -- in one sample,
    364 of 400 were in-play match markets and the survivors were zero-volume
    county-level election markets. Volume-ordered alone misses markets
    created since the last run, which is the whole point of a six-hourly
    sweep. Both are needed.
    """
    seen: set[str] = set()
    out: list[dict] = []
    for order in ("startDate", "volumeNum", "liquidityNum"):
        for m in fetch_open(fetch, pages=pages, order=order):
            cid = str(m.get("conditionId") or "")
            if cid and cid not in seen:
                seen.add(cid)
                out.append(m)
    return out


def screen(rows: list[dict], seen: set[str], min_days: float = 0.25,
           max_days: float = 120.0) -> tuple[list[Candidate], dict[str, int]]:
    """Cut the mechanically unsuitable; return the rest for review."""
    kept: list[Candidate] = []
    dropped: dict[str, int] = {}

    def drop(why: str) -> None:
        dropped[why] = dropped.get(why, 0) + 1

    for m in rows:
        cid = str(m.get("conditionId") or "")
        if not cid or cid in seen:
            drop("already seen")
            continue

        q = str(m.get("question") or "")
        desc = str(m.get("description") or "")
        blob = f"{q} {desc}"

        if m.get("gameStartTime"):
            drop("in-play match")
            continue
        if SPORTS_PAT.search(q):
            drop("sports")
            continue
        if SCHEDULED_PAT.search(blob):
            drop("settles on a schedule, not on news")
            continue
        if OFF_PLATFORM_PAT.search(q):
            drop("principal announces off-platform (Truth Social)")
            continue

        try:
            tokens = m.get("clobTokenIds")
            tokens = tokens if isinstance(tokens, list) else __import__("json").loads(tokens or "[]")
        except Exception:
            tokens = []
        try:
            outs = m.get("outcomes")
            outs = outs if isinstance(outs, list) else __import__("json").loads(outs or "[]")
        except Exception:
            outs = []

        c = Candidate(
            condition_id=cid, question=q, slug=str(m.get("slug") or ""),
            rules=desc, end_date=str(m.get("endDate") or ""),
            volume=_f(m.get("volumeNum")), liquidity=_f(m.get("liquidityNum")),
            token_ids=[str(t) for t in tokens], outcomes=[str(o) for o in outs],
        )

        d = c.days_left
        if d < min_days:
            drop("resolves too soon")
            continue
        if d > max_days:
            drop("resolves too far out")
            continue

        # Surfaced, not decided: these need a judgement call.
        if c.liquidity < 500:
            c.flags.append("thin book")
        if c.volume < 1000:
            c.flags.append("little volume yet")
        if KNOWN_INSTANT_PAT.search(blob):
            c.flags.append("SETTLES AT A KNOWN INSTANT -- everyone is watching "
                           "the same clock. Macro had the fastest repricing "
                           "windows in the study (28s median); this is where "
                           "a slow bot is last in the queue")
        elif re.search(r"\belection|\bvote\b|\bprimary\b", q, re.I):
            c.flags.append("election: resolution timing is known, but the "
                           "race call itself breaks on X")
        if d > 60:
            c.flags.append("long-dated: more chances to drift through "
                           "several headlines rather than settle on one")
        kept.append(c)

    kept.sort(key=lambda c: -c.volume)
    return kept, dropped


def review_packet(cands: list[Candidate], limit: int = 40) -> str:
    """Human-readable brief for the accept/reject conversation."""
    L = [f"{len(cands)} candidates for review (showing {min(limit, len(cands))})",
         "=" * 78]
    for i, c in enumerate(cands[:limit], 1):
        L.append(f"\n[{i}] {c.question}")
        L.append(f"    id={c.condition_id}")
        L.append(f"    ends {c.end_date[:10]} ({c.days_left:.0f}d)  "
                 f"vol ${c.volume:,.0f}  liq ${c.liquidity:,.0f}  "
                 f"outcomes={c.outcomes}")
        rules = " ".join(c.rules.split())
        L.append(f"    rules: {rules[:300]}{'...' if len(rules) > 300 else ''}")
        for f in c.flags:
            L.append(f"    ! {f}")
    return "\n".join(L)
