"""Stream rules, and what to do with a post depending on how it matched.

Two tiers, because two very different things can produce a post about a
market and they do not deserve the same size:

**Tier 1, principal.** An account we put on the watch list because it is a
party to the event or covers exactly this beat. We chose it; the trust is
prior.

**Tier 2, keyword.** Whoever happens to be carrying the story. Blind test 2
is the reason this tier exists at all: hand-enumerated account lists caught
0 of 10 markets, and topic rules with a 10k follower floor caught 3 of 8 --
including a Burnham visit broken by @SprinterPress and an OBJ signing
relayed by a 24k-follower aggregator, neither of which was on anybody's
list beforehand.

The same test is the reason tier 2 is sized down rather than sized alike.
Its recall is measured; its *precision* is not. The harness stopped gating
a market once one post passed, so false alarms on the markets that hit were
never counted -- 22 clean rejections across the markets that missed is a
lower bound, not a rate. Sizing tier 2 at a fraction of tier 1 is the price
of acting on evidence with a known hole in it.

## The required keyword

Every rule for a market ANDs one term, including the ``from:`` rules on
principals. A principal's feed is mostly not about the market -- a company
account posts recruitment, memes and conference photos -- and each of those
posts costs $0.005 to receive and an LLM call to reject.

The keyword must be a term that appears in **the announcement itself**, not
the market's subject. This is the easy mistake: for "Will Arcium launch a
token", ``Arcium`` is the obvious word but @Arcium announcing its own token
says "TGE is live", not "Arcium's TGE is live". The keyword for that market
is ``(token OR TGE OR "$ARX")``.

The residual risk is real and is not engineered away here: a principal who
announces with a bare "It's live." and a link matches nothing and is
missed. That is the accepted cost of the filter.
"""

from __future__ import annotations

from dataclasses import dataclass

from .gate import CORROBORATE, DROP, FIRE

PRINCIPAL = "principal"
KEYWORD = "keyword"

#: X filtered-stream rule length cap, characters. The standard limit; the
#: account-list rules are split to stay under it.
MAX_RULE_LEN = 512

#: Account tiers in ``market_accounts.tier`` that count as tier 1. An
#: 'osint' aggregator is on the list for coverage, not for trust, so it is
#: deliberately not here -- it fires at keyword size.
PRINCIPAL_TIERS = frozenset({"principal", "beat", "wire"})


class RuleError(ValueError):
    """A market that cannot produce a valid rule set."""


@dataclass(frozen=True)
class Rule:
    """One X filtered-stream rule."""

    value: str
    tag: str

    def as_dict(self) -> dict:
        return {"value": self.value, "tag": self.tag}


def _group(term: str) -> str:
    """Wrap a query fragment so ANDing it cannot bind an OR wrongly.

    ``a OR b`` ANDed with ``c`` must be ``(a OR b) c``; without the
    parentheses X reads ``a OR b c``, which matches every ``a``.
    """
    t = (term or "").strip()
    if not t:
        return ""
    if t.startswith("(") and t.endswith(")") and _balanced(t[1:-1]):
        return t
    return f"({t})"


def _balanced(s: str) -> bool:
    d = 0
    for ch in s:
        if ch == "(":
            d += 1
        elif ch == ")":
            d -= 1
            if d < 0:
                return False
    return d == 0


