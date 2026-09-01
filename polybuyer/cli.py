"""Command-line entry point.

    python -m polybuyer demo              offline, synthetic, no network
    python -m polybuyer discover          live sweep against the APIs
    python -m polybuyer wallets 0x... 0x. deep-dive named wallets
    python -m polybuyer selftest          run the test suite
"""

from __future__ import annotations

import argparse
import sys

import dataclasses

from .config import DEFAULT, Config, StatsConfig
from .netio import Fetcher
from .report import detail, summary, table, to_json


def _cfg(args) -> Config:
    cfg = DEFAULT
    if args.cap is not None:
        cfg = cfg.with_(follow=dataclasses.replace(cfg.follow, cap=args.cap))
    if args.boot is not None:
        cfg = cfg.with_(stats=dataclasses.replace(cfg.stats, n_boot=args.boot))
    if args.cache:
        cfg = cfg.with_(cache_dir=args.cache)
    return cfg


def _emit(a, args, n_seen: int, cfg) -> None:
    if args.json:
        print(to_json(a.ranked))
        return
    print(summary(a.ranked, n_seen, n_markets=len(a.tapes),
                  min_markets=cfg.screen.min_markets,
                  n_truncated=len(a.truncated)))
    print()
    print(table(a.ranked, limit=args.limit))
    print()
    for v, f in a.ranked[: args.detail]:
        print(detail(v, f))
        print()


def cmd_demo(args) -> int:
    """Run the whole pipeline on a synthetic universe.

    Useful as a smoke test and as a worked example: the universe contains a
    planted insider, a planted news desk, a follower, market makers and a
    crowd of noise, so the output shows what a real detection looks like.
    """
    sys.path.insert(0, ".")
    from tests import synthetic as syn
    from .pipeline import analyse

    cfg = _cfg(args)
    if args.boot is None:
        cfg = cfg.with_(stats=dataclasses.replace(cfg.stats, n_boot=1500))

    # Breadth screens are calibrated for a live sweep of thousands of
    # markets.  Left alone on a small demo universe they are unsatisfiable
    # by construction and the demo silently reports nothing, which looks
    # like a broken pipeline rather than a misconfigured one.
    if args.markets < cfg.screen.min_markets:
        cfg = cfg.with_(screen=dataclasses.replace(
            cfg.screen,
            min_markets=max(5, int(args.markets * 0.75)),
            min_effective_n=max(5.0, args.markets * 0.75),
        ))
        print(f"  (small universe: breadth screens scaled to "
              f"{cfg.screen.min_markets} markets)", file=sys.stderr)

    print(f"building synthetic universe ({args.markets} markets)...", file=sys.stderr)
    rows, payloads, _ = syn.universe(n_markets=args.markets, jump_dur_s=args.jump_dur)
    print(f"  {len(rows)} prints across {len(payloads)} markets", file=sys.stderr)
    a = analyse(rows, payloads, cfg)
    print(f"  {a.n_jumps} repricings detected\n", file=sys.stderr)
    _emit(a, args, len(a.features), cfg)
    return 0


def cmd_discover(args) -> int:
    from .pipeline import discover

    cfg = _cfg(args)
    fetch = Fetcher(cache_dir=cfg.cache_dir, use_cache=not args.no_cache)
    a = discover(fetch, cfg, max_markets=args.markets,
                 cluster_wallets=not args.no_clusters,
                 universe=args.universe,
                 exclude_in_play=not args.include_in_play,
                 since_days=args.days,
                 progress=lambda m: print(m, file=sys.stderr))
    print(f"cache: {fetch.stats}", file=sys.stderr)
    _emit(a, args, len(a.features), cfg)
    return 0


def cmd_wallets(args) -> int:
    """Deep-dive specific wallets by pulling every market they traded."""
    from .harvest import collect_markets
    from .pipeline import analyse
    from .sources import market_resolutions, wallet_trades

    cfg = _cfg(args)
    fetch = Fetcher(cache_dir=cfg.cache_dir, use_cache=not args.no_cache)
    targets = [w.strip().lower() for w in args.wallets]

    cids: list[str] = []
    for w in targets:
        rows = wallet_trades(fetch, w)
        print(f"{w}: {len(rows)} recent trades", file=sys.stderr)
        for r in rows:
            c = str(r.get("conditionId") or "")
            if c and c not in cids:
                cids.append(c)
    cids = cids[: args.markets]
    print(f"fetching {len(cids)} market tapes...", file=sys.stderr)

    raw, trunc = collect_markets(fetch, cids)
    payloads = market_resolutions(fetch, cids, workers=cfg.workers)
    a = analyse(raw, payloads, cfg)
    a.truncated = {c for c, t in trunc.items() if t}

    for w in targets:
        r = a.by_wallet(w)
        if r is None:
            f = a.features.get(w)
            if f is None:
                print(f"\n{w}: no trades found in the fetched markets")
                continue
            from .scores import classify
            print(f"\n{w}: screened out -- {classify(f, cfg).excluded}")
            continue
        print()
        print(detail(*r))
    return 0


