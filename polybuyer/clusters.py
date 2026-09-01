"""Sibling-wallet detection via the on-chain funding graph.

One operator running several proxy wallets is not exotic -- the subject of
the prior research phase ran four in a closed mesh, and the largest of them
showed a *negative* headline PnL while the cluster made $4.7M.  Screening
per wallet both misses operators like that and double-counts them when it
does not.

Two consequences if clusters are not merged:

* the same edge appears several times in the ranking, and a portfolio built
  from the top N is far less diversified than it looks;
* the follow bot fires N orders into one idea, competing with itself for the
  same offers.

The strong signal is a direct USDC transfer between two proxy wallets: there
is no ordinary reason for one trader's proxy to fund another's.  Shared
external counterparties are weaker -- exchanges and bridges are shared by
thousands of unrelated users -- so they need corroboration.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from .netio import Fetcher
from .sources import token_transfers

#: USDC on Polygon: bridged (USDC.e) and native.
USDC = {
    "0x2791bca1f2de4661ed88a30c99a7a9449aa84174",
    "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359",
}

#: Polymarket protocol contracts.  Every proxy wallet transacts with these
#: constantly, so they dominate any counterparty ranking and must never be
#: mistaken for a sibling wallet.
INFRASTRUCTURE = {
    "0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e": "CTF Exchange",
    "0xc5d563a36ae78145c45a50134d48a1215220f80a": "NegRisk CTF Exchange",
    "0x4d97dcd97ec945f40cf65f87097ace5ea0476045": "Conditional Tokens",
    "0xd91e80cf2e7be2e162c6513ced06f1dd0da35296": "NegRiskAdapter",
}


class UnionFind:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


@dataclass
class ClusterReport:
    #: wallet -> cluster id (the lexicographically smallest member).
    mapping: dict[str, str] = field(default_factory=dict)
    #: cluster id -> members.
    groups: dict[str, list[str]] = field(default_factory=dict)
    #: Human-readable evidence per merged pair.
    evidence: list[str] = field(default_factory=list)

    def cluster_of(self, wallet: str) -> str:
        w = wallet.lower()
        return self.mapping.get(w, w)

    def siblings(self, wallet: str) -> list[str]:
        return self.groups.get(self.cluster_of(wallet), [wallet.lower()])


def _norm(a: str) -> str:
    return (a or "").strip().lower()


def direct_transfer_edges(
    transfers_by_wallet: dict[str, Sequence[dict]],
    watched: Iterable[str],
) -> list[tuple[str, str, str]]:
    """Edges where one watched wallet sent USDC straight to another."""
    watch = {_norm(w) for w in watched}
    edges: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()

    for owner, rows in transfers_by_wallet.items():
        for r in rows:
            if _norm(r.get("contractAddress")) not in USDC:
                continue
            src, dst = _norm(r.get("from")), _norm(r.get("to"))
            if src not in watch or dst not in watch or src == dst:
                continue
            key = tuple(sorted((src, dst)))
            if key in seen:
                continue
            seen.add(key)
            try:
                dec = int(r.get("tokenDecimal", 6) or 6)
                amt = int(r.get("value", 0)) / (10 ** dec)
            except (TypeError, ValueError):
                amt = 0.0
            edges.append((src, dst, f"direct USDC transfer ${amt:,.2f}"))
    return edges


def shared_counterparty_edges(
    transfers_by_wallet: dict[str, Sequence[dict]],
    watched: Iterable[str],
    min_shared: int = 2,
) -> list[tuple[str, str, str]]:
    """Edges from repeatedly sharing the same external counterparty.

    Weak on its own: exchange deposit addresses and bridge contracts are
    shared by unrelated users, so a single common counterparty proves
    nothing.  Requiring several distinct shared addresses makes coincidence
    much less likely, but this remains circumstantial and is reported as
    such rather than treated as proof.
    """
    watch = {_norm(w) for w in watched}
    peers: dict[str, set[str]] = defaultdict(set)

    for owner, rows in transfers_by_wallet.items():
        o = _norm(owner)
        for r in rows:
            if _norm(r.get("contractAddress")) not in USDC:
                continue
            for side in (_norm(r.get("from")), _norm(r.get("to"))):
                if side and side != o and side not in watch:
                    peers[o].add(side)

    edges: list[tuple[str, str, str]] = []
    owners = sorted(peers)
    for i, a in enumerate(owners):
        for b in owners[i + 1:]:
            shared = peers[a] & peers[b]
            if len(shared) >= min_shared:
                edges.append((a, b, f"{len(shared)} shared counterparties (circumstantial)"))
    return edges


def build(
    transfers_by_wallet: dict[str, Sequence[dict]],
    watched: Iterable[str],
    use_shared_counterparties: bool = False,
    min_shared: int = 3,
) -> ClusterReport:
    """Merge wallets into operator clusters."""
    watched = [_norm(w) for w in watched]
    uf = UnionFind()
    for w in watched:
        uf.find(w)

    rep = ClusterReport()
    edges = direct_transfer_edges(transfers_by_wallet, watched)
    if use_shared_counterparties:
        edges += shared_counterparty_edges(transfers_by_wallet, watched, min_shared)

    for a, b, why in edges:
        uf.union(a, b)
        rep.evidence.append(f"{a[:10]}… <-> {b[:10]}…: {why}")

    groups: dict[str, list[str]] = defaultdict(list)
    for w in watched:
        groups[uf.find(w)].append(w)

    # Name each cluster by its smallest member so ids are stable across runs.
    for root, members in groups.items():
        cid = min(members)
        rep.groups[cid] = sorted(members)
        for m in members:
            rep.mapping[m] = cid
    return rep


def find_siblings(
    fetch: Fetcher,
    known: Sequence[str],
    min_usd: float = 1_000.0,
    max_candidates: int = 25,
) -> list[tuple[str, float, int, int]]:
    """Look for wallets the known set funds that are not yet in it.

    :func:`build` only merges wallets already under consideration, which
    cannot tell you the set is *complete*.  This walks outward instead: take
    every USDC counterparty of the known wallets, drop protocol contracts,
    and ask which of the rest actually trade on Polymarket.  A cash-out
    address or a bridge shows zero markets traded; a sibling proxy does not.

    Returns ``(address, usd, n_transfers, markets_traded)`` for counterparties
    that trade, best candidates first.  An empty result is meaningful: it is
    the evidence that a cluster is complete rather than an assumption that
    it is.
    """
    from .sources import markets_traded

    ks = {_norm(w) for w in known}
    totals: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)

    for w in ks:
        for r in token_transfers(fetch, w):
            if _norm(r.get("contractAddress")) not in USDC:
                continue
            src, dst = _norm(r.get("from")), _norm(r.get("to"))
            other = dst if src == w else src
            if not other or other in ks or other in INFRASTRUCTURE:
                continue
            try:
                dec = int(r.get("tokenDecimal", 6) or 6)
                totals[other] += int(r.get("value", 0)) / (10 ** dec)
            except (TypeError, ValueError):
                pass
            counts[other] += 1

    ranked = sorted(totals, key=lambda a: -totals[a])[:max_candidates]
    out: list[tuple[str, float, int, int]] = []
    for a in ranked:
        if totals[a] < min_usd:
            continue
        n = markets_traded(fetch, a)
        if n > 0:
            out.append((a, totals[a], counts[a], n))
    out.sort(key=lambda r: -r[1])
    return out


def fetch_and_build(
    fetch: Fetcher,
    wallets: Sequence[str],
    workers: int = 8,
    use_shared_counterparties: bool = False,
) -> ClusterReport:
    """Pull transfers for each wallet and cluster them."""
    ws = [_norm(w) for w in wallets]
    transfers: dict[str, list[dict]] = {}
    for w in ws:
        transfers[w] = token_transfers(fetch, w)
    return build(transfers, ws, use_shared_counterparties)
