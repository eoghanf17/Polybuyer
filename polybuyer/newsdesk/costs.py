"""What the desk costs to run, and how many markets a budget buys.

The armed-market count was treated as a research question for most of this
project — how many markets look interesting? It is a budget question first.
X charges per post *delivered*, so every armed market bills continuously
whether or not it ever fires, and 252 markets projects to somewhere between
$700 and $7,000 a month.

Density here is measured, not guessed. Blind tests 3 and 4 searched 2-hour
windows and returned 10.3 and 5.2 posts per market-hour. Both runs capped
``max_results``, so those are **floors**, and both windows sat immediately
before a repricing, so they are also the busiest two hours that market had.
``quiet_factor`` discounts from that peak to an average hour; 5 is the
default and is a guess, which is why it is a parameter and why the first
month of live running should replace it with an observed number.
"""

from __future__ import annotations

from dataclasses import dataclass

#: $ per post delivered by the filtered stream.
POST_USD = 0.005

#: Posts per market per hour during a news window, from blind tests 3 and 4.
#: A floor: both runs hit their max_results cap.
PEAK_POSTS_PER_MARKET_HOUR = 7.8

#: How much quieter an average hour is than a news window. A guess, and the
#: single largest source of error in any figure this module produces.
DEFAULT_QUIET_FACTOR = 5.0

#: OpenAI cost per gate call at gpt-4.1, from the observed prompt size.
GATE_CALL_USD = 0.0018


@dataclass(frozen=True)
class CostEstimate:
    markets: int
    posts_per_day: float
    x_usd_month: float
    gate_usd_month: float

    @property
    def total_usd_month(self) -> float:
        return self.x_usd_month + self.gate_usd_month


def cost_model(markets: int, quiet_factor: float = DEFAULT_QUIET_FACTOR,
               gate_share: float = 1.0) -> CostEstimate:
    """Monthly cost of watching ``markets`` markets.

    ``gate_share`` is the fraction of delivered posts that reach the LLM.
    It is 1.0 by default because the follower floor is applied to metadata
    that arrives *with* the post — the post is already paid for by then.
    """
    per_hour = PEAK_POSTS_PER_MARKET_HOUR / max(quiet_factor, 1e-9)
    per_day = per_hour * 24 * markets
    x = per_day * 30 * POST_USD
    gate = per_day * 30 * gate_share * GATE_CALL_USD
    return CostEstimate(markets, per_day, x, gate)


def markets_for_budget(usd_month: float,
                       quiet_factor: float = DEFAULT_QUIET_FACTOR,
                       gate_share: float = 1.0) -> int:
    """How many markets a monthly budget affords. Rounds down, never up."""
    one = cost_model(1, quiet_factor, gate_share).total_usd_month
    if one <= 0:
        return 0
    return max(0, int(usd_month / one))
