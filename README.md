# Polybuyer — trader discovery

Finds Polymarket accounts whose **timing** looks informed, and works out
whether they can actually be copied.

Two archetypes, because these are the ones worth following:

- **Anticipatory** — repeatedly positioned *before* the price moves.
- **News flow** — repeatedly among the first, and the most accurate, to
  react once it starts moving.

Neither is visible in profit and loss, which is silent about timing. The
method uses market repricings as reference clocks and times every
participant against them. See [`docs/METHOD.md`](docs/METHOD.md).

## Quick start

```bash
pip install numpy

# Runs the whole pipeline offline on a synthetic universe containing a
# planted insider, a planted news desk, a follower, market makers and a
# crowd of noise.  No network access required.
python -m polybuyer demo

python -m polybuyer selftest        # 63 tests
```

Live, once the APIs are reachable:

```bash
python -m polybuyer discover --markets 150       # sweep and rank
python -m polybuyer wallets 0xabc... --detail 1  # deep-dive named wallets
python -m polybuyer discover --json > out.json
```

Useful flags: `--cap` (slippage cap in probability points, default `0.02`),
`--boot` (bootstrap resamples), `--cache` / `--no-cache`, `--limit`,
`--detail`.

Every response is cached to disk (`.polycache/`), so re-running an analysis
while tuning thresholds costs nothing and stays reproducible as the live
tape moves.

## Network access

**The Polymarket APIs are blocked from the environment this was written in.**
`data-api`, `clob`, `gamma-api`, `lb-api`, `ws-live-data` and
`polygon.blockscout.com` all return 403 at the egress proxy, and WebSocket
upgrades are not supported through it at all. So the live paths
(`discover`, `wallets`) are written to the verified endpoint contracts but
have **not been exercised against the real APIs**. Run them somewhere with
egress before trusting them.

Everything else — detection, scoring, statistics, fill simulation,
clustering, reporting — is exercised end to end by the test suite against
synthetic tapes with known ground truth, which is how the detector's
correctness was established without live data.

## What it does

1. **Harvest** candidates from the recent large-trade tape. There is no
   leaderboard listing endpoint, so the pool is built from trades; that
   biases toward currently-active, large traders, which is the right
   population anyway.
2. **Detect repricings** — large, persistent price moves — in each market.
3. **Time every participant** against each repricing: positioned before it,
   first to react, or arriving late.
4. **Score** anticipation and reaction accuracy against the rate achieved by
   everyone else in the same window.
5. **Simulate copying** each trader's opening trade against the executed
   tape, measuring fill, slippage and adverse selection.
6. **Screen and rank**, gated on false-discovery control and on whether the
   trade was actually gettable.

## The main result

The two archetypes are blocked by **opposite constraints**:

| | anticipatory | news reaction |
|---|---|---|
| time before price clears a 2c cap | ~1.5 hours | ~5 seconds |
| share of size actually fillable | ~7–11% | ~95–100% |
| binding constraint | **liquidity** | **latency** |

Anticipatory traders act in the quiet tape before news — plenty of time to
copy, almost nothing to copy into. News traders act inside the burst —
abundant size, but the price clears a limit in seconds. Speed is decisive
for one archetype and nearly irrelevant for the other, and they need
different infrastructure. The verdict names which constraint binds.

## Layout

```
polybuyer/
  model.py      trades normalised onto one reference axis
  tape.py       price paths, follow windows, fill simulation
  jumps.py      repricing detection and participant timing
  pnl.py        mark-to-terminal PnL and deployed capital
  stats.py      cluster bootstrap, FDR control, effective N
  features.py   per-wallet feature extraction
  scores.py     archetype classification, screens, follow verdict
  clusters.py   sibling-wallet detection via the funding graph
  sources.py    the Polymarket read APIs, with their caps enforced
  netio.py      cached HTTP with a curl fallback
  pipeline.py   offline core + live discovery
  report.py     rendering
  cli.py        entry point
tests/
  synthetic.py  tape generator with planted actors and known truth
```

## Caveats

- Fill figures are **lower bounds**: no historical order books exist, so
  only prints that actually executed count as liquidity.
- Market tapes stop at ~12,000 prints (newest first); coverage is returned
  with the data and must be checked before trusting a simulation.
- Every number is in-sample on a pool selected for being interesting. The
  output is a shortlist to paper-trade forward, not a backtest to size from.
