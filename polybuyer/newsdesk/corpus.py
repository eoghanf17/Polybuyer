"""A durable record of every post the experiments have paid to read.

Posts cost $0.005 each and the full archive is only reachable through a
paid endpoint, so a post read and discarded is money spent twice. More
importantly, a gate change cannot be evaluated against data that no longer
exists: every question added to :mod:`gate` so far has been justified by a
handful of examples recalled from a terminal scrollback, which is not a
test set.

This module is the corpus those changes should be scored against. It is
deliberately append-only JSONL rather than a table in the desk database:
the desk database is operational state that gets rebuilt, and this is the
evidence, which must not.

## What a row has to carry

Three things beyond the text, each because something could not be done
without it:

``post_id``
    X's own id. Without it the same post fetched by two experiments is two
    rows, dedupe is a text hash that breaks on an edited quote, and there
    is no way to link back to the post to check it by hand.

``market_repriced_at`` / ``lead_s``
    A post is only a signal relative to the moment the market moved. The
    same text hours later is a recap. Storing the repricing timestamp with
    the post makes the row self-contained -- it can be scored without
    re-deriving the tape.

``gate``
    The model's full answers, not just fire/drop. A change to one question
    is evaluated by re-reading the stored answers of the other five; only
    rows never scored need a fresh call.

## Labels

``breaker``     this post is the one that broke the story
``chatter``     on-topic but not an announcement
``unlabelled``  read but never adjudicated

The distinction between ``chatter`` and ``unlabelled`` is not pedantry. A
market that repriced with every post dropped is either a market where
nothing was posted, or a false negative -- and only a human reading the
posts can say which. Recording the second case as ``chatter`` by default
would quietly assert the flattering answer.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable, Iterator

BREAKER = "breaker"
CHATTER = "chatter"
UNLABELLED = "unlabelled"

DEFAULT_PATH = "experiments/corpus/posts.jsonl"


def _parse_ts(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class Post:
    """One archived post, with everything needed to re-score it offline."""

    #: X's post id. Empty only for rows recovered from a run that dropped
    #: it; ``key`` falls back to a content hash for those.
    post_id: str = ""
    handle: str = ""
    author_id: str = ""
    followers: int | None = None
    created_at: str = ""
    text: str = ""
    is_retweet: bool = False
    lang: str = ""

    #: The market this post was read against.
    market: str = ""
    condition_id: str = ""
    #: When the market actually repriced, ISO8601.
    market_repriced_at: str = ""

    #: Which experiment paid for this row, and the query that matched it.
    source: str = ""
    query: str = ""

    label: str = UNLABELLED
    label_note: str = ""

    #: Full gate output: answers, direction, action, reason. Empty if the
    #: row has never been scored.
    gate: dict = field(default_factory=dict)

    @property
    def key(self) -> str:
        """Dedupe key. Prefers X's id; hashes content when it is absent."""
        if self.post_id:
            return f"id:{self.post_id}"
        h = hashlib.sha256(
            f"{self.handle}\x00{self.created_at}\x00{self.text}".encode()
        ).hexdigest()[:16]
        return f"h:{h}"

    @property
    def lead_s(self) -> float | None:
        """Seconds between the post and the repricing. Negative = after it.

        Positive means the post came first, which is the only case where
        trading on it was possible.
        """
        a, b = _parse_ts(self.created_at), _parse_ts(self.market_repriced_at)
        if a is None or b is None:
            return None
        return (b - a).total_seconds()

    @property
    def actionable(self) -> bool:
        """Did this post precede the repricing at all?"""
        s = self.lead_s
        return s is not None and s > 0

    def to_json(self) -> str:
        d = asdict(self)
        d["lead_s"] = self.lead_s
        return json.dumps(d, ensure_ascii=False)


def from_dict(d: dict) -> Post:
    """Build a Post, ignoring derived and unknown keys."""
    known = {f for f in Post.__dataclass_fields__}
    return Post(**{k: v for k, v in d.items() if k in known})


def load(path: str = DEFAULT_PATH) -> list[Post]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(from_dict(json.loads(line)))
    return out


def save(posts: Iterable[Post], path: str = DEFAULT_PATH) -> int:
    """Rewrite the corpus, deduped on :attr:`Post.key`.

    Later rows win, so re-running an experiment with richer fields (or a
    fresh gate scoring) upgrades the existing row instead of duplicating
    it. A row's label survives that upgrade unless the new row carries one.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    merged: dict[str, Post] = {}
    for p in posts:
        prev = merged.get(p.key)
        if prev is not None:
            if p.label == UNLABELLED and prev.label != UNLABELLED:
                p.label, p.label_note = prev.label, prev.label_note
            if not p.gate and prev.gate:
                p.gate = prev.gate
            if p.followers is None:
                p.followers = prev.followers
        merged[p.key] = p
    rows = sorted(merged.values(), key=lambda x: (x.market, x.created_at))
    with open(path, "w", encoding="utf-8") as fh:
        for p in rows:
            fh.write(p.to_json() + "\n")
    return len(rows)


def add(new: Iterable[Post], path: str = DEFAULT_PATH) -> int:
    """Merge rows into the corpus on disk. Returns the total row count."""
    return save([*load(path), *new], path)


def score(posts: Iterable[Post], min_followers: int = 0) -> dict[str, Any]:
    """Confusion matrix of the stored gate output against the labels.

    Only labelled, actionable rows count. An unlabelled row is not evidence
    of anything, and a post published after the repricing could not have
    been traded regardless of what the gate said about it.
    """
    tp = fp = tn = fn = 0
    skipped = 0
    for p in posts:
        if p.label == UNLABELLED or not p.gate or not p.actionable:
            skipped += 1
            continue
        if p.followers is not None and p.followers < min_followers:
            skipped += 1
            continue
        fired = p.gate.get("action") in ("fire", "corroborate")
        if p.label == BREAKER:
            tp, fn = (tp + 1, fn) if fired else (tp, fn + 1)
        else:
            fp, tn = (fp + 1, tn) if fired else (fp, tn + 1)
    scored = tp + fp + tn + fn
    return {
        "scored": scored, "skipped": skipped,
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
    }


def by_market(posts: Iterable[Post]) -> dict[str, list[Post]]:
    out: dict[str, list[Post]] = {}
    for p in posts:
        out.setdefault(p.market, []).append(p)
    return out


def needs_label(posts: Iterable[Post]) -> Iterator[Post]:
    """Actionable rows nobody has adjudicated -- the review queue."""
    for p in posts:
        if p.label == UNLABELLED and p.actionable:
            yield p
