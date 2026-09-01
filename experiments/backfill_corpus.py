"""Recover every post the earlier experiments read into the corpus.

No network calls: everything here already exists on disk. The point is to
stop it existing only as a per-experiment JSON blob with a different shape
each time.

What each source can and cannot contribute:

``who_broke_it.json``   blind test 1. Has handle, followers, timestamp and
                        the market's repricing moment. No post ids -- the
                        harness discarded them -- so these rows dedupe on a
                        content hash and will merge with a later re-fetch
                        only if the text is byte-identical.
``calibration.json``    the gate calibration sweep. Has lead time already
                        computed but no follower counts, so it cannot be
                        scored against a follower floor.
``gate_cases.json``     the only source with real human labels. No
                        timestamps -- these are hand-transcribed examples,
                        not fetched rows -- so they are written to a
                        separate labelled file rather than the main corpus,
                        where an absent timestamp would read as "not
                        actionable" and silently drop out of scoring.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.newsdesk import corpus as C

OUT = "experiments/corpus/posts.jsonl"
CASES = "experiments/corpus/labelled_cases.jsonl"


def from_who_broke_it() -> list[C.Post]:
    path = "experiments/who_broke_it.json"
    if not os.path.exists(path):
        return []
    out = []
    for m in json.load(open(path)):
        for p in m.get("posts", []):
            out.append(C.Post(
                handle=p.get("handle", ""), followers=p.get("followers"),
                created_at=p.get("at", ""), text=p.get("text", ""),
                is_retweet=p.get("text", "").startswith("RT @"),
                market=m.get("market", ""),
                market_repriced_at=m.get("repriced", ""),
                source="blind1/who_broke_it",
            ))
    return out


def from_calibration() -> list[C.Post]:
    path = "experiments/calibration.json"
    if not os.path.exists(path):
        return []
    out = []
    for r in json.load(open(path)):
        # The sweep stored lead time but not the repricing moment; recover
        # it so the row is self-contained like every other.
        repriced = ""
        ts = C._parse_ts(r.get("ts"))
        mins = r.get("mins_vs_repricing")
        if ts is not None and mins is not None:
            repriced = (ts + dt.timedelta(minutes=-float(mins))).isoformat()
        out.append(C.Post(
            handle=r.get("handle", ""), created_at=r.get("ts", ""),
            text=r.get("text", ""),
            is_retweet=r.get("text", "").startswith("RT @"),
            market=r.get("market", ""), market_repriced_at=repriced,
            source="gate_calibration",
            gate={"action": r["action"]} if r.get("action") else {},
        ))
    return out


def from_gate_cases() -> list[C.Post]:
    path = "experiments/gate_cases.json"
    if not os.path.exists(path):
        return []
    out = []
    for r in json.load(open(path)):
        mk = r.get("market", {})
        out.append(C.Post(
            handle=r.get("handle", ""), text=r.get("text", ""),
            market=mk.get("question", "") if isinstance(mk, dict) else str(mk),
            source="gate_cases",
            label=C.BREAKER if r.get("expect") == "act" else C.CHATTER,
            label_note=r.get("note", ""),
        ))
    return out


def main() -> None:
    a, b = from_who_broke_it(), from_calibration()
    rows = a + b
    n = C.save(rows, OUT)
    cases = from_gate_cases()
    m = C.save(cases, CASES)

    print(f"  blind1/who_broke_it : {len(a):>4} posts")
    print(f"  gate_calibration    : {len(b):>4} posts")
    print(f"  -> {OUT}: {n} rows after dedupe")
    print(f"  gate_cases (labelled): {len(cases):>3} -> {CASES}: {m} rows")

    loaded = C.load(OUT)
    lab = sum(1 for p in loaded if p.label != C.UNLABELLED)
    act = sum(1 for p in loaded if p.actionable)
    fol = sum(1 for p in loaded if p.followers is not None)
    print(f"\n  of {len(loaded)} corpus rows: {act} actionable (pre-repricing), "
          f"{fol} with follower counts, {lab} labelled")
    print(f"  review queue: {sum(1 for _ in C.needs_label(loaded))} rows need a label")


if __name__ == "__main__":
    main()
