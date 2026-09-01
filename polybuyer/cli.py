"""Command-line entry point.

    python -m polybuyer demo              offline, synthetic, no network
    python -m polybuyer discover          live sweep against the APIs
    python -m polybuyer wallets 0x... 0x. deep-dive named wallets
    python -m polybuyer selftest          run the test suite
"""

from __future__ import annotations

import argparse
import sys

from .config import DEFAULT, Config, StatsConfig
from .netio import Fetcher
from .report import detail, summary, table, to_json


def _cfg(args) -> Config:
    cfg = DEFAULT
    if args.cap is not None:
        cfg = cfg.with_(follow=type(cfg.follow)(**{**cfg.follow.__dict__, "cap": args.cap}))
    if args.boot is not None:
        cfg = cfg.with_(stats=StatsConfig(
            n_boot=args.boot, ci_lo=cfg.stats.ci_lo, ci_hi=cfg.stats.ci_hi,
            seed=cfg.stats.seed, fdr_q=cfg.stats.fdr_q,
            min_clusters=cfg.stats.min_clusters))
    if args.cache:
        cfg = cfg.with_(cache_dir=args.cache)
    return cfg


def _emit(a, args, n_seen: int) -> None:
    if args.json:
        print(to_json(a.ranked))
        return
    print(summary(a.ranked, n_seen))
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
        cfg = cfg.with_(stats=StatsConfig(
            n_boot=1500, ci_lo=cfg.stats.ci_lo, ci_hi=cfg.stats.ci_hi,
            seed=cfg.stats.seed, fdr_q=cfg.stats.fdr_q,
            min_clusters=cfg.stats.min_clusters))

    print(f"building synthetic universe ({args.markets} markets)...")
    rows, payloads, _ = syn.universe(n_markets=args.markets, jump_dur_s=args.jump_dur)
    print(f"  {len(rows)} prints across {len(payloads)} markets")
    a = analyse(rows, payloads, cfg)
    print(f"  {a.n_jumps} repricings detected\n")
    _emit(a, args, len(a.features))
    return 0


def cmd_discover(args) -> int:
    from .pipeline import discover

    cfg = _cfg(args)
    fetch = Fetcher(cache_dir=cfg.cache_dir, use_cache=not args.no_cache)
    a = discover(fetch, cfg, max_markets=args.markets,
                 cluster_wallets=not args.no_clusters,
                 progress=lambda m: print(m, file=sys.stderr))
    print(f"cache: {fetch.stats}", file=sys.stderr)
    _emit(a, args, len(a.features))
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
    v.set_defaults(func=cmd_discover)

    w = sub.add_parser("wallets", parents=[common], help="deep-dive specific wallets")
    w.add_argument("wallets", nargs="+")
    w.add_argument("--markets", type=int, default=120)
    w.set_defaults(func=cmd_wallets)

    s = sub.add_parser("selftest", parents=[common], help="run the test suite")
    s.set_defaults(func=cmd_selftest)

    args = p.parse_args(argv)
    return args.func(args)
