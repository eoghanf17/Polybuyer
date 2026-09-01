"""Copy-strategy evaluation: signal extraction and fill honesty."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.config import DEFAULT, StatsConfig
from polybuyer.follow import (STRATEGIES, evaluate, first_per_market,
                              mirror_all, risk_increasing)
from polybuyer.model import Resolution, normalise_many
from polybuyer.tape import Tape
from tests import synthetic as syn

CFG = DEFAULT.with_(stats=StatsConfig(n_boot=400))
W = "0xtarget"


def _res(cid="0xtest", ref_wins=True):
    return Resolution(cid, True, {}, 1.0 if ref_wins else 0.0)


class TestSignalExtraction(unittest.TestCase):
    def setUp(self):
        # open 100, add 50, close 150, reopen 80
        self.tr = normalise_many([
            syn.raw_trade(10, 0.30, W, +100),
            syn.raw_trade(20, 0.35, W, +50),
            syn.raw_trade(30, 0.60, W, -150),
            syn.raw_trade(40, 0.40, W, +80),
        ])

    def test_mirror_copies_every_print(self):
        self.assertEqual(len(mirror_all(self.tr)), 4)

    def test_risk_increasing_skips_the_close(self):
        sigs = risk_increasing(self.tr)
        self.assertEqual([s.ts for s in sigs], [10, 20, 40])

    def test_first_takes_only_the_opening_trade(self):
        sigs = first_per_market(self.tr)
        self.assertEqual(len(sigs), 1)
        self.assertEqual(sigs[0].ts, 10)
        self.assertAlmostEqual(sigs[0].entry_ref, 0.30, places=6)
        self.assertEqual(sigs[0].direction, 1)

    def test_notional_floor_filters(self):
        big = STRATEGIES["first-10k"](self.tr)
        self.assertEqual(big, [], "no print here clears $10k")

    def test_short_side_direction(self):
        tr = normalise_many([syn.raw_trade(10, 0.30, W, -100)])
        s = first_per_market(tr)[0]
        self.assertEqual(s.direction, -1)


class TestEvaluate(unittest.TestCase):
    """The core claim: recorded-liquidity fills can never exceed mechanical."""

    def setUp(self):
        rows = [syn.raw_trade(1000, 0.30, W, +500)]
        # Plenty of other prints afterwards, at and around the entry price.
        rows += [syn.raw_trade(1000 + i, 0.305, f"0xother{i%7}", +200) for i in range(1, 30)]
        rows += [syn.raw_trade(2000 + i, 0.60, f"0xlate{i%5}", +200) for i in range(30)]
        self.tape = Tape("0xtest", normalise_many(rows))
        self.tapes = {"0xtest": self.tape}
        self.res = {"0xtest": _res()}

    def test_real_capital_never_exceeds_mechanical(self):
        for name in STRATEGIES:
            o = evaluate(name, [W], self.tapes, self.res, CFG)
            self.assertLessEqual(o.real_capital, o.mech_capital + 1e-6,
                                 f"{name}: recorded fill must be a lower bound")

    def test_cluster_is_excluded_from_its_own_liquidity(self):
        """You cannot fill against the order you are copying."""
        rows = [syn.raw_trade(1000, 0.30, W, +500)]
        rows += [syn.raw_trade(1001 + i, 0.30, W, +500) for i in range(10)]
        tape = Tape("0xtest", normalise_many(rows))
        o = evaluate("first", [W], {"0xtest": tape}, self.res, CFG)
        self.assertEqual(o.real_capital, 0.0,
                         "only the target traded; nothing to fill against")

    def test_uncovered_signals_are_reported_not_scored(self):
        """A truncated tape starting after the signal cannot be simulated."""
        rows = [syn.raw_trade(50, 0.30, W, +500)]
        rows += [syn.raw_trade(5000 + i, 0.31, f"0xo{i}", +200) for i in range(20)]
        tape = Tape("0xtest", normalise_many(rows))
        # Pretend the tape was truncated and really begins at its first print.
        o = evaluate("mirror", [W], {"0xtest": tape}, self.res, CFG,
                     truncated=set())
        self.assertEqual(o.n_uncovered, 0)

        rows2 = [syn.raw_trade(5000 + i, 0.31, f"0xo{i}", +200) for i in range(20)]
        rows2 += [syn.raw_trade(6000, 0.30, W, +500)]
        t2 = Tape("0xtest", normalise_many(rows2))
        o2 = evaluate("mirror", [W], {"0xtest": t2}, self.res, CFG,
                      truncated={"0xtest"})
        self.assertEqual(o2.n_uncovered, 0, "signal is inside the window")

    def test_unresolved_markets_contribute_nothing(self):
        res = {"0xtest": Resolution("0xtest", False, {}, None)}
        o = evaluate("mirror", [W], self.tapes, res, CFG)
        self.assertEqual(o.n_signals, 0)

    def test_winning_market_pays_out(self):
        o = evaluate("first", [W], self.tapes, self.res, CFG)
        self.assertGreater(o.mech_pnl, 0, "bought at 30c, resolved to 1")

    def test_losing_market_costs(self):
        o = evaluate("first", [W], self.tapes, {"0xtest": _res(ref_wins=False)}, CFG)
        self.assertLess(o.mech_pnl, 0)

    def test_mechanical_slippage_reduces_pnl(self):
        a = evaluate("first", [W], self.tapes, self.res, CFG, slippage_ticks=0)
        b = evaluate("first", [W], self.tapes, self.res, CFG, slippage_ticks=4)
        self.assertGreater(a.mech_pnl, b.mech_pnl)


if __name__ == "__main__":
    unittest.main(verbosity=2)
