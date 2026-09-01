"""Run the gate over labelled corpus rows and store the full answers.

Storing every answer rather than just fire/drop is the point. A change to
one gate question can then be evaluated by re-reading the five stored
answers it did not touch, and only the rows whose verdict actually turns on
the changed question need a fresh call. Without this, every gate iteration
re-pays for the whole set.

Only labelled rows are scored -- an unlabelled row cannot contribute to a
confusion matrix, so scoring it now would be paying for a number nobody can
use yet.
"""

from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.newsdesk import corpus as C
from polybuyer.newsdesk.config import load as load_settings
from polybuyer.newsdesk.gate import decide
from polybuyer.newsdesk.llm import ask


def main() -> None:
    s = load_settings()
    if not s.openai_key:
        sys.exit("OPENAI_API_KEY not set")
    posts = C.load()

    todo = [p for p in posts
            if p.label != C.UNLABELLED and not p.gate.get("answers")]
    print(f"  {len(todo)} labelled rows need scoring "
          f"(~${len(todo) * 0.0018:.2f})")

    for i, p in enumerate(todo, 1):
        r = ask({"question": p.market, "rules": "Resolves YES per the market title."},
                p.text, p.handle or "unknown", s.openai_key, s.gate_model)
        action, reason = decide(r.result, 1)
        p.gate = {
            "model": s.gate_model,
            "answers": r.result.answers,
            "direction": r.result.implied_direction,
            "action": action,
            "reason": reason,
            "error": r.result.error,
        }
        if i % 25 == 0:
            print(f"    {i}/{len(todo)}", flush=True)
            C.save(posts)
        time.sleep(0.05)

    C.save(posts)

    print("\n  gate vs. human labels, by follower floor")
    print(f"  {'floor':>8} {'scored':>7} {'TP':>4} {'FP':>4} {'TN':>4} {'FN':>4}"
          f" {'precision':>10} {'recall':>8}")
    for floor in (0, 10_000, 50_000, 250_000):
        m = C.score(posts, min_followers=floor)
        pr = f"{m['precision']:.0%}" if m["precision"] is not None else "n/a"
        rc = f"{m['recall']:.0%}" if m["recall"] is not None else "n/a"
        print(f"  {floor:>8,} {m['scored']:>7} {m['tp']:>4} {m['fp']:>4}"
              f" {m['tn']:>4} {m['fn']:>4} {pr:>10} {rc:>8}")

    print("\n  disagreements (gate vs label):")
    for p in posts:
        if p.label == C.UNLABELLED or not p.gate.get("answers") or not p.actionable:
            continue
        fired = p.gate["action"] in ("fire", "corroborate")
        if fired != (p.label == C.BREAKER):
            kind = "FALSE ALARM" if fired else "MISSED"
            print(f"    {kind:<12} @{p.handle:<18} {(p.followers or 0):>9,}f "
                  f"{p.text[:70]!r}")


if __name__ == "__main__":
    main()