def cmd_follow(args) -> int:
    """Evaluate copy strategies against recorded liquidity.

    The question this answers: the headline copy-strategy PnLs were computed
    with mechanical slippage, which assumes you fill your whole size at the
    target's price plus a tick. What happens when you can only fill from
    prints that actually executed?
    """
    from .follow import STRATEGIES, evaluate, render
    from .harvest import collect_markets
    from .model import dedupe, normalise_many, resolution_from_clob
    from .sources import market_resolutions, wallet_trades
    from .tape import build_tapes

    cfg = _cfg(args)
    fetch = Fetcher(cache_dir=cfg.cache_dir, use_cache=not args.no_cache)
    wallets = [w.strip().lower() for w in args.wallets]

    cids: list[str] = []
    for w in wallets:
        rows = wallet_trades(fetch, w, max_pages=args.pages)
        print(f"{w}: {len(rows)} trades", file=sys.stderr)
        for r in rows:
            c = str(r.get("conditionId") or "")
            if c and c not in cids:
                cids.append(c)
    cids = cids[: args.markets]
    print(f"fetching {len(cids)} market tapes...", file=sys.stderr)

    raw, trunc = collect_markets(fetch, cids)
    payloads = market_resolutions(fetch, cids, workers=cfg.workers)
    print(f"  {len(raw)} prints, {len(payloads)} resolutions", file=sys.stderr)

    tapes = build_tapes(dedupe(normalise_many(raw)))
    resolutions = {c: resolution_from_clob(c, p) for c, p in payloads.items()}
    ticks = {}
    for c, p in payloads.items():
        try:
            ticks[c] = float(p.get("minimum_tick_size") or 0.01)
        except (TypeError, ValueError):
            ticks[c] = 0.01
    truncated = {c for c, t in trunc.items() if t}

    names = args.strategies.split(",") if args.strategies else list(STRATEGIES)
    outs = []
    for name in names:
        if name not in STRATEGIES:
            print(f"unknown strategy {name!r}", file=sys.stderr)
            continue
        outs.append(evaluate(name, wallets, tapes, resolutions, cfg,
                             truncated=truncated, ticks=ticks,
                             slippage_ticks=args.ticks))
    print(render(outs, cfg.follow.cap, args.ticks))
    return 0


def cmd_selftest(args) -> int:
    import unittest
    loader = unittest.TestLoader()
    suite = loader.discover("tests", top_level_dir=".")
    res = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if res.wasSuccessful() else 1


def main(argv: list[str] | None = None) -> int:
    # Shared options live on a parent parser so they are accepted either
    # before or after the subcommand -- argparse otherwise rejects the
    # position most people try first.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--cap", type=float,
                        help="slippage cap in probability points (default 0.02)")
    common.add_argument("--boot", type=int, help="bootstrap resamples")
    common.add_argument("--cache", help="cache directory")
    common.add_argument("--no-cache", action="store_true", help="bypass the disk cache")
    common.add_argument("--json", action="store_true", help="emit JSON instead of a report")
    common.add_argument("--limit", type=int, default=25, help="rows in the ranking table")
    common.add_argument("--detail", type=int, default=5, help="wallets to expand in full")

    p = argparse.ArgumentParser(
        prog="polybuyer",
        parents=[common],
        description="Find Polymarket traders whose timing looks informed, "
                    "and work out whether they can actually be copied.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("demo", parents=[common],
                       help="run offline on a synthetic universe")
    d.add_argument("--markets", type=int, default=40)
    d.add_argument("--jump-dur", type=int, default=300,
                   help="seconds a repricing takes (1 = instant gap)")
    d.set_defaults(func=cmd_demo)

    v = sub.add_parser("discover", parents=[common],
                       help="live sweep against the Polymarket APIs")
    v.add_argument("--markets", type=int, default=150)
    v.add_argument("--no-clusters", action="store_true")
    v.add_argument("--universe", choices=["recent", "volume"], default="volume",
                   help="'volume': highest-volume markets (elections, geopolitics, "
                        "macro -- where informed news flow trades). 'recent': sweep "
                        "recent large trades (biases to whatever is churning now, "
                        "in practice esports and live sport).")
    v.add_argument("--days", type=int, default=180,
                   help="volume universe only: restrict to markets resolved in "
                        "the last N days. The all-time ranking spans years and "
                        "unrelated topics, so few wallets appear in enough of "
                        "those markets to be measurable.")
    v.add_argument("--include-in-play", action="store_true",
                   help="keep scheduled match markets. Off by default: in a live "
                        "game, trading 'before the repricing' is satisfied by a "
                        "faster stream, which is latency not information.")
    v.set_defaults(func=cmd_discover)

    w = sub.add_parser("wallets", parents=[common], help="deep-dive specific wallets")
    w.add_argument("wallets", nargs="+")
    w.add_argument("--markets", type=int, default=120)
    w.set_defaults(func=cmd_wallets)

    fo = sub.add_parser("follow", parents=[common],
                        help="evaluate copy strategies against recorded liquidity")
    fo.add_argument("wallets", nargs="+",
                    help="the operator's wallets; all are excluded from the "
                         "liquidity a follower consumes")
    fo.add_argument("--markets", type=int, default=300)
    fo.add_argument("--pages", type=int, default=40)
    fo.add_argument("--ticks", type=int, default=1,
                    help="mechanical slippage in ticks, for the comparison column")
    fo.add_argument("--strategies", default="",
                    help="comma-separated subset (default: all)")
    fo.set_defaults(func=cmd_follow)

    s = sub.add_parser("selftest", parents=[common], help="run the test suite")
    s.set_defaults(func=cmd_selftest)

    args = p.parse_args(argv)
    return args.func(args)
