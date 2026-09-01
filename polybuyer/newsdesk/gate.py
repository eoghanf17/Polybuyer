"""The LLM gate: does this tweet justify firing?

Design constraints, in order of how much they cost when violated:

**False alarms are the expensive failure.** The out-of-sample experiment put
the cost of firing on stories that went nowhere at 36 points of ROI -- far
more than latency or slippage. So the gate should be willing to drop a
marginal signal.

**Latency is nearly free.** The same experiment found 2s and 45s entries
returned identically, with the cliff between 45s and 120s. A single LLM call
costs 0.3-2s. That is affordable, and it also means a *second* call, or a
short wait for corroboration, is affordable. Speed is not the scarce
resource here; correctness is.

**Every extra hard question multiplies the miss rate.** Eight independent
questions at 2% false-negative each fire only 85% of the time they should.
So the questions below are split: a small hard set that must all pass, and a
soft set that routes a borderline signal to corroboration rather than
binning it.

## The negation trap

The questions never ask "does this favour our side?". Language models are
unreliable on negation, and a model can understand a story perfectly while
inverting a yes/no about it. Instead the model reports **which way the news
cuts**, as a bare token, and the comparison against our intended direction
is done in code. A denial ("officials deny the strike took place") then
correctly produces the opposite direction rather than a confused yes.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Question:
    key: str
    text: str
    #: Must be YES to fire without corroboration.
    hard: bool
    #: The specific misfire this exists to stop.
    catches: str


QUESTIONS: tuple[Question, ...] = (
    Question(
        "relevant", "Is this post about the specific event this market asks about?",
        hard=True,
        catches="the account's ordinary output -- most tweets from a watched "
                "account have nothing to do with the market",
    ),
    Question(
        "factual",
        "Does the post report this as something that has actually happened or "
        "been officially announced, rather than as prediction, speculation, "
        "opinion, analysis, a question, or an unverified rumour?",
        hard=True,
        catches="reporters speculating and analysts forecasting, which is most "
                "of what even excellent accounts post",
    ),
    Question(
        "rules_match",
        "Taking the market's resolution rules exactly as written, including any "
        "deadline: if this report is accurate, does the event described satisfy "
        "those rules -- rather than being a similar-sounding event that would "
        "not count, or one falling outside the market's time window?",
        hard=True,
        catches="the classic near-miss: the market is on the US striking Iran "
                "and the news is Israel striking Iran; or the event happens "
                "after the deadline",
    ),
    Question(
        "novel",
        "Is the event being reported happening RIGHT NOW or within the last "
        "hour or so? Answer false if the post refers back to something that "
        "happened days, weeks or months ago, however significant it was, and "
        "false for recaps, anniversaries, follow-ups and statistics about a "
        "past event.",
        hard=True,
        catches="recaps and retrospectives. Promoted to a hard check after a "
                "live test: 'Reminder: our token launched last month, here "
                "are the stats' passed the softer wording and fired. A recap "
                "is the most common post an account makes about the very "
                "event a market is watching, so this has to be a stop.",
    ),
    Question(
        "material",
        "Is this development large enough that a reasonable trader would expect "
        "the market to reprice substantially on it, rather than marginally?",
        hard=False,
        catches="incremental updates that are genuinely news but already priced "
                "or too small to clear costs",
    ),
    Question(
        "standing",
        "Is this account in a position to know this particular fact -- a party "
        "to the event, or a reporter who covers this beat -- rather than "
        "relaying something outside their usual coverage?",
        hard=False,
        catches="account drift: a politics correspondent posting about a "
                "corporate deal, or an aggregator outside its lane",
    ),
)

HARD = tuple(q.key for q in QUESTIONS if q.hard)
SOFT = tuple(q.key for q in QUESTIONS if not q.hard)

FIRE = "fire"
CORROBORATE = "corroborate"
DROP = "drop"


@dataclass
class GateResult:
    answers: dict[str, bool] = field(default_factory=dict)
    #: Which way the model says the news cuts, on the reference outcome.
    #: +1 makes the reference outcome more likely, -1 less, 0 neither.
    implied_direction: int = 0
    raw: str = ""
    error: str = ""

    @property
    def hard_pass(self) -> bool:
        return all(self.answers.get(k) is True for k in HARD)

    @property
    def soft_pass(self) -> bool:
        return all(self.answers.get(k) is True for k in SOFT)

    def failed(self) -> list[str]:
        return [q.key for q in QUESTIONS if self.answers.get(q.key) is not True]


def build_prompt(market: dict, tweet_text: str, handle: str) -> str:
    """One call, all questions, plus the direction as a separate field."""
    qs = "\n".join(f'  "{q.key}": {q.text}' for q in QUESTIONS)
    return f"""You are screening a social media post for a prediction market trading system.

MARKET: {market.get('question', '')}

RESOLUTION RULES: {market.get('rules') or '(none recorded)'}

POST by @{handle}:
\"\"\"{tweet_text}\"\"\"

Answer each question true or false:
{qs}

Also report which way this post cuts for the market, independently of the
questions above:
  "direction": 1 if it makes the market MORE likely to resolve YES,
               -1 if it makes it more likely to resolve NO,
               0 if neither or unclear.
A denial or refutation of the event is -1, not 1.

Reply with JSON only, no other text:
{{"relevant": bool, "factual": bool, "rules_match": bool, "novel": bool,
 "material": bool, "standing": bool, "direction": -1|0|1}}"""


def parse(raw: str) -> GateResult:
    """Parse the model's reply, defaulting every unknown to a refusal.

    An unparseable or partial answer must never read as permission to trade,
    so anything missing is false and the direction is 0.
    """
    r = GateResult(raw=raw)
    m = re.search(r"\{.*\}", raw or "", re.S)
    if not m:
        r.error = "no JSON found"
        return r
    try:
        d: dict[str, Any] = json.loads(m.group(0))
    except json.JSONDecodeError as e:
        r.error = f"bad JSON: {e}"
        return r

    for q in QUESTIONS:
        v = d.get(q.key)
        r.answers[q.key] = v is True
    try:
        r.implied_direction = int(d.get("direction", 0))
    except (TypeError, ValueError):
        r.implied_direction = 0
    if r.implied_direction not in (-1, 0, 1):
        r.implied_direction = 0
    return r


def decide(result: GateResult, preferred_direction: int) -> tuple[str, str]:
    """Fire, wait for corroboration, or drop. Returns (action, reason).

    Direction is compared in code rather than asked as a yes/no, so a post
    that clearly cuts the other way is rejected even if the model answered
    the questions carelessly.
    """
    if result.error:
        return DROP, f"gate error: {result.error}"
    if result.implied_direction == 0:
        return DROP, "post does not clearly cut either way"
    if result.implied_direction != preferred_direction:
        return DROP, (f"post implies direction {result.implied_direction:+d}, "
                      f"we want {preferred_direction:+d}")
    if not result.hard_pass:
        missing = [k for k in HARD if not result.answers.get(k)]
        return DROP, f"failed hard checks: {', '.join(missing)}"
    if not result.soft_pass:
        missing = [k for k in SOFT if not result.answers.get(k)]
        # Latency is cheap and false alarms are not, so a borderline signal
        # buys a second opinion instead of being thrown away.
        return CORROBORATE, f"soft checks unclear: {', '.join(missing)}"
    return FIRE, "all checks passed"
