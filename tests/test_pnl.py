"""Mark-to-terminal PnL, capital accounting, and cluster bootstrap."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.config import DEFAULT
from polybuyer.model import Resolution, normalise_many
from polybuyer.pnl import cost_of, drop_best, market_pnl, roi
from polybuyer.stats import bootstrap_ratio, effective_n
from tests import synthetic as syn


def _res(cid: str, ref_wins: bool) -> Resolution:
    return Resolution(cid, True, {}, 1.0 if ref_wins else 0.0)


def _mk(rows):
    return normalise_many(rows)


class TestMarkToTerminal(unittest.TestCase):
    def test_simple_winner(self):
        tr = _mk([syn.raw_trade(10, 0.30, "0xw", +100)])
        r = market_pnl("0xw", "0xtest", tr, _res("0xtest", True))
        self.assertAlmostEqual(r.pnl, 70.0, places=6)
        self.assertAlmostEqual(r.capital, 30.0, places=6)
        self.assertAlmostEqual(r.roi, 70.0 / 30.0, places=6)

    def test_round_trip_equals_realised(self):
        """Buy 30c, sell 60c, resolves worthless: still +30."""
        tr = _mk([
            syn.raw_trade(10, 0.30, "0xw", +100),
            syn.raw_trade(20, 0.60, "0xw", -100),
        ])
        r = market_pnl("0xw", "0xtest", tr, _res("0xtest", False))
        self.assertAlmostEqual(r.pnl, 30.0, places=6)
        # Closing is not fresh capital.
        self.assertAlmostEqual(r.capital, 30.0, places=6)

    def test_round_trip_result_is_independent_of_resolution(self):
        """A fully closed position must pay the same either way."""
        rows = [syn.raw_trade(10, 0.30, "0xw", +100), syn.raw_trade(20, 0.60, "0xw", -100)]
        a = market_pnl("0xw", "0xtest", _mk(rows), _res("0xtest", True))
        b = market_pnl("0xw", "0xtest", _mk(rows), _res("0xtest", False))
        self.assertAlmostEqual(a.pnl, b.pnl, places=6)

    def test_short_side_pays_correctly(self):
        """Shorting the reference outcome = buying the other one."""
        tr = _mk([syn.raw_trade(10, 0.30, "0xw", -100)])
        r = market_pnl("0xw", "0xtest", tr, _res("0xtest", False))
        # Bought 100 of the other outcome at 70c, it paid 1.
        self.assertAlmostEqual(r.pnl, 30.0, places=6)
        self.assertAlmostEqual(r.capital, 70.0, places=6)

    def test_crossing_through_flat_counts_only_new_risk(self):
        tr = _mk([
            syn.raw_trade(10, 0.30, "0xw", +100),
            syn.raw_trade(20, 0.50, "0xw", -300),
        ])
        r = market_pnl("0xw", "0xtest", tr, _res("0xtest", False))
        # 30 to open the long; the short 200 costs 200 * (1-0.5) = 100.
        self.assertAlmostEqual(r.capital, 130.0, places=6)

    def test_cost_of_both_directions(self):
        long_t = _mk([syn.raw_trade(1, 0.25, "0xw", +40)])[0]
        short_t = _mk([syn.raw_trade(1, 0.25, "0xw", -40)])[0]
        self.assertAlmostEqual(cost_of(long_t), 10.0, places=6)
        self.assertAlmostEqual(cost_of(short_t), 30.0, places=6)

    def test_unresolved_market_yields_nothing(self):
        tr = _mk([syn.raw_trade(10, 0.30, "0xw", +100)])
        self.assertIsNone(market_pnl("0xw", "0xtest", tr, Resolution("0xtest", False, {}, None)))

    def test_identity_holds_on_a_full_synthetic_tape(self):
        """Summed over a whole tape, mark-to-terminal must equal the
        cash-flow result for every wallet, since all positions settle."""
        spec = syn.MarketSpec(actors=[("0xins", "insider", True)])
        rows, truth = syn.build(spec)
        trades = _mk(rows)
        T = truth["ref_terminal"]
        for w in {t.wallet for t in trades}:
            mine = [t for t in trades if t.wallet == w]
            direct = sum(t.ref_signed * (T - t.ref_price) for t in mine)
            r = market_pnl(w, spec.condition_id, trades, _res(spec.condition_id, T > 0.5))
            self.assertAlmostEqual(r.pnl, direct, places=4)


class TestBootstrap(unittest.TestCase):
    def test_consistent_winner_is_significant(self):
        num = [10.0] * 60
        den = [100.0] * 60
        ci = bootstrap_ratio(num, den, DEFAULT.stats)
        self.assertAlmostEqual(ci.point, 0.10, places=6)
        self.assertTrue(ci.significant)
        self.assertLess(ci.p_le_zero, 0.01)

    def test_coin_flip_is_not_significant(self):
        import random
        rng = random.Random(3)
        num = [rng.gauss(0, 100) for _ in range(60)]
        den = [100.0] * 60
        ci = bootstrap_ratio(num, den, DEFAULT.stats)
        self.assertFalse(ci.significant)

    def test_one_huge_winner_does_not_reach_significance(self):
        """The whole point of clustering: a single outsized market cannot
        carry a track record."""
        num = [0.0] * 59 + [5000.0]
        den = [100.0] * 60
        ci = bootstrap_ratio(num, den, DEFAULT.stats)
        self.assertGreater(ci.point, 0)
        self.assertFalse(ci.significant, "one market must not look significant")

    def test_empty_is_safe(self):
        ci = bootstrap_ratio([], [], DEFAULT.stats)
        self.assertEqual(ci.n, 0)
        self.assertEqual(ci.p_le_zero, 1.0)

    def test_effective_n_discounts_correlated_groups(self):
        self.assertAlmostEqual(effective_n([f"e{i}" for i in range(40)]), 40.0, places=6)
        # Forty markets all in one event are ~one observation.
        self.assertAlmostEqual(effective_n(["worldcup"] * 40), 1.0, places=6)
        mixed = ["worldcup"] * 20 + [f"e{i}" for i in range(20)]
        self.assertLess(effective_n(mixed), 21.0)
        self.assertGreater(effective_n(mixed), 1.0)


class TestConcentration(unittest.TestCase):
    def test_drop_best_removes_the_top_markets(self):
        from polybuyer.pnl import MarketPnL
        rows = [MarketPnL("w", f"m{i}", float(i), 100.0, 1, 0, 0.5, 1, 1.0) for i in range(10)]
        kept = drop_best(rows, 5)
        self.assertEqual(len(kept), 5)
        self.assertEqual(max(r.pnl for r in kept), 4.0)

    def test_edge_carried_by_a_few_markets_collapses(self):
        from polybuyer.pnl import MarketPnL
        rows = [MarketPnL("w", f"m{i}", -5.0, 100.0, 1, 0, 0.5, 1, 1.0) for i in range(40)]
        rows += [MarketPnL("w", f"b{i}", 900.0, 100.0, 1, 0, 0.5, 1, 1.0) for i in range(5)]
        self.assertGreater(roi(rows), 0)
        self.assertLess(roi(drop_best(rows, 5)), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
