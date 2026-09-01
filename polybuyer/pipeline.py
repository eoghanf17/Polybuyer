"""End-to-end analysis, independent of where the data came from.

Deliberately split from the network layer: this function takes raw trade
records and CLOB market payloads as plain dicts, so the same code path runs
against a live fetch, a cached corpus on disk, or a synthetic fixture.  That
is what makes the detector testable at all -- the behaviour it looks for is
rare enough in real data that you would never be sure a change had broken it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Config
from .features import WalletFeatures, extract_all
from .jumps import Jump, detect
from .model import Resolution, dedupe, normalise_many, resolution_from_clob
from .scores import Verdict, rank
from .tape import Tape, build_tapes


@dataclass
class Analysis:
    tapes: dict[str, Tape]
    jumps: dict[str, list[Jump]]
    resolutions: dict[str, Resolution]
    features: dict[str, WalletFeatures]
    ranked: list[tuple[Verdict, WalletFeatures]]

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
    jumps = {cid: detect(tape, cfg.jump) for cid, tape in tapes.items()}
    feats = extract_all(tapes, jumps, resolutions, cfg, clusters)
    ranked = rank(feats, cfg)

    return Analysis(
        tapes=tapes,
        jumps=jumps,
        resolutions=resolutions,
        features=feats,
        ranked=ranked,
    )
