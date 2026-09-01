"""Synthetic market tapes with known ground truth.

The detector's whole job is to tell four populations apart, so the tests
build markets containing all four by construction and check that it does:

    insider   accumulates correctly, quietly, before the price moves
    newsdesk  reacts correctly within seconds of the move starting
    follower  arrives well after the move is public
    maker     quotes both sides continuously, holds no opinion
    noise     random punters, the background

Trades are emitted in raw ``data-api`` wire form -- sometimes quoted on
outcome 0, sometimes on outcome 1 -- so that every test also exercises the
reference-axis normalisation round-trip.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


def raw_trade(
    ts: int,
    ref_price: float,
    wallet: str,
    ref_signed: float,
    condition_id: str = "0xtest",
    quote_on: int = 0,
    tx: str | None = None,
) -> dict:
    """Emit one wire-format trade with the given *reference* semantics.

    ``quote_on`` picks which outcome token the print is quoted against;
    both encodings must normalise back to the same ``(ref_price,
    ref_signed)`` pair.
    """
    size = abs(ref_signed)
    long_ref = ref_signed > 0
    if quote_on == 0:
        side = "BUY" if long_ref else "SELL"
        price = ref_price
    else:
        side = "SELL" if long_ref else "BUY"
        price = 1.0 - ref_price

    price = min(max(price, 0.001), 0.999)
    return {
        "timestamp": ts,
        "proxyWallet": wallet,
        "conditionId": condition_id,
        "asset": f"{condition_id}-{quote_on}",
        "outcomeIndex": quote_on,
        "side": side,
        "price": round(price, 4),
        "size": round(size, 4),
        "transactionHash": tx or f"0x{ts:08x}{abs(hash(wallet)) % 10**6:06x}",
        "slug": "synthetic-market",
        "title": "Synthetic Market",
        "eventSlug": "synthetic-event",
    }


@dataclass
class MarketSpec:
    """Recipe for one synthetic market."""

    condition_id: str = "0xtest"
    t0: int = 1_750_000_000
    duration_s: int = 14 * 24 * 3600
    p_before: float = 0.30
    p_after: float = 0.75
    #: Seconds after ``t0`` at which the repricing happens.
    jump_at_s: int = 7 * 24 * 3600
    #: How long the repricing takes to complete.  Short = a gap, long = a
    #: diffusion that a follower could actually trade.
    jump_dur_s: int = 300
    noise_sd: float = 0.012
    n_noise: int = 900
    #: Prints concentrated around the repricing.  Real markets see attention
    #: and volume spike hard on news; a uniformly-thin tape would leave the
    #: move itself almost unsampled, and onset resolution is bounded by
    #: print density.
    n_burst: int = 500
    burst_tail_s: int = 3600
    n_makers: int = 2
    maker_trades: int = 200
    seed: int = 7
    #: Planted actors: (wallet, kind, correct?) where kind is one of
    #: "insider" / "newsdesk" / "follower".
    actors: list[tuple[str, str, bool]] = field(default_factory=list)
    #: Whether the market resolves to the reference outcome.
    resolves_ref: bool | None = None


def _path(spec: MarketSpec, ts: int) -> float:
    """Deterministic price path: flat, ramp, flat."""
    jt = spec.t0 + spec.jump_at_s
    if ts < jt:
        return spec.p_before
    if ts >= jt + spec.jump_dur_s:
        return spec.p_after
    frac = (ts - jt) / max(1, spec.jump_dur_s)
    return spec.p_before + frac * (spec.p_after - spec.p_before)


def build(spec: MarketSpec) -> tuple[list[dict], dict]:
    """Generate a market.  Returns ``(raw_trades, ground_truth)``."""
    rng = random.Random(spec.seed)
    rows: list[dict] = []
    jt = spec.t0 + spec.jump_at_s
    end = spec.t0 + spec.duration_s
    direction = 1 if spec.p_after > spec.p_before else -1

    def px(ts: int) -> float:
        return min(max(_path(spec, ts) + rng.gauss(0, spec.noise_sd), 0.02), 0.98)

    # Background punters, uniformly spread, no edge.
    for i in range(spec.n_noise):
        ts = rng.randint(spec.t0, end)
        w = f"0xnoise{rng.randrange(60):03d}"
        sz = rng.uniform(20, 400)
        sign = 1.0 if rng.random() < 0.5 else -1.0
        rows.append(raw_trade(ts, px(ts), w, sign * sz, spec.condition_id, rng.randrange(2)))

    # The news burst: attention spikes when the price moves, decaying away
    # over the following hour.
    for i in range(spec.n_burst):
        if i % 2 == 0:
            ts = rng.randint(jt, jt + max(1, spec.jump_dur_s))
        else:
            ts = jt + int(rng.expovariate(1.0 / max(60.0, spec.burst_tail_s / 4)))
            ts = min(ts, jt + spec.burst_tail_s)
        ts = min(ts, end)
        w = f"0xburst{rng.randrange(80):03d}"
        sz = rng.uniform(30, 600)
        sign = 1.0 if rng.random() < 0.5 else -1.0
        rows.append(raw_trade(ts, px(ts), w, sign * sz, spec.condition_id, rng.randrange(2)))

    # Market makers: continuous two-sided quoting, flat net exposure.
    for m in range(spec.n_makers):
        w = f"0xmaker{m:03d}"
        for i in range(spec.maker_trades):
            ts = rng.randint(spec.t0, end)
            sz = rng.uniform(100, 500)
            sign = 1.0 if i % 2 == 0 else -1.0
            rows.append(raw_trade(ts, px(ts), w, sign * sz, spec.condition_id, rng.randrange(2)))

    truth: dict = {"jump_ts": jt, "direction": direction, "actors": {}}

    for wallet, kind, correct in spec.actors:
        sign = float(direction if correct else -direction)
        truth["actors"][wallet] = {"kind": kind, "correct": correct}

        if kind == "insider":
            # Accumulates in the hours before the move, in several clips so
            # it looks like ordinary accumulation rather than one block.
            for k in range(4):
                ts = jt - rng.randint(600, 5 * 3600)
                rows.append(
                    raw_trade(ts, px(ts), wallet, sign * rng.uniform(800, 2000),
                              spec.condition_id, rng.randrange(2))
                )
        elif kind == "newsdesk":
            # Hits within seconds of the move starting.
            for k in range(3):
                ts = jt + rng.randint(1, 45)
                rows.append(
                    raw_trade(ts, px(ts), wallet, sign * rng.uniform(600, 1500),
                              spec.condition_id, rng.randrange(2))
                )
        elif kind == "follower":
            # Arrives once the repricing is common knowledge.
            for k in range(3):
                ts = jt + rng.randint(20 * 60, 3 * 3600)
                rows.append(
                    raw_trade(ts, px(ts), wallet, sign * rng.uniform(500, 1200),
                              spec.condition_id, rng.randrange(2))
                )

    rows.sort(key=lambda r: r["timestamp"])
    resolves = spec.resolves_ref
    if resolves is None:
        resolves = spec.p_after > 0.5
    truth["ref_terminal"] = 1.0 if resolves else 0.0
    return rows, truth


def clob_payload(condition_id: str, ref_wins: bool, neg_risk: bool = False) -> dict:
    """A CLOB ``/markets/{id}`` payload matching :func:`build`'s truth."""
    return {
        "condition_id": condition_id,
        "closed": True,
        "neg_risk": neg_risk,
        "tokens": [
            {"token_id": f"{condition_id}-0", "outcome": "Yes", "winner": ref_wins},
            {"token_id": f"{condition_id}-1", "outcome": "No", "winner": not ref_wins},
        ],
    }


