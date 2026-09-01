"""Typed access to the Polymarket read APIs.

Endpoint behaviour here was verified live; the awkward parts are enforced in
code rather than left as warnings, because each one silently corrupts an
analysis rather than raising:

* ``/trades?market=`` returns at most ~12,000 prints, **most recent first**.
  Older history is simply unreachable.  A market whose tape does not reach
  back to the trade you are studying will quietly yield a fill simulation
  against the wrong window, so coverage is returned alongside the data and
  must be checked.
* ``/activity`` refuses offsets beyond 5,000.  Paging by time window and
  deduplicating recovers full history; paging by offset silently truncates.
* ``gamma-api``'s ``condition_ids`` filter returns ``[]`` rather than an
  error.  The CLOB endpoint is authoritative for resolution; do not
  substitute.

No endpoint below needs an API key.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .netio import Fetcher

DATA_API = "https://data-api.polymarket.com"
CLOB = "https://clob.polymarket.com"
LB_API = "https://lb-api.polymarket.com"
PNL_API = "https://user-pnl-api.polymarket.com"
SITE = "https://polymarket.com"
GAMMA = "https://gamma-api.polymarket.com"
BLOCKSCOUT = "https://polygon.blockscout.com"

#: Server-side ceiling on ``/trades?market=``.
MARKET_TAPE_CAP = 12_000
#: Server-side ceiling on ``/activity`` offsets.
ACTIVITY_OFFSET_CAP = 5_000
WEEK = 7 * 24 * 3600


@dataclass(frozen=True)
class MarketTape:
    """Raw market tape plus how far back it actually reaches.

    Distinct from :class:`polybuyer.tape.Tape`, which is the analysed form.
    """

    condition_id: str
    trades: list[dict]
    #: Earliest timestamp present.  Anything before this is unreachable.
    covers_from: int
    #: True if the server cap was hit, meaning history is truncated.
    truncated: bool

    def covers(self, ts: int) -> bool:
        """Whether this tape reaches back far enough to study ``ts``.

        Always check before simulating a fill: a truncated tape produces a
        confident answer about the wrong period.
        """
        return not self.truncated or ts >= self.covers_from


def market_tape(fetch: Fetcher, condition_id: str, page: int = 2000) -> MarketTape:
    """Full all-participants tape for one market, newest first."""
    rows: list[dict] = []
    for off in range(0, MARKET_TAPE_CAP, page):
        url = f"{DATA_API}/trades?market={condition_id}&limit={page}&offset={off}"
        batch = fetch.get(url)
        if not batch or not isinstance(batch, list):
            break
        rows.extend(batch)
        if len(batch) < page:
            break

    stamps = [int(float(r.get("timestamp", 0))) for r in rows if r.get("timestamp")]
    return MarketTape(
        condition_id=condition_id,
        trades=rows,
        covers_from=min(stamps) if stamps else 0,
        truncated=len(rows) >= MARKET_TAPE_CAP,
    )


def market_resolution(fetch: Fetcher, condition_id: str) -> dict | None:
    """Authoritative resolution: ``closed`` plus ``tokens[].winner``."""
    return fetch.get(f"{CLOB}/markets/{condition_id}")


def market_resolutions(
    fetch: Fetcher, condition_ids: Iterable[str], workers: int = 16
) -> dict[str, dict]:
    cids = list(dict.fromkeys(condition_ids))
    urls = [f"{CLOB}/markets/{c}" for c in cids]
    out: dict[str, dict] = {}
    for cid, payload in zip(cids, fetch.map(urls, workers=workers)):
        if isinstance(payload, dict) and payload:
            out[cid] = payload
    return out


def wallet_activity(
    fetch: Fetcher,
    wallet: str,
    start: int,
    end: int,
    page: int = 500,
    window: int = WEEK,
) -> list[dict]:
    """Full activity history, paged by time window.

    The offset cap makes naive pagination lose everything past 5,000
    records.  Weekly windows sidestep it; boundary records are re-read by
    construction, so the caller must deduplicate.
    """
    rows: list[dict] = []
    t = start
    while t < end:
        hi = min(t + window, end)
        for off in range(0, ACTIVITY_OFFSET_CAP, page):
            url = (f"{DATA_API}/activity?user={wallet}&limit={page}&offset={off}"
                   f"&start={t}&end={hi}")
            batch = fetch.get(url)
            if not batch or not isinstance(batch, list):
                break
            rows.extend(batch)
            if len(batch) < page:
                break
        t = hi
    return rows


def wallet_trades(fetch: Fetcher, wallet: str, page: int = 500,
                  max_pages: int = 40) -> list[dict]:
    """Recent trades for one wallet.

    The offset ceiling here is unverified, so this is for recent activity
    only.  For full history use :func:`wallet_activity`.
    """
    return fetch.paginate(
        lambda off: f"{DATA_API}/trades?user={wallet}&limit={page}&offset={off}",
        page_size=page,
        max_pages=max_pages,
    )


def big_trades(fetch: Fetcher, min_usd: float = 10_000.0, page: int = 500,
               pages: int = 40) -> list[dict]:
    """Recent trades above a notional floor, filtered server-side.

    The best candidate generator available: there is no leaderboard listing
    endpoint, and this biases toward currently-active large traders, which
    is the population worth screening anyway.
    """
    return fetch.paginate(
        lambda off: (f"{DATA_API}/trades?filterType=CASH&filterAmount={int(min_usd)}"
                     f"&limit={page}&offset={off}"),
        page_size=page,
        max_pages=pages,
    )


def recent_trades(fetch: Fetcher, page: int = 500, pages: int = 20) -> list[dict]:
    """Unfiltered global tape -- broader candidate sweep."""
    return fetch.paginate(
        lambda off: f"{DATA_API}/trades?limit={page}&offset={off}",
        page_size=page,
        max_pages=pages,
    )


def top_markets(
    fetch: Fetcher,
    pages: int = 8,
    per_page: int = 100,
    closed: bool = True,
) -> list[dict]:
    """Highest-volume markets, newest-first by volume, via gamma.

    The handoff recorded gamma as unusable, but that applies only to its
    ``condition_ids`` filter, which returns ``[]`` rather than erroring.  The
    plain listing works and is the only way to enumerate markets by anything
    other than "recently traded".

    That distinction matters for what this pipeline is looking for.  Sweeping
    recent large trades lands on whatever is churning right now -- in
    practice esports and live sport -- whereas ranking by volume surfaces the
    elections, geopolitics and macro markets where informed news flow
    actually trades.  ``tag_slug`` is silently ignored by the API, so any
    category filtering has to happen client-side.
    """
    out: list[dict] = []
    for page in range(pages):
        url = (f"{GAMMA}/markets?closed={'true' if closed else 'false'}"
               f"&limit={per_page}&offset={page * per_page}"
               f"&order=volumeNum&ascending=false")
        batch = fetch.get(url)
        if not batch or not isinstance(batch, list):
            break
        out.extend(batch)
        if len(batch) < per_page:
            break
    return out


def positions(fetch: Fetcher, wallet: str) -> list[dict]:
    url = f"{DATA_API}/positions?user={wallet}&limit=500&sizeThreshold=0"
    return fetch.get(url) or []


def markets_traded(fetch: Fetcher, wallet: str) -> int:
    """Count of markets this wallet has traded -- a cheap breadth filter."""
    r = fetch.get(f"{DATA_API}/traded?user={wallet}")
    if isinstance(r, dict):
        for k in ("traded", "count", "value"):
            if k in r:
                try:
                    return int(r[k])
                except (TypeError, ValueError):
                    pass
    if isinstance(r, (int, float)):
        return int(r)
    return 0


def portfolio_value(fetch: Fetcher, wallet: str) -> float:
    r = fetch.get(f"{DATA_API}/value?user={wallet}")
    if isinstance(r, list) and r:
        r = r[0]
    if isinstance(r, dict):
        for k in ("value", "portfolioValue", "amount"):
            if k in r:
                try:
                    return float(r[k])
                except (TypeError, ValueError):
                    pass
    return 0.0


def leaderboard_rank(fetch: Fetcher, wallet: str, window: str = "all",
                     kind: str = "pnl") -> dict | None:
    """Per-address rank.  There is no listing endpoint -- only lookup."""
    return fetch.get(f"{LB_API}/rank?address={wallet}&window={window}&rankType={kind}")


def profile(fetch: Fetcher, wallet: str) -> dict | None:
    return fetch.get(f"{SITE}/api/profile/userData?address={wallet}")


def pnl_series(fetch: Fetcher, wallet: str, interval: str = "all",
               fidelity: str = "1d") -> list[dict]:
    url = (f"{PNL_API}/user-pnl?user_address={wallet}&interval={interval}"
           f"&fidelity={fidelity}")
    r = fetch.get(url)
    return r if isinstance(r, list) else []


def token_transfers(fetch: Fetcher, address: str, limit: int = 10_000) -> list[dict]:
    """Bulk on-chain token transfers, no key required.

    Used to build the funding graph for cluster detection.  Far faster than
    the paginated v2 API, which caps at 50 per page.
    """
    url = (f"{BLOCKSCOUT}/api?module=account&action=tokentx"
           f"&address={address}&offset={limit}&sort=desc")
    r = fetch.get(url)
    if isinstance(r, dict) and isinstance(r.get("result"), list):
        return r["result"]
    return []
