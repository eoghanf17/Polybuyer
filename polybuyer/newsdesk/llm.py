"""The gate's model call.

Kept behind a tiny interface so the model, or the vendor, can change without
touching the decision logic. What matters here is not which model runs but
that a failure is never mistaken for permission: a timeout, a refusal, an
outage and a malformed reply all have to end in "do not trade".
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

from .gate import GateResult, build_prompt, parse

OPENAI_URL = "https://api.openai.com/v1/chat/completions"


@dataclass
class GateCall:
    result: GateResult
    latency_ms: int
    tokens_in: int = 0
    tokens_out: int = 0
    #: Cost of this single call in USD, at the model's list price.
    cost_usd: float = 0.0


#: $/1M tokens (input, output). Rough list prices; used only for the running
#: cost log, never for a trading decision.
PRICES = {
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4o": (2.50, 10.00),
    "gpt-5": (1.25, 10.00),
}


def ask(market: dict, tweet_text: str, handle: str, api_key: str,
        model: str = "gpt-4.1", timeout: float = 8.0) -> GateCall:
    """Score one post against one market.

    ``temperature=0`` because this is a classification, not a composition,
    and a gate that answers differently on identical input cannot be
    reasoned about. The timeout is deliberately short: the strategy has
    minutes of latency budget, but a hung call holds a slot open while the
    next post arrives.

    Default model is ``gpt-4.1``, chosen by measurement rather than instinct.
    Benchmarked on the labelled calibration set it was both the most accurate
    (16/17, no false negatives) and the *fastest* (726ms median against
    931ms for gpt-4o-mini). The cheaper model was picked first on cost, but
    keyword-filtered stream rules cut gate volume to a few hundred calls a
    month, at which point the difference is $0.05 against $0.62 and accuracy
    is the only thing left to optimise.
    """
    body = json.dumps({
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "user",
                      "content": build_prompt(market, tweet_text, handle)}],
    }).encode()

    req = urllib.request.Request(
        OPENAI_URL, data=body,
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"})

    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read().decode())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        # Any failure is a refusal. Never a fire.
        g = GateResult(error=f"{type(e).__name__}: {e}")
        return GateCall(g, int((time.time() - t0) * 1000))

    ms = int((time.time() - t0) * 1000)
    try:
        text = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return GateCall(GateResult(error="unexpected response shape"), ms)

    usage = payload.get("usage") or {}
    ti = int(usage.get("prompt_tokens", 0))
    to = int(usage.get("completion_tokens", 0))
    pin, pout = PRICES.get(model, (0.15, 0.60))
    return GateCall(parse(text), ms, ti, to, ti / 1e6 * pin + to / 1e6 * pout)
