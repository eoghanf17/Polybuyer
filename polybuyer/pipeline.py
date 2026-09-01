"""End-to-end analysis, independent of where the data came from.

Deliberately split from the network layer: this function takes raw trade
records and CLOB market payloads as plain dicts, so the same code path runs
against a live fetch, a cached corpus on disk, or a synthetic fixture.  That
is what makes the detector testable at all -- the behaviour it looks for is
rare enough in real data that you would never be sure a change had broken it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .clusters import ClusterReport, fetch_and_build
from .config import Config
from .features import WalletFeatures, extract_all
from .harvest import shortlist, sweep
from .jumps import Jump, detect
from .model import Resolution, dedupe, normalise_many, resolution_from_clob
from .netio import Fetcher
from .scores import Verdict, rank
from .sources import market_resolutions, market_tape
from .tape import Tape, build_tapes


@dataclass
class Analysis:
    tapes: dict[str, Tape]
    jumps: dict[str, list[Jump]]
    resolutions: dict[str, Resolution]
    features: dict[str, WalletFeatures]
    ranked: list[tuple[Verdict, WalletFeatures]]
    #: Markets whose tape hit the server cap and so cannot support fill
    #: simulation for older trades.
    truncated: set[str] = field(default_factory=set)
    clusters: ClusterReport | None = None

    @property
    def n_jumps(self) -> int:
        return sum(len(v) for v in self.jumps.values())

    def by_wallet(self, wallet: str) -> tuple[Verdict, WalletFeatures] | None:
        for v, f in self.ranked:
            if v.wallet == wallet.lower():
                return v, f
        return None


def analyse(
    raw_trades: list[dict],
    clob_markets: dict[str, dict],
    cfg: Config,
    clusters: dict[str, str] | None = None,
) -> Analysis:
    """Run the whole discovery analysis over a corpus of trades.

    ``clob_markets`` maps conditionId -> the CLOB ``/markets/{id}`` payload,
    which is the authoritative source of resolution.  Markets missing from
    it are still used for jump detection and timing (behaviour does not need
    a resolution) but contribute no PnL.
    """
    trades = dedupe(normalise_many(raw_trades))
    tapes = build_tapes(trades)

    resolutions = {
        cid: resolution_from_clob(cid, payload)
        for cid, payload in clob_markets.items()
    }
    jumps = {
        cid: detect(tape, cfg.jump,
                    terminal=(resolutions[cid].ref_terminal if cid in resolutions else None))
        for cid, tape in tapes.items()
    }
    feats = extract_all(tapes, jumps, resolutions, cfg, clusters)
    ranked = rank(feats, cfg)

    return Analysis(
        tapes=tapes,
        jumps=jumps,
        resolutions=resolutions,
        features=feats,
        ranked=ranked,
    )


def discover(
    fetch: Fetcher,
    cfg: Config,
    max_markets: int = 150,
    cluster_wallets: bool = True,
    progress=lambda msg: None,
) -> Analysis:
    """Live end-to-end discovery against the Polymarket APIs.

    Market-centric rather than wallet-centric, which matters for cost: one
    fetch of a market's tape yields every participant at once, so screening
    N wallets that share markets costs far less than N wallet histories --
    and the fill simulation needs the all-participants tape anyway.
    """
    progress("sweeping recent large trades for candidates...")
    cands = sweep(fetch, cfg)
    short = shortlist(cands, cfg)
    progress(f"  {len(cands)} wallets seen, {len(short)} shortlisted")

    # Rank markets by how much shortlisted activity they carry.
    weight: dict[str, int] = {}
    keep = {c.wallet for c in short}
    for c in short:
        for m in c.markets:
            weight[m] = weight.get(m, 0) + 1
    markets = sorted(weight, key=lambda m: -weight[m])[:max_markets]
    progress(f"  fetching tapes for {len(markets)} markets...")

    raw: list[dict] = []
    truncated: set[str] = set()
    for i, cid in enumerate(markets, 1):
        t = market_tape(fetch, cid)
        raw.extend(t.trades)
        if t.truncated:
            truncated.add(cid)
        if i % 25 == 0:
            progress(f"    {i}/{len(markets)} markets, {len(raw)} prints")

    progress(f"  {len(raw)} prints; {len(truncated)} tapes truncated at the cap")
    progress("resolving markets...")
    payloads = market_resolutions(fetch, markets, workers=cfg.workers)
    progress(f"  {len(payloads)} resolutions")

    clusters = None
    cmap: dict[str, str] = {}
    if cluster_wallets and keep:
        progress(f"building funding graph for {len(keep)} wallets...")
        clusters = fetch_and_build(fetch, sorted(keep))
        cmap = clusters.mapping
        merged = sum(1 for g in clusters.groups.values() if len(g) > 1)
        progress(f"  {merged} multi-wallet operators found")

    progress("analysing...")
    a = analyse(raw, payloads, cfg, cmap)
    a.truncated = truncated
    a.clusters = clusters
    return a
