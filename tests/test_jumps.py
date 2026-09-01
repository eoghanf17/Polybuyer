"""Jump detection and stance classification against known ground truth."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.config import DEFAULT, JumpConfig
from polybuyer.jumps import FAST, PRE, LATE, baseline_alignment, detect, stances
from polybuyer.model import normalise, normalise_many
from polybuyer.tape import Tape
from tests import synthetic as syn


class TestNormalisation(unittest.TestCase):
    def test_outcome_encodings_agree(self):
        """The same economic trade quoted on either token must normalise
        to identical reference terms."""
        a = normalise(syn.raw_trade(100, 0.30, "0xw", +500, quote_on=0))
        b = normalise(syn.raw_trade(100, 0.30, "0xw", +500, quote_on=1))
        self.assertIsNotNone(a)
        self.assertIsNotNone(b)
        self.assertAlmostEqual(a.ref_price, b.ref_price, places=3)
        self.assertAlmostEqual(a.ref_signed, b.ref_signed, places=3)
        self.assertAlmostEqual(a.ref_price, 0.30, places=3)
        self.assertGreater(a.ref_signed, 0)

    def test_buying_no_is_shorting_reference(self):
        t = normalise({
            "timestamp": 1, "proxyWallet": "0xw", "conditionId": "0xc",
            "asset": "a", "outcomeIndex": 1, "side": "BUY",
            "price": 0.30, "size": 100,
        })
        self.assertAlmostEqual(t.ref_price, 0.70, places=6)
        self.assertAlmostEqual(t.ref_signed, -100.0, places=6)

    def test_rejects_junk(self):
        self.assertIsNone(normalise({"side": "WAT", "price": 0.5, "size": 1, "timestamp": 1}))
        self.assertIsNone(normalise({"side": "BUY", "price": 0.0, "size": 1, "timestamp": 1}))
        self.assertIsNone(normalise({"side": "BUY", "price": 0.5, "size": 0, "timestamp": 1}))


class TestDetect(unittest.TestCase):
    def setUp(self):
        self.spec = syn.MarketSpec(actors=[
            ("0xins", "insider", True),
            ("0xnews", "newsdesk", True),
            ("0xlate", "follower", True),
        ])
        rows, self.truth = syn.build(self.spec)
        self.tape = Tape(self.spec.condition_id, normalise_many(rows))

    def test_finds_the_planted_jump(self):
        js = detect(self.tape, DEFAULT.jump)
        self.assertEqual(len(js), 1, f"expected exactly one jump, got {len(js)}")
        j = js[0]
        self.assertEqual(j.direction, self.truth["direction"])
        # Onset should land within a few minutes of the planted ramp start.
        self.assertLess(abs(j.onset_ts - self.truth["jump_ts"]), 900,
                        f"onset off by {j.onset_ts - self.truth['jump_ts']}s")
        self.assertGreater(j.magnitude, 0.30)

    def test_flat_market_has_no_jumps(self):
        spec = syn.MarketSpec(p_before=0.40, p_after=0.40, n_noise=1200, actors=[])
        rows, _ = syn.build(spec)
        tape = Tape(spec.condition_id, normalise_many(rows))
        self.assertEqual(detect(tape, DEFAULT.jump), [])

    def test_spike_that_reverts_is_rejected(self):
        """A round-trip spike is book-sweeping, not information."""
        spec = syn.MarketSpec(p_before=0.35, p_after=0.35, n_noise=800, actors=[])
        rows, _ = syn.build(spec)
        jt = spec.t0 + spec.jump_at_s
        # 25-point spike lasting 20 minutes, then straight back.
        for k in range(120):
            ts = jt + k * 10
            rows.append(syn.raw_trade(ts, 0.60, f"0xspike{k%5}", 300.0, spec.condition_id))
        rows.sort(key=lambda r: r["timestamp"])
        tape = Tape(spec.condition_id, normalise_many(rows))
        self.assertEqual(detect(tape, DEFAULT.jump), [],
                         "reverting spike must not be reported as a jump")

    def test_direction_down(self):
        spec = syn.MarketSpec(p_before=0.70, p_after=0.25, actors=[])
        rows, truth = syn.build(spec)
        tape = Tape(spec.condition_id, normalise_many(rows))
        js = detect(tape, DEFAULT.jump)
        self.assertEqual(len(js), 1)
        self.assertEqual(js[0].direction, -1)


class TestStances(unittest.TestCase):
    def setUp(self):
        self.spec = syn.MarketSpec(actors=[
            ("0xins", "insider", True),
            ("0xnews", "newsdesk", True),
            ("0xlate", "follower", True),
        ])
        rows, self.truth = syn.build(self.spec)
        self.tape = Tape(self.spec.condition_id, normalise_many(rows))
        self.jump = detect(self.tape, DEFAULT.jump)[0]
        self.st = stances(self.tape, self.jump, DEFAULT.window)

    def test_actors_land_in_their_own_buckets(self):
        self.assertEqual(self.st["0xins"].bucket, PRE)
        self.assertEqual(self.st["0xnews"].bucket, FAST)
        self.assertEqual(self.st["0xlate"].bucket, LATE)

    def test_all_planted_actors_are_aligned(self):
        for w in ("0xins", "0xnews"):
            self.assertTrue(self.st[w].aligned, f"{w} should be correctly positioned")

    def test_only_the_insider_has_anticipatory_pnl(self):
        self.assertGreater(self.st["0xins"].anticipatory_pnl, 0)
        self.assertAlmostEqual(self.st["0xnews"].anticipatory_pnl, 0.0, places=6)
        self.assertAlmostEqual(self.st["0xlate"].anticipatory_pnl, 0.0, places=6)

    def test_newsdesk_latency_is_small(self):
        """Reaction is measured in seconds, not minutes.

        The value may be slightly negative: onset resolution is bounded by
        print density, and a news desk is often *among* the first prints of
        the move.  That ambiguity is what the guard band is for, so the
        assertion is on magnitude.
        """
        lat = self.st["0xnews"].latency_s
        self.assertIsNotNone(lat)
        self.assertLess(abs(lat), DEFAULT.window.guard_s + DEFAULT.window.fast_s)

    def test_insider_lead_is_positive_and_bounded(self):
        lead = self.st["0xins"].lead_s
        self.assertIsNotNone(lead)
        self.assertGreater(lead, 0)
        self.assertLessEqual(lead, DEFAULT.window.pre_s)

    def test_makers_carry_no_net_opinion(self):
        """A two-sided quoter must not read as positioned."""
        for w, s in self.st.items():
            if w.startswith("0xmaker"):
                gross = sum(abs(t.ref_signed) for t in self.tape.trades if t.wallet == w)
                self.assertLess(abs(s.position_at_onset), 0.35 * gross,
                                "maker net exposure should be small vs gross")

    def test_baseline_is_near_a_coin_flip(self):
        """The null: absent information, pre-jump risk is ~50/50 correct."""
        base = baseline_alignment(list(self.st.values()))
        self.assertGreater(base, 0.25)
        self.assertLess(base, 0.90)


if __name__ == "__main__":
    unittest.main(verbosity=2)
