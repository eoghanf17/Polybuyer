"""News desk: store, gate and pre-fire guards."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer.newsdesk import gate, guards
from polybuyer.newsdesk.store import Market, Store

YES = '{"relevant":true,"factual":true,"rules_match":true,"novel":true,' \
      '"material":true,"standing":true,"direction":1}'


class TestStore(unittest.TestCase):
    def setUp(self):
        self.p = tempfile.mktemp(suffix=".db")
        self.s = Store(self.p)

    def tearDown(self):
        self.s.close()
        if os.path.exists(self.p):
            os.unlink(self.p)

    def _add(self, cid="0xa"):
        self.s.add_market(Market(
            condition_id=cid, question="Will X resign?", rules="YES if X resigns.",
            accounts=[{"handle": "@Reuters", "tier": "wire"},
                      {"handle": "@beatguy", "tier": "beat"}]))

    def test_round_trip(self):
        self._add()
        m = self.s.get_market("0xa")
        self.assertEqual(m["question"], "Will X resign?")
        self.assertEqual(m["on_off"], 1)
        self.assertAlmostEqual(m["aggression"], 0.05)
        self.assertAlmostEqual(m["max_size_usd"], 10.0)
        self.assertEqual(len(m["accounts"]), 2)

    def test_defaults_match_the_spec(self):
        self._add()
        m = self.s.get_market("0xa")
        self.assertAlmostEqual(m["guard_5m"], 0.20)
        self.assertAlmostEqual(m["guard_1h"], 0.20)
        self.assertAlmostEqual(m["guard_2h"], 0.20)
        self.assertAlmostEqual(m["guard_1d"], 0.30)

    def test_handles_are_normalised(self):
        self._add()
        self.assertIn("reuters", self.s.watched_handles())

    def test_one_handle_can_serve_several_markets(self):
        self._add("0xa")
        self._add("0xb")
        self.assertEqual(sorted(self.s.watched_handles()["reuters"]), ["0xa", "0xb"])

    def test_disarm_removes_it_from_the_watch_set(self):
        self._add()
        self.s.disarm("0xa", "fired")
        self.assertEqual(self.s.armed_markets(), [])
        self.assertEqual(self.s.watched_handles(), {})
        self.assertEqual(self.s.get_market("0xa")["off_reason"], "fired")

    def test_blocked_fires_are_recorded_too(self):
        """The declines matter as much as the fires -- they are the only
        record of whether the guards were set sensibly."""
        self._add()
        self.s.record_fire("0xa", "blocked", block_reason="5m moved 25%",
                           move_5m=0.25, direction=1)
        self.assertEqual(self.s.stats()["blocked"], 1)
        self.assertEqual(self.s.stats()["fires"], 0)

    def test_set_params_rejects_unknown_columns(self):
        self._add()
        self.s.set_params("0xa", aggression=0.08)
        self.assertAlmostEqual(self.s.get_market("0xa")["aggression"], 0.08)
        with self.assertRaises(ValueError):
            self.s.set_params("0xa", nonsense=1)


class TestGate(unittest.TestCase):
    def test_all_yes_fires(self):
        a, why = gate.decide(gate.parse(YES), 1)
        self.assertEqual(a, gate.FIRE)

    def test_wrong_direction_is_rejected_even_when_all_answers_are_yes(self):
        """The direction is compared in code precisely so a model that
        answers carelessly cannot talk us into the wrong side."""
        a, why = gate.decide(gate.parse(YES), -1)
        self.assertEqual(a, gate.DROP)
        self.assertIn("direction", why)

    def test_denial_flips_direction(self):
        js = YES.replace('"direction":1', '"direction":-1')
        self.assertEqual(gate.decide(gate.parse(js), 1)[0], gate.DROP)

    def test_hard_failure_drops(self):
        for k in gate.HARD:
            js = YES.replace(f'"{k}":true', f'"{k}":false')
            a, why = gate.decide(gate.parse(js), 1)
            self.assertEqual(a, gate.DROP, f"{k} should be a hard stop")
            self.assertIn(k, why)

    def test_soft_failure_seeks_corroboration_rather_than_dropping(self):
        for k in gate.SOFT:
            js = YES.replace(f'"{k}":true', f'"{k}":false')
            a, _ = gate.decide(gate.parse(js), 1)
            self.assertEqual(a, gate.CORROBORATE, f"{k} should be soft")

    def test_unparseable_reply_never_permits_a_trade(self):
        for junk in ("", "yes fire it", "{broken", "null"):
            a, _ = gate.decide(gate.parse(junk), 1)
            self.assertEqual(a, gate.DROP)

    def test_missing_fields_default_to_no(self):
        a, _ = gate.decide(gate.parse('{"relevant":true,"direction":1}'), 1)
        self.assertEqual(a, gate.DROP)

    def test_prompt_carries_market_rules(self):
        p = gate.build_prompt({"question": "Q?", "rules": "R."}, "text", "h")
        self.assertIn("Q?", p)
        self.assertIn("R.", p)
        for q in gate.QUESTIONS:
            self.assertIn(q.key, p)


class TestGuards(unittest.TestCase):
    TH = {"5m": 0.20, "1h": 0.20, "2h": 0.20, "1d": 0.30}

    def test_quiet_market_passes(self):
        r = guards.evaluate(0.55, {"5m": 0.54, "1h": 0.53, "2h": 0.52, "1d": 0.50},
                            1, self.TH)
        self.assertTrue(r.passed)

    def test_move_our_way_blocks(self):
        r = guards.evaluate(0.55, {"5m": 0.30, "1h": 0.53, "2h": 0.52, "1d": 0.50},
                            1, self.TH)
        self.assertFalse(r.passed)
        self.assertEqual(r.breached, ["5m"])

    def test_move_against_us_does_not_block(self):
        """Only moves in our own direction mean we are late."""
        r = guards.evaluate(0.55, {"5m": 0.90, "1h": 0.90, "2h": 0.90, "1d": 0.95},
                            1, self.TH)
        self.assertTrue(r.passed)

    def test_short_direction_is_mirrored(self):
        r = guards.evaluate(0.30, {"5m": 0.55, "1h": 0.55, "2h": 0.55, "1d": 0.55},
                            -1, self.TH)
        self.assertFalse(r.passed, "price fell 25c, which is our way when short")

    def test_missing_history_does_not_block(self):
        r = guards.evaluate(0.55, {"5m": None, "1h": None, "2h": None, "1d": None},
                            1, self.TH)
        self.assertTrue(r.passed)

    def test_day_threshold_is_looser(self):
        h = {"5m": 0.54, "1h": 0.53, "2h": 0.52, "1d": 0.30}
        self.assertTrue(guards.evaluate(0.55, h, 1, self.TH).passed)
        h["1d"] = 0.20
        self.assertFalse(guards.evaluate(0.55, h, 1, self.TH).passed)

    def test_limit_price_sides(self):
        self.assertAlmostEqual(guards.limit_price(0.55, 1, 0.05), 0.60, places=6)
        self.assertAlmostEqual(guards.limit_price(0.55, -1, 0.05), 0.50, places=6)

    def test_limit_price_is_clamped(self):
        self.assertLessEqual(guards.limit_price(0.99, 1, 0.05), 0.999)

    def test_history_from_series(self):
        import time
        now = time.time()
        s = [{"t": now - 86400, "p": 0.2}, {"t": now - 7200, "p": 0.4},
             {"t": now - 3600, "p": 0.45}, {"t": now - 300, "p": 0.5}]
        h = guards.history_from_series(s, now)
        self.assertAlmostEqual(h["1d"], 0.2)
        self.assertAlmostEqual(h["5m"], 0.5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
