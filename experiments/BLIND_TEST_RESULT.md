# Blind account prediction: 0 hits out of 10

Predictions were committed at `460281e` before any search. Scoring searched
FROM each predicted handle in the 24 hours before the market repriced and
gated what it found.

| market | predicted accounts | posts scanned | result |
|---|---|---:|---|
| Graham Platner drops out | @GrahamPlatner, @politico, @AP | 20 | miss |
| SHEIN IPO | @Reuters, @business, @FT | 60 | miss |
| SpaceX or OpenAI IPO | @elonmusk, @sama, @OpenAI, @SpaceX | 28 | miss |
| Binance stock tokens | @binance, @_RichardTeng, @cz_binance | 40 | miss |
| Infrared token | @InfraredFinance, @infrared_fi | 7 | miss |
| Guardiola out | @FabrizioRomano, @ManCity, @David_Ornstein | 37 | miss |
| Tria token | @tria, @useTria, @triaprotocol | 2 | miss |
| GRVT token | @grvt_io, @GRVT_official | 0 | miss |
| Kellogg visits Ukraine | @generalkellogg, @ZelenskyyUa, @StateDept | 26 | miss |
| Bitmine 5M ETH | @BitMNR, @fundstrat, @fundstratTom | 2 | miss |

The two predicted failures (Khamenei as a control, the US-announcement
markets as Truth Social) are excluded rather than counted as correct.

## Three different reasons, and they need different fixes

**The account was right and the gate was wrong.** Guardiola. Fabrizio Romano
posted 16 minutes before the repricing, and again at +13 and +55 minutes.
The gate rejected all three on `resolves`, because his phrasing is hedged --
"expected to leave", "top candidate to become". David Ornstein's flat
"Guardiola to leave position" fired instantly. The gate was demanding
resolution certainty from a market that trades probability. Fixed: a
credible report of a decision taken now counts. That rescues the +55m post,
though not the -16m one.

**The handle was wrong, the behaviour was right.** GRVT returned zero posts
across two guessed handles, Tria two, Infrared seven. These projects
certainly announced somewhere; I could not name where. A wrong handle is a
silent total failure -- the stream simply never fires, with no error.

**Nobody I predicted was in the room.** SHEIN repriced on Beijing approving
an overseas-listing filing, surfaced by accounts with a few hundred
followers. SpaceX/OpenAI repriced on a report in The Information, relayed by
aggregators. Binance repriced on "reportedly considering", not an
announcement. In each case the wires and principals I predicted were
correct-but-absent, and the news arrived through a diffuse cloud of small
relay accounts that cannot be enumerated in advance.

## What survives

Even after the gate fix, **the only genuinely pre-repricing signal in ten
markets was Romano's -16m post**, and it is implicit: naming a successor
without saying the incumbent is leaving. The gate still declines it, and
declining is defensible -- candidates get named for jobs that never open.

So the honest read is that the principal-and-beat-reporter list, chosen in
advance, would have caught none of these markets before they moved. The
strategy does not fail on latency, cost or filtering. It fails on
**enumerability**: you cannot write down the account list ahead of time,
because a third of the time the breaker is an aggregator nobody would have
listed.

## Where that points

The one design that survives this result is **topic subscription rather than
account subscription**. The filtered stream takes keyword rules, not just
`from:` rules, so a rule like `(Guardiola) (leave OR leaving OR exit)` would
have caught Romano, Ornstein, and the aggregator cloud together -- at the
cost of a far noisier feed, which is what the gate is for and what it is
now measured at 16/17 on.

That is a different system from the one specced, and it should be tested the
same way before it is built.
