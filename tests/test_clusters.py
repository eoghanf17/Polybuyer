"""Funding-graph cluster detection."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from polybuyer import clusters

USDC = "0x2791bca1f2de4661ed88a30c99a7a9449aa84174"
A, B, C, D = "0xaaa1", "0xbbb2", "0xccc3", "0xddd4"
LONE = "0xeee5"


def xfer(src: str, dst: str, amount: float = 1000.0, token: str = USDC) -> dict:
    return {
        "contractAddress": token,
        "from": src,
        "to": dst,
        "value": str(int(amount * 10 ** 6)),
        "tokenDecimal": "6",
    }


class TestDirectTransfers(unittest.TestCase):
    def test_mesh_collapses_to_one_cluster(self):
        """The subject cluster's shape: proxies funding each other."""
        t = {
            A: [xfer(A, B), xfer(A, C)],
            B: [xfer(B, D)],
            C: [], D: [], LONE: [],
        }
        rep = clusters.build(t, [A, B, C, D, LONE])
        self.assertEqual(set(rep.siblings(A)), {A, B, C, D})
        self.assertEqual(rep.siblings(LONE), [LONE])

    def test_transitive_merge(self):
        t = {A: [xfer(A, B)], B: [xfer(B, C)], C: []}
        rep = clusters.build(t, [A, B, C])
        self.assertEqual(len(rep.groups), 1)

    def test_cluster_ids_are_stable(self):
        t = {A: [xfer(A, B)], B: []}
        r1 = clusters.build(t, [A, B])
        r2 = clusters.build(t, [B, A])
        self.assertEqual(r1.cluster_of(A), r2.cluster_of(A))

    def test_non_usdc_transfers_are_ignored(self):
        t = {A: [xfer(A, B, token="0xdeadbeef")], B: []}
        rep = clusters.build(t, [A, B])
        self.assertEqual(len(rep.groups), 2)

    def test_transfers_to_unwatched_addresses_do_not_merge(self):
        t = {A: [xfer(A, "0xexchange")], B: [xfer(B, "0xexchange")]}
        rep = clusters.build(t, [A, B])
        self.assertEqual(len(rep.groups), 2,
                         "a shared exchange must not merge two traders")

    def test_evidence_is_recorded(self):
        t = {A: [xfer(A, B, 10.0)], B: []}
        rep = clusters.build(t, [A, B])
        self.assertTrue(rep.evidence)
        self.assertIn("direct USDC transfer", rep.evidence[0])


class TestSharedCounterparties(unittest.TestCase):
    def test_single_shared_peer_is_not_enough(self):
        t = {A: [xfer(A, "0xcex")], B: [xfer(B, "0xcex")]}
        rep = clusters.build(t, [A, B], use_shared_counterparties=True, min_shared=3)
        self.assertEqual(len(rep.groups), 2)

    def test_several_shared_peers_merge_when_enabled(self):
        peers = ["0xp1", "0xp2", "0xp3"]
        t = {A: [xfer(A, p) for p in peers], B: [xfer(B, p) for p in peers]}
        rep = clusters.build(t, [A, B], use_shared_counterparties=True, min_shared=3)
        self.assertEqual(len(rep.groups), 1)
        self.assertIn("circumstantial", rep.evidence[0])

    def test_disabled_by_default(self):
        peers = ["0xp1", "0xp2", "0xp3"]
        t = {A: [xfer(A, p) for p in peers], B: [xfer(B, p) for p in peers]}
        rep = clusters.build(t, [A, B])
        self.assertEqual(len(rep.groups), 2)


class TestFillExclusion(unittest.TestCase):
    def test_siblings_are_excluded_from_each_others_fills(self):
        """You cannot fill against the order you are copying -- nor against
        the same operator's other wallet firing the same idea."""
        from polybuyer.config import DEFAULT
        from polybuyer.model import normalise_many
        from polybuyer.tape import Tape
        from tests import synthetic as syn

        rows = [syn.raw_trade(100, 0.30, "0xtarget", +500)]
        rows += [syn.raw_trade(100 + i, 0.30, "0xsibling", +500) for i in range(1, 6)]
        rows += [syn.raw_trade(200 + i, 0.31, "0xother", +500) for i in range(5)]
        tape = Tape("0xm", normalise_many(rows))

        with_sib = tape.simulate_fill(100, 0.30, 1, 4000, 0.02, 600,
                                      frozenset({"0xtarget"}))
        without = tape.simulate_fill(100, 0.30, 1, 4000, 0.02, 600,
                                     frozenset({"0xtarget", "0xsibling"}))
        self.assertGreater(with_sib.shares, without.shares,
                           "excluding siblings must reduce simulated fill")


if __name__ == "__main__":
    unittest.main(verbosity=2)
