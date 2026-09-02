"""Core data model: trades normalised to a single reference outcome.

Polymarket quotes every outcome token separately.  A BUY of NO at 30c and a
SELL of YES at 70c are the same economic act, and unless they are collapsed
onto one axis the price path of a market is nonsense -- it jumps between the
YES and NO quote depending on which token happened to print.

Everything downstream (price paths, jump detection, PnL, fills) consumes
:class:`Trade` in *reference* terms, meaning outcome index 0 of the market:

    ref_price   price of outcome 0 implied by this print
    ref_signed  change in the trader's outcome-0 share exposure
                (positive = more long outcome 0)

so a BUY of NO at 0.30 becomes ``ref_price=0.70, ref_signed=-size``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Sequence

BUY = "BUY"
SELL = "SELL"


@dataclass(frozen=True, slots=True)
class Trade:
    ts: int
    wallet: str
    condition_id: str
    asset: str
    outcome_index: int
    side: str
    price: float
    size: float
    ref_price: float
    ref_signed: float
    tx: str = ""
    slug: str = ""
    title: str = ""
    event_slug: str = ""

    @property
    def notional(self) -> float:
        """USD value of the print."""
        return self.size * self.price

    @property
    def is_long_ref(self) -> bool:
        return self.ref_signed > 0


def _norm_wallet(w: Any) -> str:
    return str(w or "").strip().lower()


def normalise(raw: dict) -> Trade | None:
    """Convert one ``data-api`` / firehose trade payload into a :class:`Trade`.

    Returns ``None`` for records that cannot be interpreted (missing price,
    zero size, unknown side) rather than raising -- the tape endpoints do
    occasionally emit partial rows and one bad record should not abort a
    market.
    """
    try:
        side = str(raw.get("side", "")).upper()
        if side not in (BUY, SELL):
            return None

        price = float(raw["price"])
        size = float(raw["size"])
        if not (0.0 < price < 1.0) or size <= 0:
            return None

        oi = int(raw.get("outcomeIndex", 0))
        ts = int(float(raw["timestamp"]))
    except (KeyError, TypeError, ValueError):
        return None

    # Collapse onto outcome 0.  Buying outcome 1 is shorting outcome 0.
    if oi == 0:
        ref_price = price
        ref_signed = size if side == BUY else -size
    else:
        ref_price = 1.0 - price
        ref_signed = -size if side == BUY else size

    return Trade(
        ts=ts,
        wallet=_norm_wallet(raw.get("proxyWallet") or raw.get("user") or raw.get("maker")),
        condition_id=str(raw.get("conditionId", "")),
        asset=str(raw.get("asset", "")),
        outcome_index=oi,
        side=side,
        price=price,
        size=size,
        ref_price=ref_price,
        ref_signed=ref_signed,
        tx=str(raw.get("transactionHash", "")),
        slug=str(raw.get("slug", "")),
        title=str(raw.get("title", "")),
        event_slug=str(raw.get("eventSlug", "")),
    )


def normalise_many(rows: Iterable[dict]) -> list[Trade]:
    out = [t for t in (normalise(r) for r in rows) if t is not None]
    out.sort(key=lambda t: (t.ts, t.tx))
    return out


def dedupe(trades: Sequence[Trade]) -> list[Trade]:
    """Drop duplicate prints.

    Paged and windowed fetches overlap by construction (the ``/activity``
    weekly-window trick in particular re-reads boundary records), so
    deduplication is mandatory before any PnL is computed.
    """
    seen: set[tuple] = set()
    out: list[Trade] = []
    for t in trades:
        key = (t.tx, t.wallet, t.asset, t.ts, t.side, round(t.price, 6), round(t.size, 6))
        if key in seen:
            continue
        seen.add(key)
        out.append(t)
    return out


@dataclass(frozen=True, slots=True)
class Resolution:
    """Terminal payoff for a market, from the CLOB (authoritative)."""

    condition_id: str
    closed: bool
    #: token id -> 1.0 for the winning token, 0.0 for the losers.
    payoffs: dict[str, float]
    #: Terminal value of outcome 0, i.e. the reference axis.  None if the
    #: market has not resolved or the winner could not be determined.
    ref_terminal: float | None
    neg_risk: bool = False
    #: A scheduled match: the market has a kickoff time.
    #:
    #: **This says the market is about a scheduled event, not that any given
    #: trade happened during it.** The two were conflated once, and it
    #: mislabelled a copy strategy as a latency race against television:
    #: 95% of the cluster's entries turned out to be *before* kickoff, at a
    #: median of 30 minutes ahead. Compare an entry against
    #: :attr:`game_start_ts` to tell pre-match from in-play.
    #:
    #: For *market selection* the flag is used correctly as-is: the news
    #: desk excludes match markets whatever the entry timing, because a
    #: score is not an announcement.
    in_play: bool = False

    #: Kickoff, unix seconds, when the market has one. This is what makes
    #: the pre-match / in-play distinction measurable.
    game_start_ts: int | None = None

    @property
    def is_terminal(self) -> bool:
        return self.closed and self.ref_terminal is not None


def resolution_from_clob(condition_id: str, payload: dict) -> Resolution:
    """Build a :class:`Resolution` from ``clob.polymarket.com/markets/{id}``.

    The CLOB returns ``tokens[]`` with a ``winner`` boolean once a market
    settles.  Token order in that array follows outcome index, which is what
    lets us recover the terminal value on the reference axis.
    """
    tokens = payload.get("tokens") or []
    closed = bool(payload.get("closed", False))
    payoffs: dict[str, float] = {}
    ref_terminal: float | None = None

    any_winner = any(bool(tk.get("winner")) for tk in tokens)
    for idx, tk in enumerate(tokens):
        tid = str(tk.get("token_id", ""))
        if not tid:
            continue
        win = bool(tk.get("winner"))
        payoffs[tid] = 1.0 if win else 0.0
        if idx == 0 and any_winner:
            ref_terminal = 1.0 if win else 0.0

    if not any_winner:
        # Closed but unlabelled (or still open): no terminal payoff.
        payoffs = {}
        ref_terminal = None

    return Resolution(
        condition_id=condition_id,
        closed=closed,
        payoffs=payoffs,
        ref_terminal=ref_terminal,
        neg_risk=bool(payload.get("neg_risk", False)),
        in_play=bool(payload.get("game_start_time")),
        game_start_ts=_game_start(payload.get("game_start_time")),
    )


def _game_start(raw: Any) -> int | None:
    """Kickoff as unix seconds. Accepts ISO strings and epoch numbers."""
    if raw in (None, "", 0):
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    try:
        import datetime as _dt
        return int(_dt.datetime.fromisoformat(
            str(raw).replace("Z", "+00:00")).timestamp())
    except (TypeError, ValueError):
        return None
