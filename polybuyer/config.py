"""Tunable parameters for the discovery pipeline.

Everything that could reasonably be argued about lives here, so that a
sensitivity sweep is a loop over configs rather than a grep through the
codebase.  Defaults are the values used in the reference run; where a
default encodes a finding from the prior research phase it is noted.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True)
class JumpConfig:
    """Repricing-event ("jump") detection.

    A jump is a large, *persistent* move in the market's probability.  These
    are the moments when information arrives, and they are the reference
    points against which every trader is timed.
    """

    #: Width of the time buckets the price path is resampled onto, seconds.
    bucket_s: int = 60

    #: Look-back used to establish the pre-jump baseline level, seconds.
    baseline_s: int = 3600

    #: Look-forward used to establish the post-jump level, seconds.
    horizon_s: int = 3600

    #: Minimum absolute move, in probability points, to qualify as a jump.
    #: 0.08 keeps genuine news repricings and rejects ordinary drift.
    min_move: float = 0.08

    #: A jump must *stick*: the price this far out must retain at least
    #: ``persistence_frac`` of the move, else it was a spike-and-revert.
    persistence_s: int = 6 * 3600
    persistence_frac: float = 0.5

    #: Minimum separation between two reported jumps, seconds.  Prevents one
    #: repricing being counted several times by overlapping windows.
    min_separation_s: int = 2 * 3600

    #: Fraction of the total move that must be covered before we accept
    #: that the market has committed to the new level.
    onset_cover_frac: float = 0.25

    #: The pre-jump level must be *settled*.  If the baseline window is
    #: itself volatile we have no level to measure a move against, and the
    #: return leg of a spike gets reported as news.  Rejects a candidate
    #: whose baseline spread exceeds this fraction of the move.
    max_baseline_spread_frac: float = 0.5

    #: Minimum half-width of the "still at baseline" band when walking back
    #: to find where the move actually started, in probability points.
    onset_band_min: float = 0.015

    #: A bucket needs this many trades before its price is trusted.  Thin
    #: prints produce phantom jumps.
    min_bucket_trades: int = 1

    #: Ignore jumps in markets whose tape is thinner than this.
    min_market_trades: int = 60


@dataclass(frozen=True)
class WindowConfig:
    """Lead-time windows that define the behavioural archetypes.

    These three windows partition a trader's entries relative to a jump's
    onset, and the partition *is* the classification:

    ``pre``   entered before the market moved            -> anticipatory
    ``fast``  entered in the first moments of the move    -> news reaction
    ``late``  entered once the move was public            -> follower
    """

    #: How far before onset still counts as "positioned for this jump".
    #: Longer than this and you are just a buy-and-hold holder who got lucky.
    pre_s: int = 6 * 3600

    #: Entries within this many seconds after onset count as fast reaction.
    #: 120s is generous for a human with a good feed; sub-10s implies an
    #: automated wire.
    fast_s: int = 120

    #: Dead band immediately *before* onset, seconds.  Trades in here are
    #: counted as reaction, not anticipation.
    #:
    #: This is a deliberate concession to what the data can actually
    #: support.  The tape has one-second timestamps and shows only executed
    #: prints, so "traded 2s before the first print of the move" and
    #: "was the first to react to the news" are the same observation.  An
    #: insider claim should rest on being positioned minutes-to-hours
    #: early, not on sub-minute ordering we cannot really resolve.
    guard_s: int = 120

    #: Entries after ``fast_s`` but within this window are still "on the
    #: move" rather than absent; used for the reaction-latency curve.
    react_tail_s: int = 6 * 3600


@dataclass(frozen=True)
class FollowConfig:
    """Simulated-follow parameters.

    Answers "if I had copied this trade, what would I actually have got?"
    Fills come exclusively from the executed tape (no historical order books
    exist), so every number here is a **lower bound** on true fillability.
    """

    #: Slippage cap in probability points above the target's print.
    #: The prior phase found +2c beat +1c: a wider cap buys participation in
    #: the winners, and participation dominates the extra cost paid.
    cap: float = 0.02

    #: How long after the target's print we keep trying to fill, seconds.
    window_s: int = 600

    #: Follower sizing ladder, keyed on the *target's own* notional
    #: percentiles so it self-normalises across traders of different scale.
    size_lo_pct: float = 10.0
    size_hi_pct: float = 80.0
    size_lo_usd: float = 50.0
    size_hi_usd: float = 1000.0

    #: Exclude the target's own cluster from the liquidity we consume.
    exclude_self_cluster: bool = True


@dataclass(frozen=True)
class ScreenConfig:
    """Exclusions.  These populations look elite on volume/PnL screens but
    carry no directional signal, so they are removed before ranking."""

    #: Minimum distinct markets before a trader is scoreable at all.
    min_markets: int = 40

    #: Minimum detected jumps the trader was present for.
    min_jumps: int = 12

    #: Minimum gross buy notional, USD.
    min_notional: float = 25_000.0

    #: A directional trader must at some point actually *hold* a position.
    #: Measured as peak |position| / gross volume traded in the market: a
    #: market maker alternating both ways never accumulates one and scores
    #: near zero, while someone who builds a position and later takes profit
    #: still scores ~0.5.  Using net-vs-gross instead would screen out the
    #: profit-taker too, which is wrong -- closing a winner is not quoting.
    min_position_ratio: float = 0.15

    #: Above this share of negative-risk markets, the "positions" are
    #: structural mints rather than opinions (see NegRiskAdapter).
    max_negrisk_share: float = 0.50

    #: Drop traders whose edge does not survive removing their best markets.
    concentration_drop_n: int = 5

    #: Minimum repricings a trader must have participated in *in the relevant
    #: window* before that archetype can be scored at all.  Being early once
    #: is an anecdote.
    min_archetype_events: int = 10


@dataclass(frozen=True)
class StatsConfig:
    """Significance.  The independent unit is the *market*, never the trade:
    every trade in a market shares one resolution.  Per-trade resampling
    overstates significance by orders of magnitude."""

    n_boot: int = 4000
    ci_lo: float = 2.5
    ci_hi: float = 97.5
    seed: int = 20260901

    #: Benjamini-Hochberg false-discovery rate for the candidate sweep.  A
    #: raw p-value means nothing when several hundred wallets are tested at
    #: once; this is the gate a trader must clear to be recommended rather
    #: than merely watched.
    fdr_q: float = 0.10

    #: Minimum independent clusters (markets) before a bootstrap interval is
    #: reported as anything but underpowered.
    min_clusters: int = 8


@dataclass(frozen=True)
class HarvestConfig:
    """Candidate generation."""

    #: Server-side notional floor for the REST discovery sweep, USD.
    cash_filter_usd: float = 10_000.0

    #: Trades to pull per discovery page.
    page_limit: int = 500

    #: How many pages of the global tape to sweep.
    pages: int = 40

    #: Cap on candidates carried into the (expensive) deep-analysis stage.
    max_candidates: int = 400

    #: Markets sampled per candidate for tape-level analysis.
    max_markets_per_wallet: int = 120


@dataclass(frozen=True)
class Config:
    jump: JumpConfig = field(default_factory=JumpConfig)
    window: WindowConfig = field(default_factory=WindowConfig)
    follow: FollowConfig = field(default_factory=FollowConfig)
    screen: ScreenConfig = field(default_factory=ScreenConfig)
    stats: StatsConfig = field(default_factory=StatsConfig)
    harvest: HarvestConfig = field(default_factory=HarvestConfig)

    #: Root for the on-disk response cache.  Every network response is
    #: cached so an analysis can be re-run and audited without re-fetching.
    cache_dir: str = ".polycache"

    #: Concurrency for REST fetches.
    workers: int = 12

    def with_(self, **kw: Any) -> "Config":
        """Return a copy with top-level fields replaced."""
        return replace(self, **kw)


DEFAULT = Config()