def build_rules(market: dict) -> list[Rule]:
    """Every stream rule for one market, tagged so deliveries route back.

    The tag carries the market and the tier, which is how a delivered post
    is priced without re-matching it against the rule text.
    """
    cid = str(market.get("condition_id") or "")
    if not cid:
        raise RuleError("market has no condition_id")

    kw = _group(str(market.get("required_keyword") or ""))
    if not kw:
        raise RuleError(
            f"{cid}: required_keyword is empty. Every rule ANDs one term; a "
            "market without one would deliver a principal's entire feed.")
    if not _balanced(kw):
        raise RuleError(f"{cid}: unbalanced parentheses in required_keyword")

    rules: list[Rule] = []

    handles = sorted({
        str(a.get("handle", "")).lstrip("@").lower()
        for a in market.get("accounts", [])
        if str(a.get("tier", "beat")) in PRINCIPAL_TIERS
        and str(a.get("handle", "")).strip()
    })
    for i, chunk in enumerate(_chunk_handles(handles, kw)):
        rules.append(Rule(f"{chunk} {kw}", f"{cid}:{PRINCIPAL}:{i}"))

    topic = _group(str(market.get("topic_terms") or ""))
    if topic:
        if not _balanced(topic):
            raise RuleError(f"{cid}: unbalanced parentheses in topic_terms")
        # lang:en on the keyword tier only. We chose the principals and take
        # whatever language they post in; the open tier is the noisy one.
        value = f"{topic} {kw} lang:en"
        if len(value) > MAX_RULE_LEN:
            raise RuleError(f"{cid}: keyword rule is {len(value)} chars, "
                            f"over the {MAX_RULE_LEN} limit")
        rules.append(Rule(value, f"{cid}:{KEYWORD}"))

    if not rules:
        raise RuleError(f"{cid}: no principals and no topic_terms -- "
                        "nothing to subscribe to")
    return rules


def _chunk_handles(handles: list[str], kw: str) -> list[str]:
    """Split a handle list into OR-groups that fit inside the rule cap."""
    out: list[str] = []
    cur: list[str] = []
    # +1 for the space before the keyword group.
    budget = MAX_RULE_LEN - len(kw) - 1
    for h in handles:
        term = f"from:{h}"
        trial = cur + [term]
        if len(" OR ".join(trial)) + 2 > budget and cur:
            out.append(f"({' OR '.join(cur)})")
            cur = [term]
        else:
            cur = trial
    if cur:
        out.append(f"({' OR '.join(cur)})")
    return out


def parse_tag(tag: str) -> tuple[str, str]:
    """``condition_id``, ``tier`` from a rule tag. Unknown tags are keyword.

    Defaulting an unrecognised tag to the *lower*-trust tier is deliberate:
    a tag we cannot read must not buy full size.
    """
    parts = (tag or "").split(":")
    if len(parts) < 2:
        return (parts[0] if parts else ""), KEYWORD
    return parts[0], (PRINCIPAL if parts[1] == PRINCIPAL else KEYWORD)


def eligible(market: dict, tier: str, followers: int | None) -> tuple[bool, str]:
    """Is this post worth an LLM call at all?

    The follower floor applies to the keyword tier only. A principal we put
    on the list ourselves is trusted by that choice, however small: a
    company's own account announcing its own token is the whole signal, and
    it may have 500 followers.
    """
    if tier == PRINCIPAL:
        return True, "principal"
    floor = int(market.get("min_followers", 10_000) or 0)
    if followers is None:
        return False, "keyword tier: follower count unavailable"
    if followers < floor:
        return False, f"keyword tier: {followers:,} followers, floor {floor:,}"
    return True, f"keyword tier: {followers:,} followers"


def sizing(market: dict, tier: str) -> tuple[float, float]:
    """``aggression, size_usd`` for the tier that matched."""
    if tier == PRINCIPAL:
        return (float(market.get("aggression", 0.05)),
                float(market.get("max_size_usd", 10.0)))
    return (float(market.get("aggression_kw", 0.02)),
            float(market.get("max_size_usd_kw", 3.0)))


def act(tier: str, gate_action: str) -> tuple[str, str]:
    """Turn the gate's verdict into a decision, given the tier.

    The tiers differ on exactly one case, CORROBORATE. A principal with a
    soft check unclear is worth a second opinion -- latency is nearly free
    and the account is trusted. An unknown account with a soft check
    unclear is the population blind test 2 could not measure precision on,
    and waiting for it to be confirmed is the same as not trading it.
    """
    if gate_action == FIRE:
        return FIRE, f"{tier}: all checks passed"
    if gate_action == CORROBORATE:
        if tier == PRINCIPAL:
            return CORROBORATE, "principal: soft checks unclear, seeking second source"
        return DROP, "keyword tier does not trade on unconfirmed signals"
    return DROP, f"{tier}: gate dropped"
