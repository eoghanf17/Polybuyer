"""Score the gate against the labelled calibration set.

Run after any change to the question wording. Tuning phrasing by feel is how
the set ended up oscillating between too loose and too strict -- each fix for
a false positive bought a false negative -- so changes should be measured.

    python3 experiments/score_gate.py

Costs about $0.002 a run. Needs OPENAI_API_KEY.

"act" means fire OR corroborate: corroboration costs a short wait rather than
the trade, and latency is nearly free here, so routing a borderline signal
there is a pass rather than a miss.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.newsdesk.config import load
from polybuyer.newsdesk.gate import decide
from polybuyer.newsdesk.llm import ask


def main() -> int:
    s = load()
    if not s.can_gate:
        print("OPENAI_API_KEY not set", file=sys.stderr)
        return 2
    cases = json.load(open(os.path.join(os.path.dirname(__file__), "gate_cases.json")))

    ok = fp = fn = 0
    cost = 0.0
    for c in cases:
        r = ask(c["market"], c["text"], "acct", s.openai_key, s.gate_model)
        cost += r.cost_usd
        action, why = decide(r.result, c["direction"])
        acted = action in ("fire", "corroborate")
        good = (c["expect"] == "act") == acted
        ok += good
        if not good:
            fp += acted
            fn += not acted
        mark = "PASS" if good else ("FALSE POSITIVE" if acted else "FALSE NEGATIVE")
        print(f"  {mark:<15} {action:<12} {c['note']}")
        if not good:
            print(f"                  {why}")

    n = len(cases)
    print(f"\n{ok}/{n} correct | {fp} false positive, {fn} false negative "
          f"| ${cost:.5f}")
    return 0 if fp == 0 and fn <= 1 else 1


if __name__ == "__main__":
    sys.exit(main())
