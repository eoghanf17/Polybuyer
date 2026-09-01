"""End-to-end: does the pipeline find planted skill, and only planted skill?

The second half of that question is the one that matters.  A screen that
promotes the insider is easy; a screen that promotes the insider *and
nothing else* out of a hundred-odd wallets is the actual product, because in
live data the overwhelming majority of candidates will be noise and the cost
of a false positive is real money copied into a random punter.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.config import DEFAULT, StatsConfig
from polybuyer.pipeline import analyse
from polybuyer.scores import AVOID, FOLLOW, INSIDER, NEWSDESK, classify
from polybuyer.stats import Interval, bootstrap_ratio, fdr_qvalues
from tests import synthetic as syn

CFG = DEFAULT.with_(stats=StatsConfig(n_boot=1200))
INS, NEWS, FOL = "0xinsider", "0xnewsdesk", "0xfollower"


def _run(**kw):
    rows, payloads, _ = syn.universe(**kw)
    return analyse(rows, payloads, CFG)


class TestSignalUniverse(unittest.TestCase):
    """A universe containing genuinely skilled actors."""

    @classmethod
    def setUpClass(cls):
        cls.a = _run(n_markets=40)

    def test_every_market_yields_its_jump(self):
        self.assertEqual(self.a.n_jumps, 40)

    def test_insider_is_classified_as_such(self):
        v, f = self.a.by_wallet(INS)
        self.assertEqual(v.archetype, INSIDER)
        self.assertGreater(f.anticipation_excess.point, 0.05)
        self.assertTrue(f.anticipation_excess.significant)

    def test_insider_earns_before_the_move_not_after(self):
        _, f = self.a.by_wallet(INS)
        self.assertGreater(f.pre_pnl_share, 0.8)
        self.assertEqual(f.n_fast, 0)

    def test_newsdesk_is_classified_as_such(self):
        v, f = self.a.by_wallet(NEWS)
        self.assertEqual(v.archetype, NEWSDESK)
        self.assertTrue(f.fast_excess.significant)
        self.assertEqual(f.n_pre, 0, "news desk must not read as anticipatory")

    def test_newsdesk_reacts_within_seconds(self):
        _, f = self.a.by_wallet(NEWS)
        self.assertLess(abs(f.median_latency_s), CFG.window.fast_s)

    def test_follower_earns_no_archetype_score(self):
        v, _ = self.a.by_wallet(FOL)
        self.assertEqual(v.score, 0.0)
        self.assertEqual(v.decision, AVOID)

    def test_only_the_planted_actors_are_recommended(self):
        rec = {v.wallet for v, _ in self.a.ranked if v.decision == FOLLOW}
        self.assertEqual(rec, {INS, NEWS}, f"unexpected recommendations: {rec - {INS, NEWS}}")

    def test_market_makers_are_screened_out(self):
        for w in ("0xmaker000", "0xmaker001"):
            v = classify(self.a.features[w], CFG)
            self.assertIsNotNone(v.excluded)
            self.assertIn("market maker", v.excluded)

    def test_makers_never_reach_the_ranking(self):
        ranked = {v.wallet for v, _ in self.a.ranked}
        self.assertNotIn("0xmaker000", ranked)


class TestNullUniverse(unittest.TestCase):
    """No planted skill anywhere.  Nothing may be recommended."""

    @classmethod
    def setUpClass(cls):
        cls.a = _run(n_markets=40, insider_hit=0.5, news_hit=0.5,
                     follower_hit=0.5, seed=99)

    def test_no_follow_recommendations_from_pure_noise(self):
        rec = [v.wallet for v, _ in self.a.ranked if v.decision == FOLLOW]
        self.assertEqual(rec, [], f"false positives on a null universe: {rec}")

    def test_coin_flip_insider_is_not_significant(self):
        v, f = self.a.by_wallet(INS)
        if f.anticipation_excess is not None and not f.anticipation_excess.underpowered:
            self.assertFalse(f.anticipation_excess.significant)

    def test_fdr_holds_the_cohort_down(self):
        qs = [v.q_value for v, _ in self.a.ranked]
        self.assertTrue(all(q > CFG.stats.fdr_q for q in qs),
                        "no candidate should clear the FDR gate on noise")


class TestFollowability(unittest.TestCase):
    """Informed does not imply copyable -- and the two archetypes are
    blocked by opposite constraints.

    Anticipatory traders act in the quiet tape before the news: there is
    plenty of time to copy them and almost nothing to copy into.  Reaction
    traders act inside the news burst: size is there, but the price clears a
    limit in seconds.  Any follow infrastructure has to pick which of those
    problems it is solving.
    """

    @classmethod
    def setUpClass(cls):
        cls.a = _run(n_markets=40, jump_dur_s=300, seed=5)

    def test_anticipatory_entry_leaves_a_long_window(self):
        _, f = self.a.by_wallet(INS)
        self.assertGreater(f.median_follow_window_s, 600.0)

    def test_reaction_entry_leaves_almost_none(self):
        _, f = self.a.by_wallet(NEWS)
        self.assertLess(f.median_follow_window_s, 120.0)

    def test_the_constraints_are_opposite(self):
        _, ins = self.a.by_wallet(INS)
        _, news = self.a.by_wallet(NEWS)
        self.assertGreater(ins.median_follow_window_s, news.median_follow_window_s * 10,
                           "anticipatory entries must leave far more time")
        self.assertGreater(news.mean_fill_frac, ins.mean_fill_frac * 2,
                           "the news burst must supply far more liquidity")

    def test_binding_constraint_is_named_in_the_verdict(self):
        vi, _ = self.a.by_wallet(INS)
        vn, _ = self.a.by_wallet(NEWS)
        self.assertTrue(any("LIQUIDITY" in r for r in vi.reasons),
                        f"insider reasons: {vi.reasons}")
        self.assertTrue(any("SPEED" in r for r in vn.reasons),
                        f"newsdesk reasons: {vn.reasons}")

    def test_fills_come_only_from_the_executed_tape(self):
        """Never claim more fill than actually printed inside the cap."""
        _, f = self.a.by_wallet(NEWS)
        for s in f.signals:
            self.assertLessEqual(s.got_shares, s.want_shares + 1e-6)


class TestStatisticalGuards(unittest.TestCase):
    def test_single_cluster_bootstrap_is_never_significant(self):
        """One lucky market must not report certainty."""
        ci = bootstrap_ratio([500.0], [100.0], CFG.stats)
        self.assertTrue(ci.underpowered)
        self.assertFalse(ci.significant)

    def test_underpowered_flag_survives_a_strong_point_estimate(self):
        ci = bootstrap_ratio([50.0] * 3, [100.0] * 3, CFG.stats)
        self.assertGreater(ci.point, 0.4)
        self.assertFalse(ci.significant)

    def test_fdr_is_monotone_and_bounded(self):
        ps = [0.001, 0.01, 0.04, 0.2, 0.5, 0.9]
        qs = fdr_qvalues(ps)
        self.assertEqual(len(qs), len(ps))
        self.assertTrue(all(0.0 <= q <= 1.0 for q in qs))
        self.assertTrue(all(a <= b + 1e-12 for a, b in zip(qs, qs[1:])),
                        "q-values must be monotone in p")
        self.assertTrue(all(q >= p - 1e-12 for p, q in zip(ps, qs)))

    def test_fdr_on_uniform_noise_rejects_almost_everything(self):
        import random
        rng = random.Random(1)
        ps = [rng.random() for _ in range(300)]
        qs = fdr_qvalues(ps)
        self.assertLessEqual(sum(1 for q in qs if q < 0.10), 3)

    def test_empty_fdr(self):
        self.assertEqual(fdr_qvalues([]), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
