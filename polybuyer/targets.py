"""Known operator clusters, pinned.

These addresses cost real effort to recover once already. The FootballFan98
cluster was identified in an earlier research phase, recorded only in a
session handoff that was never committed, and when it was needed again none
of the automated paths could rebuild it:

- ``clusters.fetch_and_build`` only merges wallets already in the seed set,
  so a single seed can never grow one.
- ``clusters.find_siblings`` walks outward, but Blockscout serves only the
  most recent 10,000 transfers -- two months for a wallet this active -- and
  the cluster's founding USDC transfers are older than that.
- The funding counterparties visible in that window are shared deposit
  hubs touching thousands of addresses, which produce confident nonsense.

So the cluster is pinned here rather than rediscovered. Verified on
2026-09-02: all six pairs among the four wallets show direct on-chain
transfers, every member has degree 3, and five of the six edges carry USDC.

The PnL column is why the cluster matters more than any member of it.
Simulating FootballFan98 alone returns a loss, because FootballFan98 *is*
the loss-making leg -- the cluster's profit sits almost entirely in the
unnamed wallet. Copy strategies must be built on the cluster's combined
position per market, and all four wallets excluded from the liquidity a
follower consumes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Member:
    handle: str
    address: str
    #: Lifetime figures as displayed by Polymarket, 2026-09-02.
    volume_usd: float
    rank: int
    pnl_usd: float


FOOTBALLFAN_CLUSTER: tuple[Member, ...] = (
    Member("FootballFan98", "0xc31d0a0d63d760d72a1236d16beaa6a71c854ebe",
           45_400_000, 519, -1_070_000),
    Member("(unnamed)", "0x006cc834cc092684f1b56626e23bedb3835c16ea",
           64_900_000, 324, +4_720_000),
    Member("Airpods123", "0xb90494d9a5d8f71f1930b2aa4b599f95c344c255",
           40_000_000, 583, +1_020_000),
    Member("RBax", "0x4366ab8b8b27e4139d94a532e3cec94a83d1c73e",
           2_800_000, 7_882, +91_000),
)

#: Addresses only, lowercased -- the form every follow/exclusion path wants.
FOOTBALLFAN_WALLETS: tuple[str, ...] = tuple(
    m.address.lower() for m in FOOTBALLFAN_CLUSTER)


def cluster_pnl() -> float:
    """Combined PnL. Positive, despite one member being deeply negative."""
    return sum(m.pnl_usd for m in FOOTBALLFAN_CLUSTER)
