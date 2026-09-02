"""Run the watchlist pipeline end to end, or from any stage.

Thin on purpose: each stage is its own script with its own output file, so
this exists to name the order, enforce the budget gate before anything
bills, and print what the register says must not be forgotten.

    python experiments/run_pipeline.py --budget 100
    python experiments/run_pipeline.py --from triage
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.newsdesk.costs import cost_model, markets_for_budget
from polybuyer.newsdesk.learnings import REGISTER, unenforced

STAGES = [
    ("universe", "experiments/open_universe.py", "gamma only, free"),
    ("triage", "experiments/triage_open.py", "model, ~$3"),
    ("arm", "experiments/build_watchlist.py", "model, ~$2"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=100.0,
                    help="monthly USD for X post delivery")
    ap.add_argument("--from", dest="start", default="universe",
                    choices=[s[0] for s in STAGES])
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    bad = unenforced()
    if bad:
        sys.exit(f"refusing to run: {len(bad)} unenforced learnings "
                 f"({[l.id for l in bad]}). Anchor them to a test first.")

    cap = markets_for_budget(a.budget)
    print(f"  {len(REGISTER)} learnings in the register, all enforced")
    print(f"  budget ${a.budget:,.0f}/month -> arm at most {cap} markets")
    print(f"  ({cost_model(cap).posts_per_day:,.0f} posts/day at the measured "
          f"density; see costs.py for why that is a floor)\n")
    if cap < 1:
        sys.exit("budget affords no markets.")

    started = False
    for name, script, note in STAGES:
        if name == a.start:
            started = True
        if not started:
            print(f"  skip  {name}")
            continue
        print(f"  run   {name:<10} {script}  ({note})", flush=True)
        if a.dry_run:
            continue
        r = subprocess.run([sys.executable, script])
        if r.returncode != 0:
            sys.exit(f"stage {name} failed")

    print(f"\n  Arm at most {cap} markets. Then, before going live:")
    print("    - verify every handle exists (needs X credit)")
    print("    - keep NEWSDESK_PAPER=1 until fires look right")
    print("  After the run, append what it taught to newsdesk/learnings.py")
    print("  with a test named in enforced_by, or the next run will not start.")


if __name__ == "__main__":
    main()
