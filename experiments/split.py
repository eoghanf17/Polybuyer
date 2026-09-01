"""Build the universe and the chronological train/test split.

Kept separate from the analysis so the split is reproducible and identical
in both phases, and so the training phase can physically avoid touching test
markets rather than merely intending to.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.netio import Fetcher
from polybuyer.sources import top_markets

SPLIT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "split.json")


def _end(m: dict) -> str:
    return str(m.get("endDate") or "")


def build(pages: int = 30, days: int = 365) -> dict:
    f = Fetcher(cache_dir=".polycache")
    rows = top_markets(f, pages=pages, per_page=100, closed=True, since_days=days)

    keep = []
    for m in rows:
        cid = str(m.get("conditionId") or "")
        if not cid or not _end(m):
            continue
        if m.get("gameStartTime"):        # in-play; excluded by pre-registration
            continue
        keep.append({
            "conditionId": cid,
            "question": str(m.get("question") or ""),
            "slug": str(m.get("slug") or ""),
            "endDate": _end(m),
            "volume": float(m.get("volumeNum") or 0.0),
        })

    keep.sort(key=lambda m: m["endDate"])
    mid = len(keep) // 2
    out = {
        "built_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "n_total": len(keep),
        "boundary": keep[mid]["endDate"] if keep else None,
        "train": keep[:mid],
        "test": keep[mid:],
    }
    with open(SPLIT_FILE, "w") as fh:
        json.dump(out, fh, indent=1)
    return out


def load() -> dict:
    with open(SPLIT_FILE) as fh:
        return json.load(fh)


if __name__ == "__main__":
    s = build()
    print(f"universe: {s['n_total']} closed, non-in-play markets")
    print(f"boundary: {s['boundary']}")
    print(f"  TRAIN {len(s['train'])} markets  "
          f"{s['train'][0]['endDate'][:10]} .. {s['train'][-1]['endDate'][:10]}")
    print(f"  TEST  {len(s['test'])} markets  "
          f"{s['test'][0]['endDate'][:10]} .. {s['test'][-1]['endDate'][:10]}")