def universe(
    n_markets: int = 40,
    insider: str = "0xINSIDER",
    newsdesk: str = "0xNEWSDESK",
    follower: str = "0xFOLLOWER",
    insider_hit: float = 0.85,
    news_hit: float = 0.80,
    follower_hit: float = 0.5,
    seed: int = 11,
    jump_dur_s: int = 300,
) -> tuple[list[dict], dict[str, dict], dict]:
    """A whole synthetic universe of markets sharing the same actors.

    ``*_hit`` is the fraction of markets in which that actor is on the right
    side.  A follower at 0.5 is, by construction, uninformed -- they are
    reacting to a move that has already happened.
    """
    rng = random.Random(seed)
    all_rows: list[dict] = []
    payloads: dict[str, dict] = {}
    truths: dict[str, dict] = {}

    for i in range(n_markets):
        cid = f"0xmkt{i:04d}"
        up = rng.random() < 0.5
        p_before = rng.uniform(0.25, 0.45)
        delta = rng.uniform(0.15, 0.40)
        p_after = min(0.95, p_before + delta) if up else max(0.05, p_before - delta)

        spec = MarketSpec(
            condition_id=cid,
            t0=1_750_000_000 + i * 3600,
            p_before=p_before,
            p_after=p_after,
            jump_dur_s=jump_dur_s,
            seed=seed * 1000 + i,
            actors=[
                (insider, "insider", rng.random() < insider_hit),
                (newsdesk, "newsdesk", rng.random() < news_hit),
                (follower, "follower", rng.random() < follower_hit),
            ],
        )
        rows, truth = build(spec)
        all_rows.extend(rows)
        truths[cid] = truth
        payloads[cid] = clob_payload(cid, ref_wins=truth["ref_terminal"] > 0.5)

    return all_rows, payloads, truths
