"""Database schema for the news-trading desk.

Deliberately plain SQL. SQLite runs it locally with no server, and the same
DDL ports to Postgres or D1 with only the autoincrement line changing, so
the choice of where this lives can be deferred without rewriting anything.

One row per market we have decided to watch, plus the accounts that could
break it, plus an audit row for every fire and every blocked fire. The
blocked ones matter as much as the fires: they are the record of the
strategy declining to chase, and the only way to find out later whether the
guards were set sensibly.
"""

from __future__ import annotations

SCHEMA_VERSION = 3

DDL = [
    """
    CREATE TABLE IF NOT EXISTS markets (
        condition_id      TEXT PRIMARY KEY,
        slug              TEXT,
        question          TEXT NOT NULL,
        rules             TEXT,
        end_date          TEXT,
        category          TEXT,

        -- Which way we intend to trade if the news lands. +1 = long the
        -- reference outcome (index 0), -1 = long the other side.
        preferred_direction INTEGER NOT NULL DEFAULT 1,
        token_id_ref      TEXT,
        token_id_other    TEXT,

        -- The one term that must appear in a post for it to be worth
        -- reading, ANDed into every stream rule for this market including
        -- the from: rules on principals. An X query fragment, so an
        -- OR-group is allowed: '(token OR TGE OR "$ARX")'.
        required_keyword  TEXT NOT NULL DEFAULT '',

        -- Whether the required keyword is ANDed into the principals'
        -- from: rules too. 1 = filter them (cheaper, and the reason the
        -- keyword exists); 0 = take a principal's whole feed and let the
        -- gate sort it out. Per market, but the point of the column is
        -- that it can be flipped across every row at once if the filter
        -- turns out to be costing announcements.
        keyword_gate_principals INTEGER NOT NULL DEFAULT 1,

        -- Tier-2 subject terms. Empty disables the keyword tier entirely
        -- and leaves the market watching its principals only.
        topic_terms       TEXT NOT NULL DEFAULT '',

        -- Follower floor for the keyword tier. Blind test 2 measured this:
        -- 10k stripped the only false alarm without losing a hit.
        min_followers     INTEGER NOT NULL DEFAULT 10000,

        -- How far through the pre-move mid we are willing to pay, and how
        -- much. Per market so a thin market can be handled differently.
        -- The unsuffixed pair is tier 1 (a principal we chose); _kw is
        -- tier 2 (an account the keyword rule turned up).
        aggression        REAL NOT NULL DEFAULT 0.05,
        max_size_usd      REAL NOT NULL DEFAULT 10.0,
        aggression_kw     REAL NOT NULL DEFAULT 0.02,
        max_size_usd_kw   REAL NOT NULL DEFAULT 3.0,

        -- Armed or not. Set to 0 after a fire, and also after a fire is
        -- blocked by the move guards: if the market already moved without
        -- us, the trade is gone and re-arming would only chase it.
        on_off            INTEGER NOT NULL DEFAULT 1,
        off_reason        TEXT,
        off_at            TEXT,

        -- Don't-chase guards. If the price has already moved this far our
        -- way over the window, the news is in the price.
        guard_5m          REAL NOT NULL DEFAULT 0.20,
        guard_1h          REAL NOT NULL DEFAULT 0.20,
        guard_2h          REAL NOT NULL DEFAULT 0.20,
        guard_1d          REAL NOT NULL DEFAULT 0.30,

        added_at          TEXT NOT NULL,
        added_by          TEXT,
        notes             TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS market_accounts (
        condition_id  TEXT NOT NULL,
        handle        TEXT NOT NULL,
        -- 'principal' = party to the event (a minister, the company, the
        -- named person). 'beat' = a reporter who covers this specifically.
        -- 'wire' = agency. 'osint' = fast aggregator, lowest trust.
        tier          TEXT NOT NULL DEFAULT 'beat',
        why           TEXT,
        PRIMARY KEY (condition_id, handle)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS seen_markets (
        condition_id  TEXT PRIMARY KEY,
        question      TEXT,
        first_seen    TEXT NOT NULL,
        decision      TEXT NOT NULL DEFAULT 'pending',
        reason        TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS fires (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        condition_id  TEXT NOT NULL,
        at            TEXT NOT NULL,
        tweet_id      TEXT,
        handle        TEXT,
        tweet_text    TEXT,
        direction     INTEGER,
        -- 'principal' | 'keyword' -- which tier matched this post.
        tier          TEXT,
        followers     INTEGER,
        mid_before    REAL,
        limit_price   REAL,
        size_usd      REAL,
        -- 'paper' | 'live' | 'blocked'
        status        TEXT NOT NULL,
        block_reason  TEXT,
        gate_answers  TEXT,
        move_5m       REAL,
        move_1h       REAL,
        move_2h       REAL,
        move_1d       REAL,
        latency_ms    INTEGER
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_markets_on ON markets(on_off)",
    "CREATE INDEX IF NOT EXISTS idx_accounts_handle ON market_accounts(handle)",
    "CREATE INDEX IF NOT EXISTS idx_fires_market ON fires(condition_id)",
    """
    CREATE TABLE IF NOT EXISTS meta (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """,
]

#: Defaults for a newly accepted market, so the review flow only has to
#: supply what is genuinely market-specific.
DEFAULTS = {
    "aggression": 0.05,
    "max_size_usd": 10.0,
    "aggression_kw": 0.02,
    "max_size_usd_kw": 3.0,
    "min_followers": 10_000,
    "keyword_gate_principals": 1,
    "on_off": 1,
    "guard_5m": 0.20,
    "guard_1h": 0.20,
    "guard_2h": 0.20,
    "guard_1d": 0.30,
}

#: Columns added after v1, applied to an existing database on open.
#: SQLite has no "ADD COLUMN IF NOT EXISTS", so the caller checks
#: PRAGMA table_info first; these are the statements it runs.
MIGRATIONS: dict[int, list[str]] = {
    3: [
        "ALTER TABLE markets ADD COLUMN keyword_gate_principals"
        " INTEGER NOT NULL DEFAULT 1",
    ],
    2: [
        "ALTER TABLE markets ADD COLUMN required_keyword TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE markets ADD COLUMN topic_terms TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE markets ADD COLUMN min_followers INTEGER NOT NULL DEFAULT 10000",
        "ALTER TABLE markets ADD COLUMN aggression_kw REAL NOT NULL DEFAULT 0.02",
        "ALTER TABLE markets ADD COLUMN max_size_usd_kw REAL NOT NULL DEFAULT 3.0",
        "ALTER TABLE fires ADD COLUMN tier TEXT",
        "ALTER TABLE fires ADD COLUMN followers INTEGER",
    ],
}
