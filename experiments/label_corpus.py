"""Apply the human labels in corpus/labels.json to the corpus.

Labels live in a JSON file rather than in this script so that adding one is
a reviewable diff, and so the reasoning travels with the label instead of
being lost in a commit message.

Market-level labels are for windows where a human has read every post and
established that the breaker is not among them. That is a market-level
fact -- the market repriced on something that was not in this rule's
output -- and it licenses labelling every post in the window as chatter.
It is not a default: a market nobody has read stays unlabelled.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.newsdesk import corpus as C

LABELS = "experiments/corpus/labels.json"


def main() -> None:
    spec = json.load(open(LABELS))
    posts = C.load()
    n_m = n_p = 0

    for rule in spec.get("market_level", []):
        frag, lab = rule["market_contains"].lower(), rule["label"]
        for p in posts:
            if frag in p.market.lower() and p.label == C.UNLABELLED:
                p.label, p.label_note = lab, rule.get("note", "")
                n_m += 1

    for rule in spec.get("posts", []):
        frag = rule["market_contains"].lower()
        handle = rule["handle"].lower()
        for p in posts:
            if frag in p.market.lower() and p.handle.lower() == handle:
                p.label, p.label_note = rule["label"], rule.get("note", "")
                n_p += 1

    C.save(posts)
    counts: dict[str, int] = {}
    for p in posts:
        counts[p.label] = counts.get(p.label, 0) + 1
    print(f"  market-level: {n_m} rows   per-post: {n_p} rows")
    print(f"  corpus labels: {counts}")
    print(f"  still unlabelled but actionable: "
          f"{sum(1 for _ in C.needs_label(posts))}")


if __name__ == "__main__":
    main()
