# Strategy, frozen from the TRAIN half

**Written from train markets only (ending on or before 2026-03-31).
Committed before any test market's tape was fetched.**

## What training showed

877 repricings across 510 markets:

| category | mkts | jumps/mkt | med move | med window | <45s | <2s |
|---|---:|---:|---:|---:|---:|---:|
| **geopolitics** | 47 | **6.04** | 13% | **4m** | 32% | **0%** |
| **politics** | 31 | 4.84 | 12% | 2m | 37% | **0%** |
| **corporate** | 20 | 4.30 | 13% | 2m | 42% | **0%** |
| crypto | 30 | 3.17 | 11% | 84s | 41% | 0% |
| sports | 25 | 3.92 | 12% | 50s | 45% | 0% |
| macro | 3 | 4.67 | 15% | 28s | 64% | 0% |

**The finding that shapes everything: nothing gaps.** Not one repricing in
877 cleared a 2c cap inside 2 seconds, and the median target-category move
leaves the price gettable for two to four minutes. Polymarket is not an
equity tape. Whatever a firehose is worth here, it is not the difference
between trading and not trading.

## Targets (fixed)

**Trade:** `geopolitics`, `politics`, `corporate`.

Highest repricing density, largest moves, and the longest latency budget --
and all three are topics that break by surprise on X rather than resolving
to a timetable.

**Do not trade:**

- `sports` -- resolves by play. No tweet front-runs a Super Bowl future.
- `macro` -- the fastest windows in the sample (28s median, 64% under 45s).
  Scheduled releases are arbitraged by people with better infrastructure;
  this is where a bot without a firehose is guaranteed to be last.
- `crypto` -- mostly price-threshold markets that drift continuously rather
  than repricing on news.
- `other` -- residual, no coherent character.

## Accounts (design artefact -- UNVALIDATED)

X returns 401 without credentials, so **none of this is tested**. It is
domain knowledge about who breaks what, recorded so it can be validated
later by someone with archive access.

**Geopolitics** — the highest-value target, and the noisiest.
- Wires: `@Reuters` `@AP` `@AFP` `@BNONews`
- OSINT relays: `@sentdefender` `@AuroraIntel` `@ELINTNews`
- Official: `@IDF` `@IsraeliPM` `@WhiteHouse` `@SecDef` `@StateDept`
- Regional: `@IranIntl_En` `@TasnimNews_EN`

The OSINT accounts are minutes ahead of the wires and are where the edge
would live -- and equally where the false alarms come from. A wire-only
feed is slower but almost never wrong; an OSINT feed is fast and sometimes
reports strikes that did not happen. That tradeoff is the central design
choice and it is exactly what this test cannot resolve without archive
access.

**Politics**
- `@AP` `@DecisionDeskHQ` (race calls are authoritative)
- `@SCOTUSblog` (rulings, minutes ahead of wires)
- Scoop reporters: `@maggieNYT` `@kaitlancollins` `@jaketapper`

**Corporate**
- `@DeItaone` (Walter Bloomberg) -- the single highest-value account here;
  a headline relay that consistently front-runs the wires' own feeds
- `@FirstSquawk` `@business` `@CNBC`
- `@elonmusk` -- self-breaking for anything Tesla/SpaceX/X
- Entertainment: `@PopBase` `@PopCrave` `@TMZ`

## Entry rule (fixed, as pre-registered)

Enter at `onset + L`, in the jump's direction, limit `price + 2c`, filling
only from prints that actually executed in the next 10 minutes. $500 per
signal. Hold to resolution.

## Addition to the pre-registration, made before seeing the test set

The jump detector requires a move to **persist**, so testing only on
detected jumps silently assumes the bot never fires on a story that fizzles.
A real feed produces false alarms -- a strike reported and denied, a rumour
that reverts -- and those are losing trades.

So the test reports **two signal sets**:

1. `persistent` -- detected jumps, i.e. news that turned out to be real.
2. `all-alarms` -- the same plus candidate moves that reverted, which the
   persistence filter would normally discard.

The second is the honest number for an automated feed. The gap between them
is the cost of false alarms, and reporting only the first would flatter the
strategy in exactly the way the pre-registration exists to prevent.

## Viability bar (unchanged)

TEST set, 45s latency, 80% direction accuracy, ROI positive at bootstrap
p < 0.05. Anything less is reported as not demonstrated.
